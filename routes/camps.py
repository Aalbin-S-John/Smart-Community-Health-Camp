
from flask import Blueprint, render_template, request
from flask import redirect, url_for, flash, session

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from db import get_db_connection
from utils.decorators import login_required, role_required
from utils.camp_status import refresh_camp_statuses

camps = Blueprint("camps", __name__)


# VIEW ALL CAMPS
@camps.route("/admin/camps")
@login_required
@role_required("admin")
def list_camps():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()

        # Automatically refresh camp statuses
        refresh_camp_statuses(connection)

        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                c.*,
                COUNT(DISTINCT cd.doctor_id) AS doctor_count,
                COUNT(DISTINCT r.registration_id) AS registered_count
            FROM camps c
            LEFT JOIN camp_doctors cd
                ON c.camp_id = cd.camp_id
            LEFT JOIN registrations r
                ON c.camp_id = r.camp_id
            GROUP BY c.camp_id
            ORDER BY c.camp_date DESC
        """)

        camp_list = cursor.fetchall()

        return render_template(
            "camps.html",
            camps=camp_list
        )

    except Exception:
        flash("Unable to retrieve health camps.", "danger")
        return redirect(url_for("dashboard.admin"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# CREATE A NEW CAMP
@camps.route("/admin/camps/create", methods=["GET", "POST"])
@login_required
@role_required("admin")
def create_camp():

    if request.method == "POST":

        camp_name = request.form.get("camp_name", "").strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        camp_date = request.form.get("camp_date", "")
        start_time = request.form.get("start_time") or None
        end_time = request.form.get("end_time") or None

        capacity = request.form.get("capacity", "")
        budget = request.form.get("estimated_budget", "0")

        try:
            if not all([camp_name, location, camp_date, capacity]):
                raise ValueError("Please fill all required fields.")

            selected_date = date.fromisoformat(camp_date)

            if selected_date < date.today():
                raise ValueError("Camp date cannot be in the past.")

            capacity = int(capacity)
            budget = Decimal(budget)

            if capacity <= 0:
                raise ValueError("Capacity must be greater than zero.")

            if not budget.is_finite() or budget < 0 or budget > Decimal("99999999.99"):
                raise ValueError("Enter a valid budget in INR.")

            if start_time and end_time:
                start = datetime.strptime(start_time, "%H:%M").time()
                end = datetime.strptime(end_time, "%H:%M").time()

                if end <= start:
                    raise ValueError("End time must be later than start time.")

        except (ValueError, InvalidOperation) as e:
            print("CAMP VALIDATION ERROR:", repr(e))
            flash(f"Validation error: {e}", "danger")
            return render_template("create_camp.html")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute("""
                INSERT INTO camps
                (
                    camp_name,
                    description,
                    location,
                    city,
                    state,
                    country,
                    camp_date,
                    start_time,
                    end_time,
                    capacity,
                    estimated_budget,
                    created_by
                )
                VALUES (%s, %s, %s, 'Bengaluru',
                        'Karnataka', 'India', %s, %s, %s,
                        %s, %s, %s)
            """, (
                camp_name,
                description,
                location,
                selected_date,
                start_time,
                end_time,
                capacity,
                budget,
                session["user_id"]
            ))

            connection.commit()

            flash("Health camp created successfully!", "success")

            return redirect(url_for("camps.list_camps"))

        except Exception:
            if connection:
                connection.rollback()

            flash("Unable to create health camp.", "danger")

        finally:
            if cursor:
                cursor.close()

            if connection and connection.is_connected():
                connection.close()

    return render_template("create_camp.html")



# EDIT AN EXISTING CAMP
@camps.route("/admin/camps/<int:camp_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_camp(camp_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the camp
        cursor.execute("""
            SELECT *
            FROM camps
            WHERE camp_id = %s
        """, (camp_id,))

        camp = cursor.fetchone()

        if not camp:
            flash("Health camp not found.", "danger")
            return redirect(url_for("camps.list_camps"))

        if camp["status"] in ("cancelled", "completed"):
            flash("Cancelled or completed camps cannot be edited.", "warning")
            return redirect(url_for("camps.list_camps"))

        if request.method == "POST":

            camp_name = request.form.get("camp_name", "").strip()
            description = request.form.get("description", "").strip()
            location = request.form.get("location", "").strip()
            camp_date = request.form.get("camp_date", "")
            start_time = request.form.get("start_time") or None
            end_time = request.form.get("end_time") or None
            capacity = request.form.get("capacity", "")
            budget = request.form.get("estimated_budget", "0")

            try:
                if not all([camp_name, location, camp_date, capacity]):
                    raise ValueError

                selected_date = date.fromisoformat(camp_date)

                if selected_date < date.today():
                    raise ValueError

                capacity = int(capacity)
                budget = Decimal(budget)

                if capacity <= 0:
                    raise ValueError

                if not budget.is_finite() or budget < 0 or budget > Decimal("99999999.99"):
                    raise ValueError

                if start_time and end_time:
                    start = datetime.strptime(start_time[:5], "%H:%M").time()
                    end = datetime.strptime(end_time[:5], "%H:%M").time()

                    if end <= start:
                        raise ValueError("End time must be after start time.")

            except (ValueError, InvalidOperation) as e:
                print("EDIT VALIDATION ERROR:", repr(e))
                flash(f"Validation error: {e}", "danger")
                return render_template("edit_camp.html", camp=camp)

            # Prevent capacity from going below active registrations
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM registrations
                WHERE camp_id = %s
                  AND status != 'cancelled'
            """, (camp_id,))

            registered_count = cursor.fetchone()["total"]

            if capacity < registered_count:
                flash(
                    f"Capacity cannot be less than {registered_count} active registrations.",
                    "danger"
                )
                return render_template("edit_camp.html", camp=camp)

            cursor.execute("""
                UPDATE camps
                SET
                    camp_name = %s,
                    description = %s,
                    location = %s,
                    camp_date = %s,
                    start_time = %s,
                    end_time = %s,
                    capacity = %s,
                    estimated_budget = %s
                WHERE camp_id = %s
                  AND status NOT IN ('cancelled', 'completed')
            """, (
                camp_name,
                description,
                location,
                selected_date,
                start_time,
                end_time,
                capacity,
                budget,
                camp_id
            ))

            connection.commit()

            flash("Health camp updated successfully!", "success")
            return redirect(url_for("camps.list_camps"))

        return render_template("edit_camp.html", camp=camp)

    except Exception as e:
        if connection:
            connection.rollback()

        print("Edit camp error:", e)
        flash("Unable to edit health camp.", "danger")
        return redirect(url_for("camps.list_camps"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()



# CANCEL A CAMP
@camps.route("/admin/camps/<int:camp_id>/cancel", methods=["POST"])
@login_required
@role_required("admin")
def cancel_camp(camp_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE camps
            SET status = 'cancelled'
            WHERE camp_id = %s
            AND status = 'upcoming'
            AND camp_date >= CURDATE()
        """, (camp_id,))

        if cursor.rowcount == 1:

            # Cancel patients who are still waiting
            cursor.execute("""
                UPDATE registrations
                SET status = 'cancelled'
                WHERE camp_id = %s
                AND status = 'waiting'
            """, (camp_id,))

            connection.commit()

            flash("Health camp and waiting registrations cancelled successfully.", "success")

        else:
            connection.rollback()
            flash("This camp cannot be cancelled.", "warning")

    except Exception:
        if connection:
            connection.rollback()

        flash("Unable to cancel the health camp.", "danger")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("camps.list_camps"))
