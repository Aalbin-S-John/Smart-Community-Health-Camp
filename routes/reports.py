import json

from flask import Blueprint, send_file, flash, redirect, url_for, session
from flask import abort

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

from db import get_db_connection
from utils.decorators import login_required, role_required


reports = Blueprint("reports", __name__)


@reports.route(
    "/reports/<int:record_id>/download",
    methods=["POST"]
)
@login_required
@role_required("admin", "doctor", "patient")
def download_report(record_id):

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Retrieve the screening record and related information
        cursor.execute("""
            SELECT
                hr.record_id,
                hr.systolic_bp,
                hr.diastolic_bp,
                hr.blood_sugar,
                hr.temperature,
                hr.weight,
                hr.height,
                hr.observations,
                hr.specialist_details,
                hr.recorded_at,

                p.patient_id,
                p.user_id AS patient_user_id,
                p.full_name,
                p.date_of_birth,
                p.gender,
                p.phone,
                p.address,

                d.doctor_id,
                d.user_id AS doctor_user_id,
                d.full_name AS doctor_name,
                d.specialization,

                c.camp_id,
                c.camp_name,
                c.location,
                c.city,
                c.state,
                c.camp_date,

                r.registration_id,
                r.token_no,
                r.status

            FROM health_records hr

            JOIN registrations r
                ON hr.registration_id = r.registration_id

            JOIN patients p
                ON r.patient_id = p.patient_id

            JOIN doctors d
                ON hr.doctor_id = d.doctor_id

            JOIN camps c
                ON r.camp_id = c.camp_id

            WHERE hr.record_id = %s
        """, (record_id,))

        record = cursor.fetchone()

        # Safely read specialist-specific screening details
        try:
            specialist_details = (
                json.loads(record["specialist_details"])
                if record and record["specialist_details"]
                else {}
            )
        except (json.JSONDecodeError, TypeError):
            specialist_details = {}

        if not record:
            abort(404)

        # Check whether the logged-in user can access this report
        role = session.get("role")
        user_id = session.get("user_id")

        if role == "patient":
            if record["patient_user_id"] != user_id:
                abort(403)

        elif role == "doctor":

            cursor.execute("""
                SELECT 1
                FROM camp_doctors
                WHERE camp_id = %s
                  AND doctor_id = %s
            """, (record["camp_id"], record["doctor_id"]))

            assignment = cursor.fetchone()

            if record["doctor_user_id"] != user_id or not assignment:
                abort(403)

        # Admins can access reports across the system.

        # Build the PDF in memory
        pdf_buffer = BytesIO()

        document = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#174A7E"),
            spaceAfter=8
        )

        subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            textColor=colors.grey,
            spaceAfter=18
        )

        section_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            textColor=colors.HexColor("#174A7E"),
            spaceBefore=12,
            spaceAfter=8
        )

        normal_style = styles["Normal"]

        story = []

        story.append(
            Paragraph(
                "COMMUNITY HEALTH SCREENING REPORT",
                title_style
            )
        )

        story.append(
            Paragraph(
                "Swasthya Community Health Initiative",
                subtitle_style
            )
        )

        story.append(
            Paragraph("Patient Information", section_style)
        )

        patient_data = [
            ["Patient Name", record["full_name"]],
            [
                "Date of Birth",
                record["date_of_birth"].strftime("%d-%m-%Y")
                if record["date_of_birth"] else "Not provided"
            ],
            ["Gender", record["gender"] or "Not provided"],
            ["Phone", record["phone"] or "Not provided"],
            ["Address", record["address"] or "Not provided"]
        ]

        patient_table = Table(
            [
                [
                    Paragraph(f"<b>{escape(str(row[0]))}</b>", normal_style),
                    Paragraph(escape(str(row[1])), normal_style)
                ]
                for row in patient_data
            ],
            colWidths=[45 * mm, 115 * mm]
        )

        story.append(patient_table)

        story.append(
            Paragraph("Health Camp Information", section_style)
        )

        camp_data = [
            ["Camp Name", record["camp_name"]],
            ["Location", record["location"]],
            [
                "City",
                f'{record["city"]}, {record["state"]}'
            ],
            [
                "Camp Date",
                record["camp_date"].strftime("%d-%m-%Y")
            ],
            ["Queue Token", f'#{record["token_no"]}']
        ]

        camp_table = Table(
            [
                [
                    Paragraph(f"<b>{escape(str(row[0]))}</b>", normal_style),
                    Paragraph(escape(str(row[1])), normal_style)
                ]
                for row in camp_data
            ],
            colWidths=[45 * mm, 115 * mm]
        )

        story.append(camp_table)

        story.append(
            Paragraph("Screening Measurements", section_style)
        )

        measurements = [
            ["Measurement", "Recorded Value"],
            [
                "Systolic Blood Pressure",
                f'{record["systolic_bp"]} mmHg'
            ],
            [
                "Diastolic Blood Pressure",
                f'{record["diastolic_bp"]} mmHg'
            ],
            [
                "Blood Sugar",
                f'{record["blood_sugar"]} mg/dL'
            ],
            [
                "Temperature",
                f'{record["temperature"]} °C'
            ],
            [
                "Weight",
                f'{record["weight"]} kg'
            ],
            [
                "Height",
                f'{record["height"]} cm'
            ]
        ]

        measurement_table = Table(
            measurements,
            colWidths=[85 * mm, 75 * mm]
        )

        measurement_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0),
                 colors.HexColor("#174A7E")),

                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

                ("PADDING", (0, 0), (-1, -1), 8),

                ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
            ])
        )

        story.append(measurement_table)

        # Specialist-specific screening details
        if specialist_details:

            story.append(
                Paragraph("Specialist Screening Details", section_style)
            )

            specialist_data = [
                ["Screening Field", "Recorded Details"]
            ]

            specialist_labels = {
                "general_symptoms": "General Symptoms",
                "clinical_findings": "Clinical Findings",
                "pulse_rate": "Pulse Rate (beats/min)",
                "heart_symptoms": "Heart-related Symptoms",
                "affected_area": "Affected Skin Area",
                "skin_condition": "Skin Condition / Findings",
                "right_eye_vision": "Right Eye Visual Acuity",
                "left_eye_vision": "Left Eye Visual Acuity",
                "vision_complaints": "Vision Complaints",
                "growth_observations": "Growth Observations",
                "developmental_observations": "Developmental Observations",
                "relevant_symptoms": "Relevant Symptoms",
                "examination_findings": "Examination Findings",
                "affected_tooth": "Affected Tooth / Area",
                "oral_condition": "Oral Condition",
                "dental_findings": "Dental Findings",
                "specialist_findings": "Specialist Findings"
            }

            for field_name, value in specialist_details.items():
                label = specialist_labels.get(
                    field_name,
                    field_name.replace("_", " ").title()
                )

                specialist_data.append([
                    Paragraph(escape(label), normal_style),
                    Paragraph(
                        escape(str(value)).replace("\n", "<br/>"),
                        normal_style
                    )
                ])

            specialist_table = Table(
                specialist_data,
                colWidths=[65 * mm, 95 * mm]
            )

            specialist_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0),
                    colors.HexColor("#174A7E")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("PADDING", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP")
                ])
            )

            story.append(specialist_table)

        story.append(
            Paragraph("Doctor Information", section_style)
        )

        story.append(
            Paragraph(
                f'<b>Doctor:</b> {escape(str(record["doctor_name"]))}',
                normal_style
            )
        )

        story.append(
            Paragraph(
                f'<b>Specialization:</b> '
                f'{escape(str(record["specialization"] or "Not specified"))}',
                normal_style
            )
        )

        story.append(Spacer(1, 10))

        story.append(
            Paragraph("Observations", section_style)
        )

        observations = record["observations"] or "No observations recorded."

        story.append(
            Paragraph(
                escape(str(observations)).replace("\n", "<br/>"),
                normal_style
            )
        )

        story.append(Spacer(1, 20))

        story.append(
            Paragraph(
                "<b>Important:</b> This document contains recorded "
                "screening measurements. It is not a medical diagnosis "
                "or a substitute for professional medical advice.",
                styles["Italic"]
            )
        )

        story.append(Spacer(1, 12))

        recorded_at = record["recorded_at"]

        story.append(
            Paragraph(
                f"Record generated from screening data recorded on: "
                f"{recorded_at.strftime('%d-%m-%Y %I:%M %p')}",
                styles["Normal"]
            )
        )

        document.build(story)

        pdf_buffer.seek(0)

        # Record the report generation in MySQL
        cursor.execute("""
            INSERT INTO reports (record_id, generated_by)
            VALUES (%s, %s)
        """, (record_id, user_id))

        connection.commit()

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"health_report_{record_id}.pdf"
        )

    except Exception as e:

        if connection:
            connection.rollback()

        if getattr(e, "code", None) in (403, 404):
            raise

        print("PDF generation error:", e)

        flash("Unable to generate the health report.", "danger")
        return redirect(url_for("dashboard.home"))

    finally:

        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()