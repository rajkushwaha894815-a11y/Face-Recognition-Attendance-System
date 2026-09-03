import base64
import io
import os
import sqlite3
from datetime import datetime

import face_recognition
import numpy as np
from flask import Flask, jsonify, render_template, request
from PIL import Image


# =========================
# PATHS
# =========================

APP_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE = os.path.join(APP_DIR, "attendance.db")

UPLOAD_DIR = os.path.join(APP_DIR, "known_faces")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# =========================
# FLASK APP
# =========================

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


# =========================
# DATABASE CONNECTION
# =========================

def connection():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


# =========================
# DATABASE SETUP
# =========================

def setup_database():

    with connection() as db:

        db.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                enrollment_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                face_encoding BLOB NOT NULL
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enrollment_id TEXT NOT NULL,
                name TEXT NOT NULL,
                attended_at TEXT NOT NULL,
                attendance_date TEXT NOT NULL,
                attendance_time TEXT NOT NULL,
                UNIQUE(enrollment_id, attendance_date)
            );
        """)


# IMPORTANT:
# Render/Gunicorn ke liye database startup par create hoga
setup_database()


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


    # Read image and detect face
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


    # Safe file name
    safe_id = "".join(
        char
        for char in enrollment_id
        if char.isalnum() or char in "-_"
    )


    if not safe_id:

        return jsonify(
            error="Enrollment ID contains invalid characters."
        ), 400


    # Save photo
    image_path = os.path.join(
        UPLOAD_DIR,
        f"{safe_id}.jpg"
    )


    Image.fromarray(image).save(
        image_path,
        "JPEG"
    )


    # Save student in database
    with connection() as db:

        db.execute(
            """
            INSERT INTO students
            (
                enrollment_id,
                name,
                image_path,
                face_encoding
            )

            VALUES (?, ?, ?, ?)

            ON CONFLICT(enrollment_id)
            DO UPDATE SET

                name=excluded.name,

                image_path=excluded.image_path,

                face_encoding=excluded.face_encoding
            """,

            (
                enrollment_id,
                name,
                image_path,
                encodings[0].astype(
                    np.float64
                ).tobytes()
            )
        )


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


    # Detect faces
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


    # Get registered students
    with connection() as db:

        students = db.execute(
            """
            SELECT
                enrollment_id,
                name,
                face_encoding

            FROM students
            """
        ).fetchall()


    if not students:

        return jsonify(
            found=False,
            message="No students enrolled yet."
        )


    # Convert stored encodings
    known = np.array(
        [
            np.frombuffer(
                row["face_encoding"],
                dtype=np.float64
            )

            for row in students
        ]
    )


    # Compare faces
    distances = face_recognition.face_distance(
        known,
        encodings[0]
    )


    best = int(
        np.argmin(distances)
    )


    # Face not matched
    if distances[best] > 0.48:

        return jsonify(
            found=False,
            message="Face is not registered."
        )


    student = students[best]


    now = datetime.now()


    record = {

        "enrollment_id":
            student["enrollment_id"],

        "name":
            student["name"],

        "date":
            now.strftime("%Y-%m-%d"),

        "time":
            now.strftime("%H:%M:%S")
    }


    # Attendance
    with connection() as db:

        existing = db.execute(
            """
            SELECT attended_at

            FROM attendance

            WHERE enrollment_id=?

            AND attendance_date=?
            """,

            (
                record["enrollment_id"],
                record["date"]
            )
        ).fetchone()


        # Already marked
        if existing:

            record["already_marked"] = True

            record["time"] = (
                existing["attended_at"]
                .split(" ")[1]
            )


        # New attendance
        else:

            db.execute(
                """
                INSERT INTO attendance
                (
                    enrollment_id,
                    name,
                    attended_at,
                    attendance_date,
                    attendance_time
                )

                VALUES (?, ?, ?, ?, ?)
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


    return jsonify(
        found=True,
        student=record
    )


# =========================
# ATTENDANCE LIST
# =========================

@app.get("/api/attendance")
def attendance():

    with connection() as db:

        rows = db.execute(
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
        ).fetchall()


    return jsonify(
        [
            dict(row)
            for row in rows
        ]
    )


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

