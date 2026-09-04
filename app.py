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

from flask import Flask, jsonify, render_template, request, Response


app = Flask(__name__)


# ==========================================
# DATABASE
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")


def connection():
    parsed = urlparse(DATABASE_URL)

    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        user=parsed.username,
        password=unquote(parsed.password),
        sslmode="require"
    )


# ==========================================
# TIMEZONE
# ==========================================

INDIA_TZ = ZoneInfo("Asia/Kolkata")


def india_now():
    return datetime.now(INDIA_TZ)


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

def init_db():

    conn = connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            enrollment_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            image_path TEXT,
            image_data BYTEA,
            face_encoding BYTEA NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            enrollment_id TEXT NOT NULL,
            name TEXT NOT NULL,
            attended_at TEXT NOT NULL,
            attendance_date TEXT NOT NULL,
            attendance_time TEXT NOT NULL,
            UNIQUE(enrollment_id, attendance_date)
        )
    """)

    conn.commit()

    cur.close()
    conn.close()


# ==========================================
# HOME / DASHBOARD
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
# STUDENTS MANAGEMENT PAGE
# ==========================================

@app.get("/students")
def students_page():
    return render_template("students.html")


# ==========================================
# ENROLL STUDENT API
# ==========================================

@app.post("/api/enroll")
def enroll_student():

    enrollment_id = request.form.get("enrollment_id", "").strip()
    name = request.form.get("name", "").strip()
    image = request.files.get("image")

    if not enrollment_id:
        return jsonify({
            "success": False,
            "message": "Enrollment ID is required"
        }), 400

    if not name:
        return jsonify({
            "success": False,
            "message": "Student name is required"
        }), 400

    if not image:
        return jsonify({
            "success": False,
            "message": "Student image is required"
        }), 400

    # Read image
    image_bytes = image.read()

    if not image_bytes:
        return jsonify({
            "success": False,
            "message": "Invalid image"
        }), 400

    # Convert image
    image_array = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if frame is None:
        return jsonify({
            "success": False,
            "message": "Could not read image"
        }), 400

    # Convert BGR -> RGB
    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Detect faces
    face_locations = face_recognition.face_locations(rgb_image)

    if len(face_locations) == 0:
        return jsonify({
            "success": False,
            "message": "No face detected in image"
        }), 400

    if len(face_locations) > 1:
        return jsonify({
            "success": False,
            "message": "Please upload an image containing only one face"
        }), 400

    # Generate face encoding
    encodings = face_recognition.face_encodings(
        rgb_image,
        face_locations
    )

    if not encodings:
        return jsonify({
            "success": False,
            "message": "Could not generate face encoding"
        }), 400

    face_encoding = encodings[0]

    # Save to database
    conn = connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT enrollment_id
            FROM students
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        existing = cur.fetchone()

        if existing:
            cur.close()
            conn.close()

            return jsonify({
                "success": False,
                "message": "Enrollment ID already exists"
            }), 409

        cur.execute(
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
                "",
                psycopg2.Binary(image_bytes),
                psycopg2.Binary(pickle.dumps(face_encoding))
            )
        )

        conn.commit()

    except Exception as e:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Student enrolled successfully"
    })


# ==========================================
# GET ALL STUDENTS
# ==========================================

@app.get("/api/students")
def get_students():

    conn = connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT
            enrollment_id,
            name,
            image_path
        FROM students
        ORDER BY name ASC
    """)

    students = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "students": students
    })


# ==========================================
# GET STUDENT PHOTO
# ==========================================

