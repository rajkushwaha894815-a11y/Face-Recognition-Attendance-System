import os
import pickle
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, unquote

import cv2
import face_recognition
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

from flask import Flask, jsonify, render_template, request


# ==========================================
# FLASK APP
# ==========================================

app = Flask(__name__)


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")


def connection():

    parsed = urlparse(DATABASE_URL)

    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        user=unquote(parsed.username),
        password=unquote(parsed.password),
        sslmode="require"
    )


# ==========================================
# INDIA TIMEZONE
# ==========================================

INDIA_TZ = ZoneInfo("Asia/Kolkata")


def india_now():
    return datetime.now(INDIA_TZ)


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    with connection() as db:

        with db.cursor() as cursor:

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    enrollment_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    image_path TEXT,
                    image_data BYTEA,
                    face_encoding BYTEA NOT NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    enrollment_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    attended_at TEXT NOT NULL,
                    attendance_date TEXT NOT NULL,
                    attendance_time TEXT NOT NULL,
                    UNIQUE(enrollment_id, attendance_date)
                )
                """
            )

        db.commit()


# ==========================================
# HOME PAGE
# ==========================================

@app.get("/")
def home():

    return render_template("index.html")


# ==========================================
# ENROLL PAGE
# ==========================================

@app.get("/enroll")
def enroll_page():

    return render_template("enroll.html")


# ==========================================
# ENROLL STUDENT
# ==========================================

@app.post("/api/enroll")
def enroll_student():

    try:

        enrollment_id = request.form.get(
            "enrollment_id",
            ""
        ).strip()

        name = request.form.get(
            "name",
            ""
        ).strip()

        image = request.files.get("image")

        if not enrollment_id:

            return jsonify(
                error="Enrollment ID is required."
            ), 400

        if not name:

            return jsonify(
                error="Student name is required."
            ), 400

        if not image:

            return jsonify(
                error="Student image is required."
            ), 400

        # Read image
        image_bytes = image.read()

        np_array = np.frombuffer(
            image_bytes,
            np.uint8
        )

        frame = cv2.imdecode(
            np_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return jsonify(
                error="Invalid image."
            ), 400

        # BGR -> RGB
        rgb_image = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        # Detect faces
        face_locations = face_recognition.face_locations(
            rgb_image,
            model="hog"
        )

        if len(face_locations) == 0:

            return jsonify(
                error=(
                    "No face detected. "
                    "Please upload a clear face photo."
                )
            ), 400

        if len(face_locations) > 1:

            return jsonify(
                error=(
                    "Multiple faces detected. "
                    "Please upload a photo with only one face."
                )
            ), 400

        # Create face encoding
        encodings = face_recognition.face_encodings(
            rgb_image,
            face_locations
        )

        if not encodings:

            return jsonify(
                error="Could not create face encoding."
            ), 400

        face_encoding = encodings[0]

        encoding_bytes = pickle.dumps(
            face_encoding
        )

        with connection() as db:

            with db.cursor() as cursor:

                # Check duplicate enrollment ID
                cursor.execute(
                    """
                    SELECT enrollment_id
                    FROM students
                    WHERE enrollment_id = %s
                    """,
                    (enrollment_id,)
                )

                existing = cursor.fetchone()

                if existing:

                    return jsonify(
                        error="Enrollment ID already exists."
                    ), 409

                # Save student
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
                    """,
                    (
                        enrollment_id,
                        name,
                        image.filename,
                        psycopg2.Binary(image_bytes),
                        psycopg2.Binary(encoding_bytes)
                    )
                )

            db.commit()

        return jsonify(
            success=True,
            message="Student enrolled successfully.",
            enrollment_id=enrollment_id,
            name=name
        )

    except Exception as error:

        print("ENROLL ERROR:", error)

        return jsonify(
            error="Could not enroll student."
        ), 500


# ==========================================
# FACE RECOGNITION
# ==========================================

