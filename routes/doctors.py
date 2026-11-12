from flask import Blueprint, render_template, request
from flask import redirect, url_for, flash

from werkzeug.security import generate_password_hash
from mysql.connector import IntegrityError

from db import get_db_connection
from utils.decorators import login_required, role_required

doctors = Blueprint("doctors", __name__)


# 1. Display all doctors
@doctors.route("/admin/doctors")
@login_required
@role_required("admin")
def list_doctors():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                d.doctor_id,
                d.full_name,
                d.specialization,
                d.phone,
                u.email,
                u.username
            FROM doctors d
            JOIN users u ON d.user_id = u.user_id
            ORDER BY d.full_name
        """)

        doctor_list = cursor.fetchall()

        return render_template(
            "doctors.html",
            doctors=doctor_list
        )

    except Exception as e:
        print("Doctor list error:", e)
        flash("Unable to retrieve doctors.", "danger")
        return redirect(url_for("dashboard.admin"))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# 2. Create a doctor account
@doctors.route("/admin/doctors/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def create_doctor():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        specialization = request.form.get("specialization", "").strip()
        phone = request.form.get("phone", "").strip()

        if not all([username, email, password, full_name]):
            flash("Please fill in all required fields.", "danger")
            return render_template("create_doctor.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return render_template("create_doctor.html")

        if phone and (not phone.isdigit() or len(phone) != 10):
            flash("Enter a valid 10-digit Indian mobile number.", "danger")
            return render_template("create_doctor.html")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            password_hash = generate_password_hash(password)

            # Create the login account
            cursor.execute("""
                INSERT INTO users
                (username, email, password_hash, role)
                VALUES (%s, %s, %s, 'doctor')
            """, (username, email, password_hash))

            user_id = cursor.lastrowid

            # Create the doctor profile
            cursor.execute("""
                INSERT INTO doctors
                (user_id, full_name, specialization, phone)
                VALUES (%s, %s, %s, %s)
            """, (user_id, full_name, specialization, phone))

            connection.commit()

            flash("Doctor account created successfully!", "success")
            return redirect(url_for("doctors.list_doctors"))

        except IntegrityError:
            if connection:
                connection.rollback()

            flash(
                "Username or email already exists. Please use different details.",
                "danger"
            )

        except Exception as e:
            if connection:
                connection.rollback()

            print("Doctor creation error:", e)
            flash("Unable to create doctor account.", "danger")

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("create_doctor.html")


# 3. Assign doctors to a health camp
@doctors.route(
    "/admin/camps/<int:camp_id>/assign-doctors",
    methods=["GET", "POST"]
)
@login_required
@role_required("admin")
def assign_doctors(camp_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Check whether the camp exists and can receive assignments
        cursor.execute("""
            SELECT *
            FROM camps
            WHERE camp_id = %s
              AND status = 'upcoming'
              AND camp_date >= CURDATE()
        """, (camp_id,))

        camp = cursor.fetchone()

        if not camp:
            flash("Camp not found or no longer available for assignment.", "warning")
            return redirect(url_for("camps.list_camps"))

        if request.method == "POST":

            selected_ids = request.form.getlist("doctor_ids")
            # Retrieve and validate patient limits
            patient_limits = {}

            try:
                for doctor_id in selected_ids:
                    limit = int(request.form.get(
                        f"patient_limit_{doctor_id}", 10
                    ))

                    if limit < 1:
                        raise ValueError

                    patient_limits[int(doctor_id)] = limit

            except (ValueError, TypeError):
                flash("Patient limits must be positive whole numbers.", "danger")
                return redirect(
                    url_for("doctors.assign_doctors", camp_id=camp_id)
                )

            # Convert submitted IDs into integers
            try:
                selected_ids = list(set(int(x) for x in selected_ids))
            except ValueError:
                flash("Invalid doctor selection.", "danger")
                return redirect(
                    url_for("doctors.assign_doctors", camp_id=camp_id)
                )

            if selected_ids:
                placeholders = ", ".join(["%s"] * len(selected_ids))

                cursor.execute(
                    f"""
                    SELECT doctor_id
                    FROM doctors
                    WHERE doctor_id IN ({placeholders})
                    """,
                    tuple(selected_ids)
                )

                valid_ids = {
                    row["doctor_id"] for row in cursor.fetchall()
                }

                if valid_ids != set(selected_ids):
                    flash("One or more selected doctors do not exist.", "danger")
                    return redirect(
                        url_for("doctors.assign_doctors", camp_id=camp_id)
                    )

                # Check whether any selected doctor has an overlapping camp
                for doctor_id in selected_ids:

                    cursor.execute("""
                        SELECT
                            c.camp_id,
                            c.camp_name,
                            c.start_time,
                            c.end_time,
                            d.full_name
                        FROM camp_doctors cd
                        JOIN camps c ON cd.camp_id = c.camp_id
                        JOIN doctors d ON cd.doctor_id = d.doctor_id
                        WHERE cd.doctor_id = %s
                        AND c.camp_id != %s
                        AND c.status != 'cancelled'
                        AND c.camp_date = %s
                        AND TIMESTAMP(
                            c.camp_date,
                            COALESCE(c.start_time, '00:00:00')
                        ) < TIMESTAMP(%s, %s)
                        AND TIMESTAMP(
                            c.camp_date,
                            COALESCE(c.end_time, '23:59:59')
                        ) > TIMESTAMP(%s, %s)
                    """, (
                        doctor_id,
                        camp_id,
                        camp["camp_date"],
                        camp["camp_date"],
                        camp["end_time"],
                        camp["camp_date"],
                        camp["start_time"]
                    ))

                    conflict = cursor.fetchone()

                    if conflict:
                        connection.rollback()
                        flash(
                            f"Dr. {conflict['full_name']} is already assigned to "
                            f"{conflict['camp_name']} during this time.",
                            "danger"
                        )
                        return redirect(
                            url_for("doctors.assign_doctors", camp_id=camp_id)
                        )

            # Replace the camp's existing doctor assignments
            cursor.execute("""
                DELETE FROM camp_doctors
                WHERE camp_id = %s
            """, (camp_id,))

            for doctor_id in selected_ids:
                cursor.execute("""
                    INSERT INTO camp_doctors
                        (camp_id, doctor_id, patient_limit)
                    VALUES (%s, %s, %s)
                """, (
                    camp_id,
                    doctor_id,
                    patient_limits[doctor_id]
                ))

            connection.commit()

            flash("Doctors assigned to the camp successfully!", "success")
            return redirect(url_for("camps.list_camps"))

        # Retrieve all doctors
        cursor.execute("""
            SELECT
                d.doctor_id,
                d.full_name,
                d.specialization,
                COALESCE(cd.patient_limit, 10) AS patient_limit
            FROM doctors d
            LEFT JOIN camp_doctors cd
                ON d.doctor_id = cd.doctor_id
                AND cd.camp_id = %s
            ORDER BY d.full_name
        """, (camp_id,))

        doctor_list = cursor.fetchall()

        # Retrieve doctors already assigned to this camp
        cursor.execute("""
            SELECT doctor_id
            FROM camp_doctors
            WHERE camp_id = %s
        """, (camp_id,))

        assigned_ids = [
            row["doctor_id"] for row in cursor.fetchall()
        ]

        return render_template(
            "assign_doctors.html",
            camp=camp,
            doctors=doctor_list,
            assigned_ids=assigned_ids
        )

    except Exception as e:
        if connection:
            connection.rollback()

        print("Doctor assignment error:", e)
        flash("Unable to process doctor assignments.", "danger")
        return redirect(url_for("camps.list_camps"))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()