@app.get("/api/students/<enrollment_id>/photo")
def student_photo(enrollment_id):

    conn = connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT image_data
        FROM students
        WHERE enrollment_id = %s
        """,
        (enrollment_id,)
    )

    result = cur.fetchone()

    cur.close()
    conn.close()

    if not result or not result[0]:
        return Response(status=404)

    return Response(
        bytes(result[0]),
        mimetype="image/jpeg"
    )


# ==========================================
# DELETE STUDENT
# ==========================================

@app.delete("/api/students/<enrollment_id>")
def delete_student(enrollment_id):

    conn = connection()
    cur = conn.cursor()

    try:

        # Delete attendance first
        cur.execute(
            """
            DELETE FROM attendance
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        # Delete student
        cur.execute(
            """
            DELETE FROM students
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        if cur.rowcount == 0:

            conn.rollback()

            cur.close()
            conn.close()

            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        conn.commit()

    except Exception as e:

        conn.rollback()

        cur.close()
        conn.close()

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Student deleted successfully"
    })


# ==========================================
# FACE RECOGNITION
# ==========================================

@app.post("/api/recognize")
def recognize():

    image = request.files.get("image")

    if not image:
        return jsonify({
            "success": False,
            "message": "Image is required"
        }), 400

    image_bytes = image.read()

    image_array = np.frombuffer(image_bytes, np.uint8)

    frame = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR
    )

    if frame is None:
        return jsonify({
            "success": False,
            "message": "Invalid image"
        }), 400

    rgb_image = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    face_locations = face_recognition.face_locations(
        rgb_image
    )

    face_encodings = face_recognition.face_encodings(
        rgb_image,
        face_locations
    )

    if not face_encodings:

        return jsonify({
            "success": False,
            "message": "No face detected"
        })

    # Get students
    conn = connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            enrollment_id,
            name,
            face_encoding
        FROM students
    """)

    students = cur.fetchall()

    today = india_now().strftime("%Y-%m-%d")
    current_time = india_now().strftime("%H:%M:%S")

    recognized_students = []

    for face_encoding in face_encodings:

        best_student = None
        best_distance = 1.0

        for enrollment_id, name, stored_encoding in students:

            known_encoding = pickle.loads(
                bytes(stored_encoding)
            )

            distance = face_recognition.face_distance(
                [known_encoding],
                face_encoding
            )[0]

            if distance < best_distance:

                best_distance = distance
                best_student = (
                    enrollment_id,
                    name
                )

        if best_student and best_distance < 0.48:

            enrollment_id, name = best_student

            cur.execute(
                """
                SELECT id
                FROM attendance
                WHERE enrollment_id = %s
                AND attendance_date = %s
                """,
                (
                    enrollment_id,
                    today
                )
            )

            already_marked = cur.fetchone()

            if not already_marked:

                attended_at = india_now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                cur.execute(
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
                        enrollment_id,
                        name,
                        attended_at,
                        today,
                        current_time
                    )
                )

                conn.commit()

                recognized_students.append({
                    "enrollment_id": enrollment_id,
                    "name": name,
                    "status": "Present",
                    "date": today,
                    "time": current_time
                })

            else:

                recognized_students.append({
                    "enrollment_id": enrollment_id,
                    "name": name,
                    "status": "Already Marked",
                    "date": today,
                    "time": current_time
                })

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "students": recognized_students
    })


# ==========================================
# DASHBOARD API
# ==========================================

@app.get("/api/dashboard")
def dashboard():

    conn = connection()
    cur = conn.cursor()

    today = india_now().strftime("%Y-%m-%d")

    # Total students
    cur.execute("""
        SELECT COUNT(*)
        FROM students
    """)

    total_students = cur.fetchone()[0]

    # Present today
    cur.execute(
        """
        SELECT COUNT(*)
        FROM attendance
        WHERE attendance_date = %s
        """,
        (today,)
    )

    present_today = cur.fetchone()[0]

    # Absent
    absent_today = max(
        total_students - present_today,
        0
    )

    # Attendance rate
    if total_students > 0:
        attendance_rate = round(
            (present_today / total_students) * 100,
            2
        )
    else:
        attendance_rate = 0

    cur.close()
    conn.close()

    return jsonify({
        "success": True,
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_rate": attendance_rate
    })


# ==========================================
# TODAY ATTENDANCE
# ==========================================

@app.get("/api/attendance")
def attendance():

    conn = connection()
    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    today = india_now().strftime("%Y-%m-%d")

    cur.execute(
        """
        SELECT
            enrollment_id,
            name,
            attendance_date AS date,
            attendance_time AS time
        FROM attendance
        WHERE attendance_date = %s
        ORDER BY attendance_time DESC
        LIMIT 100
        """,
        (today,)
    )

    records = cur.fetchall()

    cur.close()
    conn.close()

    for record in records:
        record["status"] = "Present"

    return jsonify({
        "success": True,
        "attendance": records
    })


# ==========================================
# ATTENDANCE HISTORY
# ==========================================

@app.get("/api/history")
def history():

    conn = connection()
    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    cur.execute("""
        SELECT
            id,
            enrollment_id,
            name,
            attendance_date AS date,
            attendance_time AS time
        FROM attendance
        ORDER BY id DESC
        LIMIT 500
    """)

    records = cur.fetchall()

    cur.close()
    conn.close()

    for record in records:
        record["status"] = "Present"

    return jsonify({
        "success": True,
        "history": records
    })


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    init_db()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )