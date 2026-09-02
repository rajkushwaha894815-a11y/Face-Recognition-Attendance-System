# Face Recognition Attendance System

A real-time **Face Recognition based Attendance Management System** built with **Python, Flask, OpenCV, and face-recognition**.

The system allows users to enroll students/employees using their face and automatically mark attendance when their face is recognized.

## 🚀 Features

* 🔐 Face Recognition based authentication
* 👤 Student/Employee enrollment
* 📷 Real-time camera-based face recognition
* ✅ Automatic attendance marking
* 📅 Date-wise attendance tracking
* 🗄️ SQLite database integration
* 🌐 Flask web interface
* 📊 Attendance records through API
* ⚡ Real-time face matching

## 🛠️ Technologies Used

* **Python**
* **Flask**
* **OpenCV**
* **Face Recognition**
* **NumPy**
* **Pillow**
* **SQLite**
* **HTML**
* **CSS**
* **JavaScript**

## 📁 Project Structure

```text
Face-Recognition-Attendance-System/
│
├── app.py
├── requirements.txt
├── Procfile
├── Attendance.csv
│
├── templates/
│   ├── index.html
│   └── enroll.html
│
├── static/
│   ├── app.js
│   └── style.css
│
└── .vscode/
    └── test.py
```

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/rajkushwaha894815-a11y/Face-Recognition-Attendance-System.git
```

### 2. Open the project

```bash
cd Face-Recognition-Attendance-System
```

### 3. Create a virtual environment

```bash
python -m venv .venv
```

### 4. Activate virtual environment

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

## ▶️ Run the Project

Start the Flask application:

```bash
python app.py
```

Then open your browser and visit:

```text
http://127.0.0.1:5000
```

## 🔄 How It Works

1. Open the web application.
2. Enroll a student/employee using their name and photo.
3. The system detects the face from the uploaded image.
4. The face encoding is stored for recognition.
5. Start the recognition process using the camera.
6. The system compares the detected face with registered faces.
7. If the face matches, attendance is automatically recorded.
8. Attendance can be retrieved from the attendance system.

## 🗄️ Database

The application uses **SQLite** to store:

* Student/Employee information
* Face-related data
* Attendance records
* Attendance date and time

## 📌 API Endpoints

| Endpoint          | Method | Purpose                |
| ----------------- | ------ | ---------------------- |
| `/`               | GET    | Main application       |
| `/enroll`         | GET    | Enrollment page        |
| `/api/enroll`     | POST   | Register a new person  |
| `/api/recognize`  | POST   | Recognize a face       |
| `/api/attendance` | GET    | Get attendance records |

## 🎯 Future Improvements

* Admin login and authentication
* Employee dashboard
* Monthly attendance reports
* Export attendance to Excel/PDF
* Email notifications
* Cloud database
* Deployment with a live URL
* Improved UI/UX
* Multiple camera support

## 👨‍💻 Author

**Raj Kushwaha**

BCA Student | Python Developer | AI Enthusiast

## ⭐ Support

If you find this project useful, consider giving it a ⭐ star on GitHub.

---

**Built with Python, Flask, OpenCV & Face Recognition**

