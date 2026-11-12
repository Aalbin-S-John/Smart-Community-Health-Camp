# Smart Community Health Camp Management System

A web-based health camp management system designed to simplify community health camp organization, patient registration, doctor scheduling, consultation management, and health record generation.

## Overview

The system provides separate interfaces for administrators, doctors, and patients. It helps manage the complete workflow of a community health camp, from camp creation and patient registration to medical screening and report generation.

## Key Features

### Admin
- Admin login and dashboard.
- Create, edit, and cancel health camps.
- Create doctor accounts and assign doctors to camps.
- View camp statistics and analytics.
- Monitor camp status and completed checkups.

### Doctor
- Doctor login and personalized dashboard.
- View assigned health camps.
- Access doctor-specific patient queues.
- Manage consultations and record screening measurements.
- Enter specialist-specific medical details.
- Generate patient health reports in PDF format.

### Patient
- Patient registration and login.
- Browse available health camps.
- Register for camps and select medical concerns.
- Receive doctor-specific queue tokens.
- View registration history and status.
- Cancel registrations and register again.
- Access health reports.

## Application Screenshots

### Admin Dashboard
![Admin_Dashboard](screenshots/admin_dashboard.png)

### Camp Management
![Camp_Management](screenshots/camp_management.png)

### Doctor Dashboard
![Doctor_Dashboard](screenshots/doctor_dashboard.png)

### Patient Dashboard
![Patient_Dashboard](screenshots/patient_dashboard.png)

### Health Report
![Health_Report](screenshots/health_report.png)

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Python, Flask |
| Database | MySQL |
| Frontend | HTML, CSS, Bootstrap, JavaScript |
| PDF Generation | ReportLab |
| Data Visualization | Chart.js |
| Security | Flask-WTF CSRF Protection, Role-Based Access Control |

## Project Structure

- `app.py` – Flask application entry point.
- `config.py` – Application configuration.
- `db.py` – Database connection.
- `routes/` – Application routes and business logic.
- `templates/` – HTML templates.
- `utils/` – Utility functions.
- `requirements.txt` – Python dependencies.
- `schema.sql` – MySQL database structure.

## Getting Started

### Prerequisites

- Python 3.x
- MySQL Server
- Git

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Aalbin-S-John/Smart-Community-Health-Camp.git
   cd Smart-Community-Health-Camp
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   ```

   On Windows:

   ```bash
   venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create the MySQL database:

   ```sql
   CREATE DATABASE smart_health_camp;
   ```

5. Import the database structure:

   ```bash
   mysql -u root -p smart_health_camp < schema.sql
   ```

6. Create a `.env` file in the project root:

   ```env
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=smart_health_camp
   SECRET_KEY=your_secret_key
   ```

7. Create the Admin Account

   After configuring the `.env` file and importing the database schema, run:

   ```bash
   python create_admin.py
   ```

   Enter the admin username, email, and password when prompted.

   The password is securely hashed before being stored in the database.

8. Run the application:

   ```bash
   python app.py
   ```

9. Open the application in your browser:

   ```text
   http://127.0.0.1:5000
   ```

## Security Notes

- Database credentials and secret keys are stored in environment variables.
- Sensitive configuration files and virtual environments are excluded through `.gitignore`.
- Role-based access controls restrict features according to user roles.
- CSRF protection is enabled for applicable forms.

## Future Enhancements

- QR-based patient registration and queue management.
- Email and SMS notifications.
- Location-based camp discovery.
- Multilingual support.
- Data export and expanded analytics.

## Author

**Aalbin S. John**

GitHub: https://github.com/Aalbin-S-John

---

*Developed as a community health camp management project using Flask and MySQL.*