from flask import Blueprint, render_template, request
from flask import redirect, url_for, flash, session

from decimal import Decimal, InvalidOperation

from db import get_db_connection
from utils.decorators import login_required, role_required
from utils.camp_status import refresh_camp_statuses

import json

doctor_work = Blueprint("doctor_work", __name__)


# Get the logged-in doctor's profile ID
def get_doctor_id(cursor):
    cursor.execute("""
        SELECT doctor_id
        FROM doctors
        WHERE user_id = %s
    """, (session["user_id"],))

    doctor = cursor.fetchone()

    return doctor["doctor_id"] if doctor else None


# 1. Doctor dashboard: show assigned camps
@doctor_work.route("/doctor/camps")
@login_required
@role_required("doctor")
def my_camps():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        refresh_camp_statuses(connection)
        cursor = connection.cursor(dictionary=True)

        doctor_id = get_doctor_id(cursor)

        if not doctor_id:
            flash("Doctor profile not found.", "danger")
            return redirect(url_for("auth.logout"))

        cursor.execute("""
            SELECT
                c.camp_id,
                c.camp_name,
                c.location,
                c.camp_date,
                c.start_time,
                c.end_time,
                c.capacity,
                c.status,

                COUNT(
                    CASE
                        WHEN r.status <> 'cancelled'
                        THEN r.registration_id
                    END
                ) AS registered_count,

                COUNT(
                    CASE
                        WHEN r.status = 'waiting'
                        THEN r.registration_id
                    END
                ) AS waiting_count

            FROM camp_doctors cd

            JOIN camps c
                ON cd.camp_id = c.camp_id

            LEFT JOIN registrations r
                ON c.camp_id = r.camp_id
                AND r.doctor_id = cd.doctor_id

            WHERE cd.doctor_id = %s

            GROUP BY c.camp_id

            ORDER BY
                CASE c.status
                    WHEN 'ongoing' THEN 1
                    WHEN 'upcoming' THEN 2
                    WHEN 'completed' THEN 3
                    WHEN 'cancelled' THEN 4
                END,
                c.camp_date ASC
        """, (doctor_id,))

        camp_list = cursor.fetchall()

        return render_template(
            "doctor_camps.html",
            camps=camp_list
        )

    except Exception as e:
        print("Doctor dashboard error:", e)
        flash("Unable to load assigned camps.", "danger")
        return redirect(url_for("dashboard.home"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# 2. View the patient queue for an assigned camp
@doctor_work.route("/doctor/camps/<int:camp_id>/queue")
@login_required
@role_required("doctor")
def camp_queue(camp_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        refresh_camp_statuses(connection)
        cursor = connection.cursor(dictionary=True)

        doctor_id = get_doctor_id(cursor)

        if not doctor_id:
            flash("Doctor profile not found.", "danger")
            return redirect(url_for("auth.logout"))

        # Verify that this doctor is assigned to the camp
        cursor.execute("""
            SELECT c.*
            FROM camps c
            JOIN camp_doctors cd
                ON c.camp_id = cd.camp_id
            WHERE c.camp_id = %s
              AND cd.doctor_id = %s
        """, (camp_id, doctor_id))

        camp = cursor.fetchone()

        if not camp:
            flash("You are not assigned to this camp.", "danger")
            return redirect(url_for("doctor_work.my_camps"))

        cursor.execute("""
            SELECT
                r.registration_id,
            r.token_no,
            r.status,
            p.full_name,
            p.phone,
            hr.record_id,
            hr.doctor_id AS screening_doctor_id
            FROM registrations r
            JOIN patients p
                ON r.patient_id = p.patient_id
            LEFT JOIN health_records hr
                ON r.registration_id = hr.registration_id
            WHERE r.camp_id = %s
                AND r.doctor_id = %s
            ORDER BY r.token_no
        """, (camp_id, doctor_id))

        patients = cursor.fetchall()

        return render_template(
            "doctor_queue.html",
            camp=camp,
            patients=patients,
            doctor_id=doctor_id
        )

    except Exception as e:
        print("Patient queue error:", e)
        flash("Unable to load the patient queue.", "danger")
        return redirect(url_for("doctor_work.my_camps"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# 3. Start a patient's consultation
@doctor_work.route(
    "/doctor/registration/<int:registration_id>/start",
    methods=["POST"]
)
@login_required
@role_required("doctor")
def start_consultation(registration_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        doctor_id = get_doctor_id(cursor)

        if not doctor_id:
            flash("Doctor profile not found.", "danger")
            return redirect(url_for("auth.logout"))

        # Only allow a doctor assigned to the patient's camp
        # Only allow the doctor assigned to this specific registration
        cursor.execute("""
            SELECT
                r.camp_id,
                r.status,
                c.camp_date,
                c.start_time,
                c.end_time
            FROM registrations r
            JOIN camps c ON r.camp_id = c.camp_id
            WHERE r.registration_id = %s
            AND r.doctor_id = %s
            AND c.status != 'cancelled'
        """, (registration_id, doctor_id))

        registration = cursor.fetchone()
        print("START CONSULTATION ROUTE CALLED")

        if not registration:
            flash("You are not authorized to access this registration.", "danger")
            return redirect(url_for("doctor_work.my_camps"))

        cursor.execute("""
            SELECT
                (
                    NOW() >= TIMESTAMP(
                        camp_date,
                        COALESCE(start_time, '00:00:00')
                    )
                    AND
                    NOW() <= TIMESTAMP(
                        camp_date,
                        COALESCE(end_time, '23:59:59')
                    )
                ) AS is_active
            FROM camps
            WHERE camp_id = %s
        """, (registration["camp_id"],))

        camp_timing = cursor.fetchone()

        if not camp_timing or not camp_timing["is_active"]:
            flash(
                "Consultations can only start during the camp's scheduled hours.",
                "warning"
            )
            return redirect(url_for(
                "doctor_work.camp_queue",
                camp_id=registration["camp_id"]
            ))

        if registration["status"] != "waiting":
            flash("This patient is not waiting for consultation.", "warning")
        else:
            cursor.execute("""
                UPDATE registrations
                SET status = 'in_progress'
                WHERE registration_id = %s
                  AND status = 'waiting'
            """, (registration_id,))

            connection.commit()

            if cursor.rowcount == 1:
                flash("Consultation started.", "success")
            else:
                flash("Unable to start this consultation.", "warning")

        return redirect(url_for(
            "doctor_work.camp_queue",
            camp_id=registration["camp_id"]
        ))

    except Exception as e:
        if connection:
            connection.rollback()

        print("Start consultation error:", e)
        flash("Unable to start the consultation.", "danger")
        return redirect(url_for("doctor_work.my_camps"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# 4. Enter and save health screening measurements
@doctor_work.route(
    "/doctor/registration/<int:registration_id>/screening",
    methods=["GET", "POST"]
)
@login_required
@role_required("doctor")
def record_screening(registration_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        doctor_id = get_doctor_id(cursor)

        specialist_fields_map = {
            "General Physician": [
                ("general_symptoms", "General Symptoms"),
                ("clinical_findings", "Clinical Findings")
            ],
            "Cardiologist": [
                ("pulse_rate", "Pulse Rate (beats/min)"),
                ("heart_symptoms", "Heart-related Symptoms")
            ],
            "Dermatologist": [
                ("affected_area", "Affected Skin Area"),
                ("skin_condition", "Skin Condition / Findings")
            ],
            "Ophthalmologist": [
                ("right_eye_vision", "Right Eye Visual Acuity"),
                ("left_eye_vision", "Left Eye Visual Acuity"),
                ("vision_complaints", "Vision Complaints")
            ],
            "Paediatrician": [
                ("growth_observations", "Growth Observations"),
                ("developmental_observations", "Developmental Observations")
            ],
            "Gynaecologist": [
                ("relevant_symptoms", "Relevant Symptoms"),
                ("examination_findings", "Examination Findings")
            ],
            "Dentist": [
                ("affected_tooth", "Affected Tooth / Area"),
                ("oral_condition", "Oral Condition"),
                ("dental_findings", "Dental Findings")
            ],
            "Other": [
                ("specialist_findings", "Specialist Findings")
            ]
        }

        if not doctor_id:
            flash("Doctor profile not found.", "danger")
            return redirect(url_for("auth.logout"))

        # Verify doctor assignment and retrieve patient details
        cursor.execute("""
            SELECT
                r.registration_id,
                r.camp_id,
                r.token_no,
                r.status,
                p.full_name,
                d.specialization,
                c.camp_name,
                c.camp_date,
                c.start_time,
                c.end_time

            FROM registrations r

            JOIN patients p
                ON r.patient_id = p.patient_id

            JOIN doctors d
                ON r.doctor_id = d.doctor_id

            JOIN camps c
                ON r.camp_id = c.camp_id

            WHERE r.registration_id = %s
            AND r.doctor_id = %s
        """, (registration_id, doctor_id))

        registration = cursor.fetchone()

        if not registration:
            flash("You are not authorized to access this patient.", "danger")
            return redirect(url_for("doctor_work.my_camps"))

        specialist_fields = specialist_fields_map.get(
            registration["specialization"],
            specialist_fields_map["Other"]
        )

        # Check whether the camp is currently active
        cursor.execute("""
            SELECT
                (
                    NOW() >= TIMESTAMP(
                        camp_date,
                        COALESCE(start_time, '00:00:00')
                    )
                    AND
                    NOW() <= TIMESTAMP(
                        camp_date,
                        COALESCE(end_time, '23:59:59')
                    )
                ) AS is_active
            FROM camps
            WHERE camp_id = %s
            AND status != 'cancelled'
        """, (registration["camp_id"],))

        camp_timing = cursor.fetchone()

        if not camp_timing or not camp_timing["is_active"]:
            flash(
                "Screening is available only during the camp's scheduled hours.",
                "warning"
            )
            return redirect(url_for(
                "doctor_work.camp_queue",
                camp_id=registration["camp_id"]
            ))

        if registration["status"] != "in_progress":
            flash(
                "Please start the consultation before recording screening measurements.",
                "warning"
            )
            return redirect(url_for(
                "doctor_work.camp_queue",
                camp_id=registration["camp_id"]
            ))

        # Prevent a second screening record for the same registration
        cursor.execute("""
            SELECT record_id
            FROM health_records
            WHERE registration_id = %s
        """, (registration_id,))

        if cursor.fetchone():
            flash("A screening record already exists for this registration.", "warning")
            return redirect(url_for(
                "doctor_work.camp_queue",
                camp_id=registration["camp_id"]
            ))

        if request.method == "POST":

            try:
                systolic_bp = Decimal(request.form.get("systolic_bp", "").strip())
                diastolic_bp = Decimal(request.form.get("diastolic_bp", "").strip())
                blood_sugar = Decimal(request.form.get("blood_sugar", "").strip())
                temperature = Decimal(request.form.get("temperature", "").strip())
                weight = Decimal(request.form.get("weight", "").strip())
                height = Decimal(request.form.get("height", "").strip())

                observations = request.form.get("observations", "").strip()

                values = [
                    systolic_bp,
                    diastolic_bp,
                    blood_sugar,
                    temperature,
                    weight,
                    height
                ]

                if not all(value.is_finite() for value in values):
                    raise ValueError("Enter valid numeric measurements.")

                if not (
                    Decimal("1") <= systolic_bp <= Decimal("300")
                    and Decimal("1") <= diastolic_bp <= Decimal("200")
                    and Decimal("1") <= blood_sugar <= Decimal("2000")
                    and Decimal("25") <= temperature <= Decimal("45")
                    and Decimal("0.1") <= weight <= Decimal("500")
                    and Decimal("20") <= height <= Decimal("250")
                ):
                    raise ValueError("One or more measurements are outside the accepted input limits.")

            except (ValueError, InvalidOperation):
                flash("Please enter valid screening measurements.", "danger")

                return render_template(
                    "screening.html",
                    registration=registration,
                    specialist_fields = specialist_fields
                )

            specialist_data = {}

            for field_name, field_label in specialist_fields:
                value = request.form.get(field_name, "").strip()

                if value:
                    specialist_data[field_name] = value

            specialist_details = (
                json.dumps(specialist_data)
                if specialist_data
                else None
            )

            # Save screening and complete registration together
            cursor.execute("""
                INSERT INTO health_records
                (
                    registration_id,
                    doctor_id,
                    systolic_bp,
                    diastolic_bp,
                    blood_sugar,
                    temperature,
                    weight,
                    height,
                    observations,
                    specialist_details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                registration_id,
                doctor_id,
                systolic_bp,
                diastolic_bp,
                blood_sugar,
                temperature,
                weight,
                height,
                observations,
                specialist_details
            ))

            cursor.execute("""
                UPDATE registrations
                SET status = 'completed'
                WHERE registration_id = %s
                  AND status IN ('waiting', 'in_progress')
            """, (registration_id,))

            if cursor.rowcount != 1:
                connection.rollback()
                flash("Registration status changed. Please check the queue.", "warning")
                return redirect(url_for(
                    "doctor_work.camp_queue",
                    camp_id=registration["camp_id"]
                ))

            connection.commit()

            flash("Health screening record saved successfully.", "success")

            return redirect(url_for(
                "doctor_work.camp_queue",
                camp_id=registration["camp_id"]
            ))

        return render_template(
            "screening.html",
            registration=registration,
            specialist_fields = specialist_fields
        )

    except Exception as e:
        if connection:
            connection.rollback()

        print("Screening record error:", e)
        flash("Unable to save the screening record.", "danger")
        return redirect(url_for("doctor_work.my_camps"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()