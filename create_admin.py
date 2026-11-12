
from getpass import getpass
from werkzeug.security import generate_password_hash
from db import get_db_connection

username = input("Enter admin username: ").strip()
email = input("Enter admin email: ").strip().lower()
password = getpass("Enter admin password: ")

if not username or not email or len(password) < 8:
    print("Invalid details. Password must have at least 8 characters.")
else:
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO users
            (username, email, password_hash, role)
            VALUES (%s, %s, %s, 'admin')
        """, (username, email, password_hash))

        connection.commit()

        print("Admin account created successfully!")

    except Exception as e:
        if connection:
            connection.rollback()
        print("Error:", e)

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
