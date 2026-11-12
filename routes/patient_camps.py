from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    request
)
from mysql.connector import IntegrityError

from db import get_db_connection
from utils.decorators import login_required, role_required
from utils.camp_status import refresh_camp_statuses

patient_camps = Blueprint("patient_camps", __name__)


# 1. Display available health camps to patients
@patient_camps.route("/patient/camps")
@login_required
@role_required("patient")
def list_available_camps():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                c.camp_id,
                c.camp_name,
                c.description,
                c.location,
                c.city,
                c.state,
                c.camp_date,
                TIME_FORMAT(c.start_time, '%h:%i %p') AS display_start_time,
                TIME_FORMAT(c.end_time, '%h:%i %p') AS display_end_time,
                c.capacity,

                (
                    SELECT COUNT(*)
                    FROM registrations r
                    WHERE r.camp_id = c.camp_id
                      AND r.status <> 'cancelled'
                ) AS registered_count,

                (
                    SELECT COUNT(*)
                    FROM camp_doctors cd
                    WHERE cd.camp_id = c.camp_id
                ) AS doctor_count

            FROM camps c

            WHERE c.status = 'upcoming'
              AND c.camp_date >= CURDATE()

            ORDER BY c.camp_date ASC
        """)

        available_camps = cursor.fetchall()
        # Retrieve doctors assigned to each available camp
        cursor.execute("""
            SELECT
                cd.camp_id,
                d.doctor_id,
                d.full_name,
                d.specialization
            FROM camp_doctors cd
            JOIN doctors d ON cd.doctor_id = d.doctor_id
            JOIN camps c ON cd.camp_id = c.camp_id
            WHERE c.status = 'upcoming'
            AND c.camp_date >= CURDATE()
            AND d.specialization IS NOT NULL
            AND TRIM(d.specialization) <> ''
            ORDER BY d.full_name
        """)

        assigned_doctors = cursor.fetchall()

        # Organize doctors according to their camp
        doctors_by_camp = {
            camp["camp_id"]: [] for camp in available_camps
        }

        for doctor in assigned_doctors:
            doctors_by_camp[doctor["camp_id"]].append(doctor)

        return render_template(
            "patient_camps.html",
            camps=available_camps,
            doctors_by_camp=doctors_by_camp
        )

    except Exception as e:
        print("Patient camp list error:", e)
        flash("Unable to retrieve available health camps.", "danger")
        return redirect(url_for("dashboard.patient"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()



# 2. Register a patient for a health camp
@patient_camps.route(
    "/patient/camps/<int:camp_id>/register",
    methods=["POST"]
)
@login_required
@role_required("patient")
def register_for_camp(camp_id):

    connection = None
    cursor = None

    # Map patient concerns to doctor specializations
    concern_mapping = {
        "General health": "General Physician",
        "Heart problems": "Cardiologist",
        "Skin problems": "Dermatologist",
        "Eye problems": "Ophthalmologist",
        "Child health": "Paediatrician",
        "Women's health": "Gynaecologist",
        "Dental problems": "Dentist",
        "Other concerns": "Other"
    }

    medical_concern = request.form.get(
        "medical_concern", ""
    ).strip()

    doctor_id_input = request.form.get("doctor_id", "").strip()

    if medical_concern not in concern_mapping:
        flash("Please select a valid medical concern.", "danger")
        return redirect(url_for("patient_camps.list_available_camps"))

    try:
        doctor_id = int(doctor_id_input)

        if doctor_id <= 0:
            raise ValueError

    except (ValueError, TypeError):
        flash("Please select a valid doctor.", "danger")
        return redirect(url_for("patient_camps.list_available_camps"))

    expected_specialization = concern_mapping[medical_concern]

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Find the patient's profile
        cursor.execute("""
            SELECT patient_id
            FROM patients
            WHERE user_id = %s
        """, (session["user_id"],))

        patient = cursor.fetchone()

        if not patient:
            flash("Patient profile not found.", "danger")
            return redirect(url_for("dashboard.patient"))

        patient_id = patient["patient_id"]

        # Lock the camp row while checking capacity
        cursor.execute("""
            SELECT camp_id, capacity
            FROM camps
            WHERE camp_id = %s
              AND status = 'upcoming'
              AND camp_date >= CURDATE()
            FOR UPDATE
        """, (camp_id,))

        camp = cursor.fetchone()

        if not camp:
            connection.rollback()
            flash(
                "This camp is no longer available for registration.",
                "warning"
            )
            return redirect(url_for("patient_camps.list_available_camps"))

        # Verify that the selected doctor is assigned to this camp
        # and has the required specialization
        cursor.execute("""
            SELECT
                d.doctor_id,
                d.specialization,
                cd.patient_limit
            FROM camp_doctors cd
            JOIN doctors d ON cd.doctor_id = d.doctor_id
            WHERE cd.camp_id = %s
            AND d.doctor_id = %s
        """, (camp_id, doctor_id))

        selected_doctor = cursor.fetchone()

        if (
            not selected_doctor
            or not selected_doctor["specialization"]
            or selected_doctor["specialization"].strip().casefold()
            != expected_specialization.casefold()
        ):
            connection.rollback()
            flash(
                "The selected doctor is not available for this concern.",
                "danger"
            )
            return redirect(url_for("patient_camps.list_available_camps"))

        # Check whether the patient has already registered
        cursor.execute("""
            SELECT registration_id
            FROM registrations
            WHERE patient_id = %s
              AND camp_id = %s
              AND status <> 'cancelled'
        """, (patient_id, camp_id))

        existing_registration = cursor.fetchone()

        if existing_registration:
            connection.rollback()
            flash(
                "You have already registered for this camp.",
                "warning"
            )
            return redirect(url_for("patient_camps.list_available_camps"))

        # Count registrations that are not cancelled
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM registrations
            WHERE camp_id = %s
              AND status <> 'cancelled'
        """, (camp_id,))

        registered_count = cursor.fetchone()["total"]

        if registered_count >= camp["capacity"]:
            connection.rollback()
            flash("Sorry, this health camp is full.", "danger")
            return redirect(url_for("patient_camps.list_available_camps"))

        # Count active registrations for the selected doctor
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM registrations
            WHERE camp_id = %s
            AND doctor_id = %s
            AND status <> 'cancelled'
        """, (camp_id, doctor_id))

        doctor_registered_count = cursor.fetchone()["total"]

        # Check the selected doctor's patient limit
        if doctor_registered_count >= selected_doctor["patient_limit"]:
            connection.rollback()
            flash(
                "Sorry, this doctor has reached the patient limit for this camp. "
                "Please select another doctor.",
                "warning"
            )
            return redirect(url_for("patient_camps.list_available_camps"))
        # Check whether this patient has a cancelled registration
        cursor.execute("""
            SELECT registration_id, token_no
            FROM registrations
            WHERE patient_id = %s
            AND camp_id = %s
            AND doctor_id = %s
            AND status = 'cancelled'
            ORDER BY registration_id DESC
            LIMIT 1
            FOR UPDATE
        """, (patient_id, camp_id, doctor_id))

        cancelled_registration = cursor.fetchone()

        if cancelled_registration:
            token_no = cancelled_registration["token_no"]

            cursor.execute("""
                UPDATE registrations
                SET
                    medical_concern = %s,
                    status = 'waiting',
                    registered_at = NOW()
                WHERE registration_id = %s
                AND status = 'cancelled'
            """, (
                medical_concern,
                cancelled_registration["registration_id"]
            ))

        else:
            cursor.execute("""
                SELECT COALESCE(MAX(token_no), 0) + 1 AS next_token
                FROM registrations
                WHERE camp_id = %s
                AND doctor_id = %s
            """, (camp_id, doctor_id))

            token_no = cursor.fetchone()["next_token"]

            cursor.execute("""
                INSERT INTO registrations
                (
                    patient_id,
                    camp_id,
                    doctor_id,
                    medical_concern,
                    token_no,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, 'waiting')
            """, (
                patient_id,
                camp_id,
                doctor_id,
                medical_concern,
                token_no
            ))

        connection.commit()

        flash(
            f"Registration successful! Your queue token is #{token_no}.",
            "success"
        )

        return redirect(url_for("patient_camps.my_registrations"))

    except IntegrityError as e:
        if connection:
            connection.rollback()

        print("Registration integrity error:", repr(e))

        flash(
            "Registration could not be completed due to a database constraint.",
            "danger"
        )
        return redirect(url_for("patient_camps.list_available_camps"))

    except Exception as e:
        if connection:
            connection.rollback()

        print("Camp registration error:", e)
        flash(
            "Unable to complete your registration. Please try again.",
            "danger"
        )
        return redirect(url_for("patient_camps.list_available_camps"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# 3. Display the patient's registrations and token numbers
@patient_camps.route("/patient/my-registrations")
@login_required
@role_required("patient")
def my_registrations():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        refresh_camp_statuses(connection)
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
        SELECT
            r.registration_id,
            r.token_no,
            r.status,
            r.registered_at,
            c.camp_name,
            c.location,
            c.camp_date,
            c.start_time,
            c.end_time,
            c.status AS camp_status,
            hr.record_id

        FROM registrations r

        JOIN patients p
            ON r.patient_id = p.patient_id

        JOIN camps c
            ON r.camp_id = c.camp_id

        LEFT JOIN health_records hr
            ON r.registration_id = hr.registration_id

        WHERE p.user_id = %s

        ORDER BY
            CASE c.status
                WHEN 'ongoing' THEN 1
                WHEN 'upcoming' THEN 2
                WHEN 'completed' THEN 3
                WHEN 'cancelled' THEN 4
            END,
            c.camp_date ASC,
            r.token_no ASC
    """, (session["user_id"],))

        registrations = cursor.fetchall()

        return render_template(
            "my_registrations.html",
            registrations=registrations
        )

    except Exception as e:
        print("Patient registration history error:", e)
        flash("Unable to retrieve your registrations.", "danger")
        return redirect(url_for("dashboard.patient"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

# 4. Cancel a patient's camp registration
@patient_camps.route(
    "/patient/registrations/<int:registration_id>/cancel",
    methods=["POST"]
)
@login_required
@role_required("patient")
def cancel_registration(registration_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()

        # Refresh camp statuses before allowing cancellation
        refresh_camp_statuses(connection)

        cursor = connection.cursor(dictionary=True)

        # Verify ownership and registration status
        cursor.execute("""
            SELECT
                r.registration_id,
                r.status,
                c.status AS camp_status
            FROM registrations r
            JOIN patients p ON r.patient_id = p.patient_id
            JOIN camps c ON r.camp_id = c.camp_id
            WHERE r.registration_id = %s
              AND p.user_id = %s
            FOR UPDATE
        """, (registration_id, session["user_id"]))

        registration = cursor.fetchone()

        if not registration:
            connection.rollback()
            flash("Registration not found.", "danger")
            return redirect(
                url_for("patient_camps.my_registrations")
            )

        if (
            registration["status"] != "waiting"
            or registration["camp_status"] not in ["upcoming", "ongoing"]
        ):
            connection.rollback()
            flash(
                "This registration can no longer be cancelled.",
                "warning"
            )
            return redirect(
                url_for("patient_camps.my_registrations")
            )

        # Cancel the registration
        cursor.execute("""
            UPDATE registrations
            SET status = 'cancelled'
            WHERE registration_id = %s
        """, (registration_id,))

        connection.commit()

        flash(
            "Your camp registration has been cancelled successfully.",
            "success"
        )

    except Exception as e:
        if connection:
            connection.rollback()

        print("Registration cancellation error:", e)
        flash("Unable to cancel your registration.", "danger")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("patient_camps.my_registrations"))