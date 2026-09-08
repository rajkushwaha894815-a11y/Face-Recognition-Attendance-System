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


# =========================================================
# DATABASE
# =========================================================

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
        password=unquote(parsed.password or ""),
        sslmode="require",
        connect_timeout=10
    )


# =========================================================
# TIMEZONE
# =========================================================

INDIA_TZ = ZoneInfo("Asia/Kolkata")


def india_now():
    return datetime.now(INDIA_TZ)


# =========================================================
# FACE SETTINGS
# =========================================================

# Lower value = stricter matching.
# 0.45 is safer against wrong attendance.
FACE_TOLERANCE = float(
    os.environ.get("FACE_TOLERANCE", "0.45")
)

# Difference required between best and second-best match.
# This helps prevent ambiguous/wrong matches.
FACE_MARGIN = float(
    os.environ.get("FACE_MARGIN", "0.04")
)


# =========================================================
# FACE IMAGE PROCESSING
# =========================================================

def prepare_face_image(frame):
    """
    Resize and lightly improve webcam image.
    The SAME processing is used during enrollment
    and recognition.
    """

    if frame is None or frame.size == 0:
        return None

    h, w = frame.shape[:2]

    max_width = 900

    if w > max_width:
        scale = max_width / float(w)

        new_width = int(w * scale)
        new_height = int(h * scale)

        frame = cv2.resize(
            frame,
            (new_width, new_height),
            interpolation=cv2.INTER_AREA
        )

    # Mild contrast improvement
    lab = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2LAB
    )

    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(
        clipLimit=2.0,
        tileGridSize=(8, 8)
    )

    l_channel = clahe.apply(l_channel)

    enhanced = cv2.merge(
        (
            l_channel,
            a_channel,
            b_channel
        )
    )

    return cv2.cvtColor(
        enhanced,
        cv2.COLOR_LAB2BGR
    )


def detect_and_encode(frame):
    """
    Detect faces and generate 128-dimensional
    face encodings.

    Returns:
        face_locations
        face_encodings
        processed_rgb
    """

    processed = prepare_face_image(frame)

    if processed is None:
        return [], [], None

    rgb = cv2.cvtColor(
        processed,
        cv2.COLOR_BGR2RGB
    )

    face_locations = face_recognition.face_locations(
        rgb,
        number_of_times_to_upsample=1,
        model="hog"
    )

    if not face_locations:
        return [], [], rgb

    face_encodings = face_recognition.face_encodings(
        rgb,
        face_locations,
        num_jitters=1
    )

    return (
        face_locations,
        face_encodings,
        rgb
    )


# =========================================================
# FACE ENCODING DATABASE COMPATIBILITY
# =========================================================

def decode_stored_encoding(stored_encoding):
    """
    Supports multiple formats:

    1. Current pickle format
    2. Legacy raw float64 bytes
    3. Legacy raw float32 bytes

    Returns:
        numpy array shape (128,)
        OR None if invalid
    """

    if stored_encoding is None:
        return None

    raw = bytes(stored_encoding)

    if not raw:
        return None

    # -----------------------------------------------------
    # FORMAT 1: Pickle
    # -----------------------------------------------------

    try:
        decoded = pickle.loads(raw)

        decoded = np.asarray(
            decoded,
            dtype=np.float64
        )

        if decoded.shape == (128,):
            return decoded

        decoded = decoded.reshape(-1)

        if decoded.size == 128:
            return decoded.astype(np.float64)

    except Exception:
        pass

    # -----------------------------------------------------
    # FORMAT 2: Legacy float64 raw bytes
    #
    # 128 * 8 = 1024 bytes
    # -----------------------------------------------------

    if len(raw) == 128 * 8:

        try:
            decoded = np.frombuffer(
                raw,
                dtype=np.float64
            ).copy()

            if decoded.shape == (128,):
                return decoded

        except Exception:
            pass

    # -----------------------------------------------------
    # FORMAT 3: Legacy float32 raw bytes
    #
    # 128 * 4 = 512 bytes
    # -----------------------------------------------------

    if len(raw) == 128 * 4:

        try:
            decoded = np.frombuffer(
                raw,
                dtype=np.float32
            ).astype(np.float64)

            if decoded.shape == (128,):
                return decoded

        except Exception:
            pass

    return None


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = connection()
    cur = conn.cursor()

    try:

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

    finally:

        cur.close()
        conn.close()


# =========================================================
# HOME / PAGES
# =========================================================

@app.get("/")
def home():
    return render_template("index.html")


@app.get("/enroll")
def enroll_page():
    return render_template("enroll.html")


@app.get("/students")
def students_page():
    return render_template("students.html")


@app.get("/attendance")
def attendance_page():
    return render_template("attendance.html")


