
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import IntegrityError
from db import get_db_connection

auth = Blueprint("auth", __name__)


# PATIENT REGISTRATION
@auth.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        dob = request.form.get("dob") or None
        gender = request.form.get("gender", "")
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        if not all([username, email, password, full_name]):
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
            return render_template("register.html")

        password_hash = generate_password_hash(password)

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            # Insert user
            cursor.execute("""
                INSERT INTO users
                (username, email, password_hash, role)
                VALUES (%s, %s, %s, 'patient')
            """, (username, email, password_hash))

            user_id = cursor.lastrowid

            # Insert patient profile
            cursor.execute("""
                INSERT INTO patients
                (user_id, full_name, date_of_birth,
                 gender, phone, address)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, full_name, dob,
                  gender, phone, address))

            connection.commit()

            flash("Registration successful! Please login.", "success")
            return redirect(url_for("auth.login"))

        except IntegrityError:
            if connection:
                connection.rollback()

            flash("Username or email already exists.", "danger")

        except Exception:
            if connection:
                connection.rollback()

            flash("Registration failed. Please try again.", "danger")

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("register.html")


# USER LOGIN
@auth.route("/login", methods=["GET", "POST"])
def login():

    if "user_id" in session:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT user_id, username, email,
                       password_hash, role
                FROM users
                WHERE email = %s
            """, (email,))

            user = cursor.fetchone()

            if user and check_password_hash(
                user["password_hash"], password
            ):

                session.clear()

                session["user_id"] = user["user_id"]
                session["username"] = user["username"]
                session["role"] = user["role"]

                flash("Login successful!", "success")

                return redirect(url_for("dashboard.home"))

            flash("Invalid email or password.", "danger")

        except Exception:
            flash("Unable to login. Please try again.", "danger")

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("login.html")


# USER LOGOUT
@auth.route("/logout", methods=["POST"])
def logout():

    session.clear()

    flash("You have been logged out.", "info")

    return redirect(url_for("auth.login"))