@app.post("/api/recognize")
def recognize():

    try:

        image = request.files.get("image")

        if not image:

            return jsonify(
                error="Image is required."
            ), 400

        image_bytes = image.read()

        np_array = np.frombuffer(
            image_bytes,
            np.uint8
        )

        frame = cv2.imdecode(
            np_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return jsonify(
                error="Invalid image."
            ), 400

        # Convert BGR -> RGB
        rgb_image = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        # Detect faces
        face_locations = face_recognition.face_locations(
            rgb_image,
            model="hog"
        )

        if not face_locations:

            return jsonify(
                found=False,
                message="No face detected."
            )

        # Generate encodings
        face_encodings = face_recognition.face_encodings(
            rgb_image,
            face_locations
        )

        if not face_encodings:

            return jsonify(
                found=False,
                message="Could not read face."
            )

        # Get registered students
        with connection() as db:

            with db.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

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

        if not students:

            return jsonify(
                found=False,
                message="No students are registered."
            )

        known_encodings = []
        known_students = []

        for student in students:

            try:

                encoding = pickle.loads(
                    bytes(student["face_encoding"])
                )

                known_encodings.append(
                    encoding
                )

                known_students.append(
                    student
                )

            except Exception as error:

                print(
                    "ENCODING LOAD ERROR:",
                    error
                )

        if not known_encodings:

            return jsonify(
                found=False,
                message="No valid face encodings found."
            )

        # Check detected faces
        for face_encoding in face_encodings:

            distances = face_recognition.face_distance(
                known_encodings,
                face_encoding
            )

            best_index = int(
                np.argmin(distances)
            )

            best_distance = float(
                distances[best_index]
            )

            # Recognition threshold
            if best_distance <= 0.48:

                student = known_students[
                    best_index
                ]

                now = india_now()

                attendance_date = now.strftime(
                    "%Y-%m-%d"
                )

                attendance_time = now.strftime(
                    "%H:%M:%S"
                )

                attended_at = now.isoformat()

                already_marked = False

                with connection() as db:

                    with db.cursor() as cursor:

                        cursor.execute(
                            """
                            SELECT id
                            FROM attendance
                            WHERE enrollment_id = %s
                            AND attendance_date = %s
                            """,
                            (
                                student["enrollment_id"],
                                attendance_date
                            )
                        )

                        existing = cursor.fetchone()

                        if existing:

                            already_marked = True

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
                                    student["enrollment_id"],
                                    student["name"],
                                    attended_at,
                                    attendance_date,
                                    attendance_time
                                )
                            )

                    db.commit()

                return jsonify(
                    found=True,
                    student={
                        "enrollment_id":
                            student["enrollment_id"],
                        "name":
                            student["name"]
                    },
                    date=attendance_date,
                    time=attendance_time,
                    already_marked=already_marked,
                    message=(
                        "Attendance already marked today."
                        if already_marked
                        else "Attendance marked successfully."
                    )
                )

        return jsonify(
            found=False,
            message="Face is not registered."
        )

    except Exception as error:

        print("RECOGNITION ERROR:", error)

        return jsonify(
            error="Face recognition failed."
        ), 500


# ==========================================
# DASHBOARD
# ==========================================

@app.get("/api/dashboard")
def dashboard():

    try:

        today = india_now().strftime(
            "%Y-%m-%d"
        )

        with connection() as db:

            with db.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                # Total students
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM students
                    """
                )

                total_students = int(
                    cursor.fetchone()["total"]
                )

                # Present today
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM attendance
                    WHERE attendance_date = %s
                    """,
                    (today,)
                )

                present_today = int(
                    cursor.fetchone()["total"]
                )

        absent_today = max(
            total_students - present_today,
            0
        )

        if total_students > 0:

            attendance_rate = round(
                (
                    present_today /
                    total_students
                ) * 100,
                2
            )

        else:

            attendance_rate = 0

        return jsonify(
            total_students=total_students,
            present_today=present_today,
            absent_today=absent_today,
            attendance_rate=attendance_rate
        )

    except Exception as error:

        print("DASHBOARD ERROR:", error)

        return jsonify(
            error="Could not load dashboard."
        ), 500


# ==========================================
# TODAY'S ATTENDANCE
# ==========================================

@app.get("/api/attendance")
def attendance():

    try:

        today = india_now().strftime(
            "%Y-%m-%d"
        )

        with connection() as db:

            with db.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        enrollment_id,
                        name,
                        attendance_date,
                        attendance_time,
                        attended_at
                    FROM attendance
                    WHERE attendance_date = %s
                    ORDER BY attended_at DESC
                    LIMIT 100
                    """,
                    (today,)
                )

                rows = cursor.fetchall()

        return jsonify(rows)

    except Exception as error:

        print("ATTENDANCE ERROR:", error)

        return jsonify(
            error="Could not load attendance."
        ), 500


# ==========================================
# ATTENDANCE HISTORY
# ==========================================

@app.get("/api/history")
def attendance_history():

    try:

        with connection() as db:

            with db.cursor(
                cursor_factory=RealDictCursor
            ) as cursor:

                cursor.execute(
                    """
                    SELECT
                        id,
                        enrollment_id,
                        name,
                        attendance_date,
                        attendance_time,
                        attended_at
                    FROM attendance
                    ORDER BY attended_at DESC
                    LIMIT 500
                    """
                )

                rows = cursor.fetchall()

        return jsonify(rows)

    except Exception as error:

        print("HISTORY ERROR:", error)

        return jsonify(
            error="Could not load attendance history."
        ), 500


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    init_db()

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=True
    )