# =========================================================
# ENROLL STUDENT
# =========================================================

@app.post("/api/enroll")
def enroll_student():

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

    image_bytes = image.read()

    if not image_bytes:

        return jsonify({
            "success": False,
            "message": "Invalid image"
        }), 400

    image_array = np.frombuffer(
        image_bytes,
        dtype=np.uint8
    )

    frame = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR
    )

    if frame is None:

        return jsonify({
            "success": False,
            "message": "Could not read image"
        }), 400

    # Same pipeline as recognition
    face_locations, encodings, _ = detect_and_encode(
        frame
    )

    if len(face_locations) == 0:

        return jsonify({
            "success": False,
            "message": (
                "No face detected. "
                "Use a clear front-facing photo "
                "with good lighting."
            )
        }), 400

    if len(face_locations) > 1:

        return jsonify({
            "success": False,
            "message": (
                "Multiple faces detected. "
                "Please use a photo containing "
                "only one face."
            )
        }), 400

    if not encodings:

        return jsonify({
            "success": False,
            "message": "Could not generate face encoding"
        }), 400

    face_encoding = np.asarray(
        encodings[0],
        dtype=np.float64
    )

    # Safety validation
    if face_encoding.shape != (128,):

        return jsonify({
            "success": False,
            "message": "Invalid face encoding generated"
        }), 400

    conn = connection()
    cur = conn.cursor()

    try:

        # Check duplicate enrollment ID
        cur.execute(
            """
            SELECT enrollment_id
            FROM students
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        if cur.fetchone():

            return jsonify({
                "success": False,
                "message": "Enrollment ID already exists"
            }), 409

        # Always save current encoding in pickle format
        encoded_bytes = pickle.dumps(
            face_encoding,
            protocol=pickle.HIGHEST_PROTOCOL
        )

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
                psycopg2.Binary(encoded_bytes)
            )
        )

        conn.commit()

        print(
            f"ENROLLED -> {enrollment_id} | "
            f"{name} | encoding shape={face_encoding.shape}"
        )

        return jsonify({
            "success": True,
            "message": "Student enrolled successfully"
        })

    except Exception as e:

        conn.rollback()

        print(
            "ENROLL ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message": "Enrollment failed: " + str(e)
        }), 500

    finally:

        cur.close()
        conn.close()


# =========================================================
# GET ALL STUDENTS
# =========================================================

@app.get("/api/students")
def get_students():

    conn = connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cur.execute("""
            SELECT
                enrollment_id,
                name,
                image_path
            FROM students
            ORDER BY name ASC
        """)

        students = cur.fetchall()

        return jsonify({
            "success": True,
            "students": students
        })

    finally:

        cur.close()
        conn.close()


# =========================================================
# STUDENT PHOTO
# =========================================================

@app.get("/api/students/<enrollment_id>/photo")
def student_photo(enrollment_id):

    conn = connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT image_data
            FROM students
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        result = cur.fetchone()

        if not result or not result[0]:

            return Response(
                status=404
            )

        return Response(
            bytes(result[0]),
            mimetype="image/jpeg"
        )

    finally:

        cur.close()
        conn.close()


# =========================================================
# DELETE STUDENT
# =========================================================

@app.delete("/api/students/<enrollment_id>")
def delete_student(enrollment_id):

    conn = connection()
    cur = conn.cursor()

    try:

        cur.execute(
            """
            DELETE FROM attendance
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        cur.execute(
            """
            DELETE FROM students
            WHERE enrollment_id = %s
            """,
            (enrollment_id,)
        )

        if cur.rowcount == 0:

            conn.rollback()

            return jsonify({
                "success": False,
                "message": "Student not found"
            }), 404

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Student deleted successfully"
        })

    except Exception as e:

        conn.rollback()

        print(
            "DELETE ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

    finally:

        cur.close()
        conn.close()


# =========================================================
# FACE RECOGNITION
# =========================================================

@app.post("/api/recognize")
def recognize():

    conn = None
    cur = None

    try:

        # -------------------------------------------------
        # RECEIVE IMAGE
        # -------------------------------------------------

        image = request.files.get("image")

        if not image:

            return jsonify({
                "success": False,
                "message": "Image is required",
                "students": []
            }), 400

        image_bytes = image.read()

        if not image_bytes:

            return jsonify({
                "success": False,
                "message": "Empty image received",
                "students": []
            }), 400

        image_array = np.frombuffer(
            image_bytes,
            dtype=np.uint8
        )

        frame = cv2.imdecode(
            image_array,
            cv2.IMREAD_COLOR
        )

        if frame is None:

            return jsonify({
                "success": False,
                "message": "Invalid image received from camera",
                "students": []
            }), 400

        # -------------------------------------------------
        # DETECT FACE
        # -------------------------------------------------

        face_locations, face_encodings, _ = detect_and_encode(
            frame
        )

        if not face_locations:

            return jsonify({
                "success": False,
                "message": (
                    "No face detected. "
                    "Move closer, face the camera "
                    "and improve lighting."
                ),
                "students": []
            })

        if not face_encodings:

            return jsonify({
                "success": False,
                "message": (
                    "Face detected but encoding "
                    "could not be generated."
                ),
                "students": []
            })

        # -------------------------------------------------
        # DATABASE
        # -------------------------------------------------

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

        if not students:

            return jsonify({
                "success": False,
                "message": "No students are enrolled yet.",
                "students": []
            })

        # -------------------------------------------------
        # LOAD ALL VALID ENCODINGS
        # -------------------------------------------------

        known_students = []

        for (
            enrollment_id,
            name,
            stored_encoding
        ) in students:

            known_encoding = decode_stored_encoding(
                stored_encoding
            )

            if known_encoding is None:

                print(
                    "BAD STORED ENCODING ->",
                    enrollment_id,
                    name,
                    "size=",
                    len(bytes(stored_encoding))
                )

                continue

            # Validate range/shape
            if known_encoding.shape != (128,):

                print(
                    "INVALID ENCODING SHAPE ->",
                    enrollment_id,
                    known_encoding.shape
                )

                continue

            known_students.append(
                (
                    enrollment_id,
                    name,
                    known_encoding
                )
            )

        if not known_students:

            return jsonify({
                "success": False,
                "message": (
                    "No valid face encodings found "
                    "in database."
                ),
                "students": []
            }), 500

        # -------------------------------------------------
        # DATE / TIME
        # -------------------------------------------------

        now = india_now()

        today = now.strftime(
            "%Y-%m-%d"
        )

        current_time = now.strftime(
            "%H:%M:%S"
        )

        recognized_students = []

        # -------------------------------------------------
        # MATCH EACH DETECTED FACE
        # -------------------------------------------------

        for face_encoding in face_encodings:

            distances = []

            # Calculate distance against EVERY student
            for (
                enrollment_id,
                name,
                known_encoding
            ) in known_students:

                try:

                    distance = float(
                        face_recognition.face_distance(
                            [known_encoding],
                            face_encoding
                        )[0]
                    )

                    distances.append(
                        (
                            distance,
                            enrollment_id,
                            name
                        )
                    )

                except Exception as distance_error:

                    print(
                        "DISTANCE ERROR:",
                        enrollment_id,
                        repr(distance_error)
                    )

            if not distances:

                recognized_students.append({
                    "enrollment_id": "",
                    "name": "Unknown",
                    "status": "Unknown Face",
                    "date": today,
                    "time": current_time,
                    "distance": None
                })

                continue

            # Sort by smallest distance
            distances.sort(
                key=lambda x: x[0]
            )

            # Best match
            best_distance = distances[0][0]
            best_student = (
                distances[0][1],
                distances[0][2]
            )

            # Second-best match
            second_distance = (
                distances[1][0]
                if len(distances) > 1
                else None
            )

            print(
                "========================================"
            )

            print(
                "FACE MATCH"
            )

            print(
                "Best:",
                best_student,
                "distance=",
                round(best_distance, 4)
            )

            if second_distance is not None:

                print(
                    "Second distance=",
                    round(second_distance, 4)
                )

            print(
                "Tolerance=",
                FACE_TOLERANCE
            )

            print(
                "Margin=",
                FACE_MARGIN
            )

            print(
                "========================================"
            )

            # -------------------------------------------------
            # SAFETY CHECK
            # -------------------------------------------------

            match_is_good = (
                best_distance <= FACE_TOLERANCE
            )

            # If multiple students exist, require
            # the best match to be sufficiently better.
            if second_distance is not None:

                distance_gap = (
                    second_distance -
                    best_distance
                )

                if distance_gap < FACE_MARGIN:

                    match_is_good = False

                    print(
                        "AMBIGUOUS MATCH -> UNKNOWN"
                    )

            # -------------------------------------------------
            # UNKNOWN FACE
            # -------------------------------------------------

            if not match_is_good:

                recognized_students.append({
                    "enrollment_id": "",
                    "name": "Unknown",
                    "status": "Unknown Face",
                    "date": today,
                    "time": current_time,
                    "distance": round(
                        best_distance,
                        4
                    )
                })

                continue

            # -------------------------------------------------
            # VALID STUDENT
            # -------------------------------------------------

            enrollment_id, name = best_student

            # Check whether today's attendance
            # already exists
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

            # -------------------------------------------------
            # FIRST ATTENDANCE
            # -------------------------------------------------

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

                    ON CONFLICT
                    (
                        enrollment_id,
                        attendance_date
                    )
                    DO NOTHING
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
                    "time": current_time,
                    "distance": round(
                        best_distance,
                        4
                    )
                })

                print(
                    f"ATTENDANCE MARKED -> "
                    f"{enrollment_id} | "
                    f"{name} | "
                    f"distance={best_distance:.4f}"
                )

            # -------------------------------------------------
            # ALREADY MARKED
            # -------------------------------------------------

            else:

                recognized_students.append({
                    "enrollment_id": enrollment_id,
                    "name": name,
                    "status": "Already Marked",
                    "date": today,
                    "time": current_time,
                    "distance": round(
                        best_distance,
                        4
                    )
                })

                print(
                    f"ALREADY MARKED -> "
                    f"{enrollment_id} | "
                    f"{name}"
                )

        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        has_recognized = any(
            student["name"] != "Unknown"
            for student in recognized_students
        )

        return jsonify({
            "success": True,
            "message": (
                "Face recognized"
                if has_recognized
                else "Face detected, but no matching student found"
            ),
            "students": recognized_students
        })

    except Exception as e:

        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        print(
            "========================================"
        )

        print(
            "RECOGNITION ERROR:",
            repr(e)
        )

        print(
            "========================================"
        )

        return jsonify({
            "success": False,
            "message": (
                "Recognition server error: "
                + str(e)
            ),
            "students": []
        }), 500

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# =========================================================
# DASHBOARD API
# =========================================================

