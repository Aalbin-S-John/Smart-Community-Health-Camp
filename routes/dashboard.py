
from mysql.connector import abstracts
from mysql.connector import abstracts
from flask import Blueprint, render_template, session, redirect, url_for, flash
from db import get_db_connection
from utils.decorators import login_required, role_required
from utils.camp_status import refresh_camp_statuses

dashboard = Blueprint("dashboard", __name__)


# Redirect users according to their roles
@dashboard.route("/dashboard")
@login_required
def home():

    role = session.get("role")

    if role == "admin":
        return redirect(url_for("dashboard.admin"))

    elif role == "doctor":
        return redirect(url_for("dashboard.doctor"))

    elif role == "patient":
        return redirect(url_for("dashboard.patient"))

    return redirect(url_for("auth.logout"))


# ADMIN DASHBOARD

@dashboard.route("/admin")
@login_required
@role_required("admin")
def admin():

    connection = None
    cursor = None

    stats = {
        "total_patients": 0,
        "total_doctors": 0,
        "total_camps": 0,
        "upcoming_camps": 0,
        "ongoing_camps": 0,
        "completed_camps": 0,
        "cancelled_camps": 0,
        "completed_checkups": 0
    }
    try:
        connection = get_db_connection()
        refresh_camp_statuses(connection)
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM patients
        """)
        stats["total_patients"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM doctors
        """)
        stats["total_doctors"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM camps
        """)
        stats["total_camps"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM camps
            WHERE camp_date >= CURDATE()
            AND status = 'upcoming'
        """)
        stats["upcoming_camps"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM camps
            WHERE status = 'completed'
        """)
        stats["completed_camps"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM camps
            WHERE status = 'ongoing'
        """)
        stats["ongoing_camps"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM camps
            WHERE status = 'cancelled'
        """)
        stats["cancelled_camps"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM registrations
            WHERE status = 'completed'
        """)
        stats["completed_checkups"] = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT camp_name, location, city, state,
                camp_date, estimated_budget, status
            FROM camps
            ORDER BY camp_date DESC
            LIMIT 5
        """)

        recent_camps = cursor.fetchall()

        return render_template(
            "admin_dashboard.html",
            stats=stats,
            recent_camps=recent_camps
        )

    except Exception:
        flash("Unable to load dashboard information.", "danger")
        return render_template(
            "admin_dashboard.html",
            stats=stats,
            recent_camps=[]
        )

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()



# DOCTOR DASHBOARD
@dashboard.route("/doctor")
@login_required
@role_required("doctor")
def doctor():
    return redirect(url_for("doctor_work.my_camps"))


# PATIENT DASHBOARD
@dashboard.route("/patient")
@login_required
@role_required("patient")
def patient():

    return render_template(
        "dashboard.html",
        title="Patient Dashboard",
        role="Patient"
    )


@dashboard.route("/admin/analytics")
@login_required
@role_required("admin")
def admin_analytics():

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # 1. Monthly patient registrations (last 6 months)
        cursor.execute("""
            SELECT
                YEAR(registered_at) AS reg_year,
                MONTH(registered_at) AS reg_month,
                DATE_FORMAT(MIN(registered_at), '%b %Y') AS month_label,
                COUNT(*) AS total
            FROM registrations
            WHERE registered_at >= DATE_FORMAT(
                DATE_SUB(CURDATE(), INTERVAL 5 MONTH),
                '%Y-%m-01'
            )
            GROUP BY YEAR(registered_at), MONTH(registered_at)
            ORDER BY reg_year, reg_month
        """)
        monthly_data = cursor.fetchall()

        # 2. Registration status distribution
        cursor.execute("""
            SELECT
                status,
                COUNT(*) AS total
            FROM registrations
            GROUP BY status
        """)
        status_data = cursor.fetchall()

        # 3. Top 5 camps by registrations
        cursor.execute("""
            SELECT
                c.camp_name,
                COUNT(r.registration_id) AS total
            FROM camps c
            LEFT JOIN registrations r
                ON c.camp_id = r.camp_id
            GROUP BY c.camp_id, c.camp_name
            ORDER BY total DESC
            LIMIT 5
        """)
        top_camps = cursor.fetchall()

        return render_template(
            "admin_analytics.html",
            monthly_data=monthly_data,
            status_data=status_data,
            top_camps=top_camps
        )

    except Exception as e:
        print("Analytics Dashboard Error:", e)
        flash("Unable to load analytics information.", "danger")
        return redirect(url_for("dashboard.admin"))

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()
