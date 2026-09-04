import base64
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import face_recognition
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, render_template, request
from PIL import Image


# =========================
# FLASK APP
# =========================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# =========================
# POSTGRESQL DATABASE
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")


def connection():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


# =========================
# DATABASE SETUP
# =========================

def setup_database():
    with connection() as db:
        with db.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    enrollment_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    image_path TEXT,
                    image_data BYTEA,
                    face_encoding BYTEA NOT NULL
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    enrollment_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    attended_at TEXT NOT NULL,
                    attendance_date TEXT NOT NULL,
                    attendance_time TEXT NOT NULL,
                    UNIQUE(enrollment_id, attendance_date)
                );
            """)

            cursor.execute("""
                ALTER TABLE students
                ADD COLUMN IF NOT EXISTS image_path TEXT;
            """)

            cursor.execute("""
                ALTER TABLE students
                ADD COLUMN IF NOT EXISTS image_data BYTEA;
            """)


# Initialize database
setup_database()


# =========================
# INDIA TIMEZONE
# =========================

INDIA_TIMEZONE = ZoneInfo("Asia/Kolkata")


# =========================
# IMAGE FROM CAMERA
# =========================

def image_from_data_url(data_url):

    try:
        encoded = data_url.split(",", 1)[1]

        raw = base64.b64decode(encoded)

        image = Image.open(
            io.BytesIO(raw)
        ).convert("RGB")

        return np.array(image)

    except (IndexError, ValueError, OSError):

        return None


# =========================
# HOME PAGE
# =========================

@app.get("/")
def index():
    return render_template("index.html")


# =========================
# ENROLL PAGE
# =========================

@app.get("/enroll")
def enroll_page():
    return render_template("enroll.html")


# =========================
# ENROLL STUDENT
# =========================

@app.post("/api/enroll")
def enroll():

    enrollment_id = request.form.get(
        "enrollment_id",
        ""
    ).strip()

    name = request.form.get(
        "name",
        ""
    ).strip()

    photo = request.files.get("photo")


    # Check details
    if not enrollment_id or not name or not photo:

        return jsonify(
            error="Enrollment ID, name, and photo are required."
        ), 400


    # =========================
    # READ IMAGE AND DETECT FACE
    # =========================

    try:

        image = face_recognition.load_image_file(photo)

        encodings = face_recognition.face_encodings(
            image
        )

    except Exception:

        return jsonify(
            error="The uploaded image could not be read."
        ), 400


    # Exactly one face required
    if len(encodings) != 1:

        return jsonify(
            error="Upload a clear photo containing exactly one face."
        ), 400


    # =========================
    # SAFE FILE NAME
    # =========================

    safe_id = "".join(
        char
        for char in enrollment_id
        if char.isalnum() or char in "-_"
    )

    if not safe_id:

        return jsonify(
            error="Enrollment ID contains invalid characters."
        ), 400


    # =========================
    # CONVERT IMAGE TO BYTES
    # =========================

    try:

        image_buffer = io.BytesIO()

        Image.fromarray(image).save(
            image_buffer,
            format="JPEG"
        )

        image_data = image_buffer.getvalue()

    except Exception:

        return jsonify(
            error="Could not process the uploaded photo."
        ), 400


    # =========================
    # FACE ENCODING
    # =========================

    face_encoding = encodings[0].astype(
        np.float64
    ).tobytes()


    # =========================
    # SAVE STUDENT
    # =========================

    try:

        with connection() as db:

            with db.cursor() as cursor:

                cursor.execute(
                    """
                    INSERT INTO students
                    (
                        enrollment_id,
                        name,
                        image_path,
                        image_data,
                        face_encoding
                    )
                    VALUES (%s, %s, %s, %s, %s)

                    ON CONFLICT(enrollment_id)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        image_path = EXCLUDED.image_path,
                        image_data = EXCLUDED.image_data,
                        face_encoding = EXCLUDED.face_encoding
                    """,
                    (
                        enrollment_id,
                        name,
                        f"{safe_id}.jpg",
                        image_data,
                        face_encoding
                    )
                )

    except Exception as error:

        print("DATABASE ERROR:", error)

        return jsonify(
            error="Could not save student to database."
        ), 500


    return jsonify(
        message=f"{name} enrolled successfully."
    )


# =========================
# FACE RECOGNITION
# =========================

@app.post("/api/recognize")
def recognize():

    payload = request.get_json(
        silent=True
    ) or {}

    image = image_from_data_url(
        payload.get("image", "")
    )


    if image is None:

        return jsonify(
            error="Invalid camera image."
        ), 400


    # =========================
    # DETECT FACES
    # =========================

    locations = face_recognition.face_locations(
        image,
        model="hog"
    )

    encodings = face_recognition.face_encodings(
        image,
        locations
    )


    if not encodings:

        return jsonify(
            found=False,
            message="No face detected. Look at the camera."
        )


    # =========================
    # GET REGISTERED STUDENTS
    # =========================

    try:

        with connection() as db:

            with db.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        enrollment_id,
                        name,
                        face_encoding
                    FROM students
                    """
                )

                students = cursor.fetchall()

    except Exception as error:

        print("DATABASE ERROR:", error)

        return jsonify(
            error="Could not read student database."
        ), 500


    if not students:

        return jsonify(
            found=False,
            message="No students enrolled yet."
        )


    # =========================
    # CONVERT STORED ENCODINGS
    # =========================

    known = np.array(
        [
            np.frombuffer(
                row["face_encoding"],
                dtype=np.float64
            )
            for row in students
        ]
    )


    # =========================
    # COMPARE FACES
    # =========================

    distances = face_recognition.face_distance(
        known,
        encodings[0]
    )

    best = int(
        np.argmin(distances)
    )


    # =========================
    # FACE NOT MATCHED
    # =========================

    if distances[best] > 0.48:

        return jsonify(
            found=False,
            message="Face is not registered."
        )


    student = students[best]


    # =========================
    # INDIA CURRENT DATE/TIME
    # =========================

    now = datetime.now(
        INDIA_TIMEZONE
    )


    record = {
        "enrollment_id": student["enrollment_id"],
        "name": student["name"],
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S")
    }


    # =========================
    # ATTENDANCE
    # =========================

    try:

        with connection() as db:

            with db.cursor() as cursor:

                # Check today's attendance
                cursor.execute(
                    """
                    SELECT attended_at
                    FROM attendance
                    WHERE enrollment_id = %s
                    AND attendance_date = %s
                    """,
                    (
                        record["enrollment_id"],
                        record["date"]
                    )
                )

                existing = cursor.fetchone()


                # =========================
                # ALREADY MARKED
                # =========================

                if existing:

                    record["already_marked"] = True

                    record["time"] = (
                        existing["attended_at"]
                        .split(" ")[1]
                    )


                # =========================
                # NEW ATTENDANCE
                # =========================

                else:

                    cursor.execute(
                        """
                        INSERT INTO attendance
                        (
                            enrollment_id,
                            name,
                            attended_at,
                            attendance_date,
                            attendance_time
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            record["enrollment_id"],
                            record["name"],
                            now.strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                            record["date"],
                            record["time"]
                        )
                    )

                    record["already_marked"] = False


    except Exception as error:

        print("DATABASE ERROR:", error)

        return jsonify(
            error="Could not save attendance."
        ), 500


    return jsonify(
        found=True,
        student=record
    )


# =========================
# ATTENDANCE LIST
# =========================

@app.get("/api/attendance")
def attendance():

    try:

        with connection() as db:

            with db.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        enrollment_id,
                        name,
                        attendance_date,
                        attendance_time
                    FROM attendance
                    ORDER BY attended_at DESC
                    LIMIT 100
                    """
                )

                rows = cursor.fetchall()


        return jsonify(rows)


    except Exception as error:

        print("DATABASE ERROR:", error)

        return jsonify(
            error="Could not load attendance."
        ), 500


# =========================
# LOCAL RUN
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv("PORT", 5000)
        ),
        debug=True
    )