@app.get("/api/dashboard")
def dashboard():

    conn = connection()
    cur = conn.cursor()

    try:

        today = india_now().strftime(
            "%Y-%m-%d"
        )

        cur.execute("""
            SELECT COUNT(*)
            FROM students
        """)

        total_students = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*)
            FROM attendance
            WHERE attendance_date = %s
            """,
            (today,)
        )

        present_today = cur.fetchone()[0]

        absent_today = max(
            total_students - present_today,
            0
        )

        attendance_rate = (
            round(
                (
                    present_today /
                    total_students
                ) * 100,
                2
            )
            if total_students > 0
            else 0
        )

        return jsonify({
            "success": True,
            "total_students": total_students,
            "present_today": present_today,
            "absent_today": absent_today,
            "attendance_rate": attendance_rate
        })

    finally:

        cur.close()
        conn.close()


# =========================================================
# TODAY ATTENDANCE
# =========================================================

@app.get("/api/attendance")
def attendance_api():

    conn = connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        today = india_now().strftime(
            "%Y-%m-%d"
        )

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

        for record in records:

            record["status"] = "Present"

        return jsonify({
            "success": True,
            "attendance": records
        })

    finally:

        cur.close()
        conn.close()


# =========================================================
# ATTENDANCE MANAGEMENT
# =========================================================

@app.get("/api/attendance-management")
def attendance_management():

    try:

        requested_date = request.args.get(
            "date",
            ""
        ).strip()

        if requested_date:

            try:

                selected_date = datetime.strptime(
                    requested_date,
                    "%Y-%m-%d"
                ).strftime(
                    "%Y-%m-%d"
                )

            except ValueError:

                return jsonify({
                    "success": False,
                    "message": "Invalid date format"
                }), 400

        else:

            selected_date = india_now().strftime(
                "%Y-%m-%d"
            )

        conn = connection()

        cur = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:

            cur.execute(
                """
                SELECT
                    s.enrollment_id,
                    s.name,
                    a.attendance_date AS date,
                    a.attendance_time AS time,

                    CASE
                        WHEN a.enrollment_id IS NOT NULL
                        THEN 'Present'
                        ELSE 'Absent'
                    END AS status

                FROM students s

                LEFT JOIN attendance a
                    ON s.enrollment_id =
                       a.enrollment_id

                    AND a.attendance_date = %s

                ORDER BY s.name ASC
                """,
                (selected_date,)
            )

            records = cur.fetchall()

            return jsonify({
                "success": True,
                "date": selected_date,
                "attendance": records
            })

        finally:

            cur.close()
            conn.close()

    except Exception as e:

        print(
            "ATTENDANCE MANAGEMENT ERROR:",
            repr(e)
        )

        return jsonify({
            "success": False,
            "message": (
                "Unable to load attendance "
                "management data"
            )
        }), 500


# =========================================================
# ATTENDANCE HISTORY
# =========================================================

@app.get("/api/history")
def history():

    conn = connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

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

        for record in records:

            record["status"] = "Present"

        return jsonify({
            "success": True,
            "history": records
        })

    finally:

        cur.close()
        conn.close()


# =========================================================
# RUN APPLICATION
# =========================================================

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
        debug=False
    )