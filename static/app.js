const video = document.querySelector("#video");
const canvas = document.querySelector("#canvas");
const status = document.querySelector("#status");
const records = document.querySelector("#records");

let cameraStream = null;
let scanInterval = null;
let attendanceMarked = false;
let recognizing = false;


// =====================================================
// HTML ESCAPE
// =====================================================

function escapeHTML(value) {
    if (value === null || value === undefined) {
        return "";
    }

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


// =====================================================
// DASHBOARD
// =====================================================

async function loadDashboard() {

    try {

        const response = await fetch("/api/dashboard", {
            cache: "no-store"
        });

        const data = await response.json();

        console.log("Dashboard:", data);

        if (!response.ok || data.success === false) {
            console.error("Dashboard error:", data.message);
            return;
        }

        const totalStudents =
            document.querySelector("#totalStudents");

        const presentToday =
            document.querySelector("#presentToday");

        const absentToday =
            document.querySelector("#absentToday");

        const attendanceRate =
            document.querySelector("#attendanceRate");


        if (totalStudents) {
            totalStudents.textContent =
                data.total_students ?? 0;
        }

        if (presentToday) {
            presentToday.textContent =
                data.present_today ?? 0;
        }

        if (absentToday) {
            absentToday.textContent =
                data.absent_today ?? 0;
        }

        if (attendanceRate) {
            attendanceRate.textContent =
                `${data.attendance_rate ?? 0}%`;
        }

    }

    catch (error) {

        console.error(
            "Dashboard loading error:",
            error
        );

    }

}


// =====================================================
// TODAY ATTENDANCE
// =====================================================

async function loadRecords() {

    if (!records) {
        return;
    }

    try {

        const response =
            await fetch("/api/attendance", {
                cache: "no-store"
            });

        const data =
            await response.json();

        console.log(
            "Attendance API:",
            data
        );


        if (!response.ok || data.success === false) {

            records.innerHTML =
                '<tr><td colspan="5">Unable to load attendance</td></tr>';

            return;
        }


        // IMPORTANT:
        // app.py returns:
        // {
        //   success: true,
        //   attendance: [...]
        // }

        const attendance =
            Array.isArray(data.attendance)
                ? data.attendance
                : [];


        if (attendance.length === 0) {

            records.innerHTML =
                '<tr><td colspan="5">No attendance yet</td></tr>';

            return;
        }


        records.innerHTML =
            attendance.map(x => `

                <tr>

                    <td>
                        ${escapeHTML(x.enrollment_id)}
                    </td>

                    <td>
                        ${escapeHTML(x.name)}
                    </td>

                    <td>
                        ${escapeHTML(x.date)}
                    </td>

                    <td>
                        ${escapeHTML(x.time)}
                    </td>

                    <td>
                        <span class="status-present">
                            Present
                        </span>
                    </td>

                </tr>

            `).join("");

    }

    catch (error) {

        console.error(
            "Attendance loading error:",
            error
        );

        records.innerHTML =
            '<tr><td colspan="5">Unable to load attendance</td></tr>';

    }

}


// =====================================================
// ATTENDANCE HISTORY
// =====================================================

async function loadHistory() {

    const historyPanel =
        document.querySelector("#history");

    if (!historyPanel) {
        return;
    }


    try {

        const response =
            await fetch("/api/history", {
                cache: "no-store"
            });

        const data =
            await response.json();

        console.log(
            "History API:",
            data
        );


        if (!response.ok || data.success === false) {

            historyPanel.innerHTML = `

                <div class="panel-header">

                    <div>

                        <h2>
                            Attendance History
                        </h2>

                        <p>
                            Recent attendance activity
                        </p>

                    </div>

                </div>

                <div class="history-message">
                    Unable to load attendance history.
                </div>

            `;

            return;
        }


        // IMPORTANT:
        // app.py returns:
        // {
        //   success: true,
        //   history: [...]
        // }

        const history =
            Array.isArray(data.history)
                ? data.history
                : [];


        if (history.length === 0) {

            historyPanel.innerHTML = `

                <div class="panel-header">

                    <div>

                        <h2>
                            Attendance History
                        </h2>

                        <p>
                            Recent attendance activity
                        </p>

                    </div>

                </div>

                <div class="history-message">
                    No attendance history available.
                </div>

            `;

            return;
        }


        historyPanel.innerHTML = `

            <div class="panel-header">

                <div>

                    <h2>
                        Attendance History
                    </h2>

                    <p>
                        Recent attendance activity
                    </p>

                </div>

            </div>


            <div class="table-wrapper">

                <table>

                    <thead>

                        <tr>

                            <th>
                                Enrollment ID
                            </th>

                            <th>
                                Student Name
                            </th>

                            <th>
                                Date
                            </th>

                            <th>
                                Time
                            </th>

                            <th>
                                Status
                            </th>

                        </tr>

                    </thead>


                    <tbody>

                        ${history.map(x => `

                            <tr>

                                <td>
                                    ${escapeHTML(
                                        x.enrollment_id
                                    )}
                                </td>

                                <td>
                                    ${escapeHTML(
                                        x.name
                                    )}
                                </td>

                                <td>
                                    ${escapeHTML(
                                        x.date
                                    )}
                                </td>

                                <td>
                                    ${escapeHTML(
                                        x.time
                                    )}
                                </td>

                                <td>

                                    <span class="status-present">
                                        Present
                                    </span>

                                </td>

                            </tr>

                        `).join("")}

                    </tbody>

                </table>

            </div>

        `;

    }

    catch (error) {

        console.error(
            "History loading error:",
            error
        );

        historyPanel.innerHTML = `

            <div class="history-message">
                Unable to load attendance history.
            </div>

        `;

    }

}


// =====================================================
// STOP CAMERA
// =====================================================

function stopCamera() {

    if (scanInterval) {

        clearInterval(scanInterval);

        scanInterval = null;

    }


    if (cameraStream) {

        cameraStream
            .getTracks()
            .forEach(track => track.stop());

        cameraStream = null;

    }


    if (video) {

        video.srcObject = null;

    }

}


// =====================================================
// START CAMERA
// =====================================================

async function startCamera() {

    try {

        stopCamera();

        attendanceMarked = false;
        recognizing = false;


        if (
            !navigator.mediaDevices ||
            !navigator.mediaDevices.getUserMedia
        ) {

            if (status) {

                status.textContent =
                    "Camera is not supported by this browser.";

            }

            return;
        }


        if (status) {

            status.textContent =
                "Starting camera...";

        }


        cameraStream =
            await navigator.mediaDevices.getUserMedia({

                video: {

                    facingMode: "user",

                    width: {
                        ideal: 640
                    },

                    height: {
                        ideal: 480
                    }

                },

                audio: false

            });


        if (video) {

            video.srcObject =
                cameraStream;

            await video.play();

        }


        if (status) {

            status.textContent =
                "Camera started. Look at the camera...";

        }


        // Wait a little before first scan
        setTimeout(() => {

            recognize();

        }, 1000);


        // Scan every 2.5 seconds
        scanInterval =
            setInterval(() => {

                recognize();

            }, 2500);

    }

    catch (error) {

        console.error(
            "Camera error:",
            error
        );


        if (status) {

            if (error.name === "NotAllowedError") {

                status.textContent =
                    "Camera permission denied. Please allow camera access.";

            }

            else if (error.name === "NotFoundError") {

                status.textContent =
                    "No camera found on this device.";

            }

            else {

                status.textContent =
                    "Camera could not be started.";

            }

        }

    }

}


// =====================================================
// FACE RECOGNITION
// =====================================================

async function recognize() {

    if (
        attendanceMarked ||
        recognizing ||
        !video ||
        !canvas ||
        video.readyState < 2 ||
        !video.videoWidth ||
        !video.videoHeight
    ) {

        return;

    }


    recognizing = true;


    try {

        /*
         * Resize image before sending.
         * This makes face_recognition faster.
         */

        const maxWidth = 800;

        const scale =
            Math.min(
                1,
                maxWidth / video.videoWidth
            );


        canvas.width =
            Math.round(
                video.videoWidth * scale
            );

        canvas.height =
            Math.round(
                video.videoHeight * scale
            );


        const context =
            canvas.getContext("2d", {
                willReadFrequently: true
            });


        context.drawImage(

            video,

            0,
            0,

            canvas.width,
            canvas.height

        );


        if (status) {

            status.textContent =
                "Detecting face...";

        }


        const imageBlob =
            await new Promise(resolve => {

                canvas.toBlob(

                    resolve,

                    "image/jpeg",

                    0.85

                );

            });


        if (!imageBlob) {

            if (status) {

                status.textContent =
                    "Could not capture camera image.";

            }

            return;

        }


        const formData =
            new FormData();


        formData.append(
            "image",
            imageBlob,
            "camera.jpg"
        );


        console.log(
            "Sending image to /api/recognize..."
        );


        const response =
            await fetch(
                "/api/recognize",
                {

                    method: "POST",

                    body: formData,

                    cache: "no-store"

                }
            );


        const data =
            await response.json();


        console.log(
            "Recognition response:",
            data
        );


        if (!response.ok) {

            if (status) {

                status.textContent =
                    data.message ||
                    "Recognition request failed.";

            }

            return;

        }


        /*
         * YOUR app.py returns:
         *
         * {
         *   success: true,
         *   students: [...]
         * }
         *
         * NOT:
         *
         * data.found
         * data.student
         */


        const recognizedStudents =
            Array.isArray(data.students)
                ? data.students
                : [];


        // ==========================================
        // FACE NOT FOUND
        // ==========================================

        if (
            data.success === false ||
            recognizedStudents.length === 0
        ) {

            if (status) {

                status.textContent =
                    data.message ||
                    "Face not recognized. Please look clearly at the camera.";

            }

            return;

        }


        // ==========================================
        // STUDENT FOUND
        // ==========================================

        const student =
            recognizedStudents[0];


        if (!student) {

            return;

        }


        // ==========================================
        // ALREADY MARKED
        // ==========================================

        if (
            student.status === "Already Marked"
        ) {

            if (status) {

                status.textContent =
                    `${student.name} (${student.enrollment_id}) is already marked today at ${student.time}`;

            }

        }


        // ==========================================
        // NEW ATTENDANCE
        // ==========================================

        else if (
            student.status === "Present"
        ) {

            if (status) {

                status.textContent =
                    `✓ Attendance Marked: ${student.name} | ${student.enrollment_id} | ${student.date} ${student.time}`;

            }

        }


        else {

            if (status) {

                status.textContent =
                    `${student.name} recognized`;

            }

        }


        // ==========================================
        // STOP AFTER SUCCESS
        // ==========================================

        attendanceMarked = true;

        stopCamera();


        const nextButton =
            document.querySelector(
                "#nextStudent"
            );


        if (nextButton) {

            nextButton.style.display =
                "block";

        }


        // Refresh dashboard and records

        await loadRecords();

        await loadHistory();

        await loadDashboard();

    }


    catch (error) {

        console.error(
            "Recognition error:",
            error
        );


        if (status) {

            status.textContent =
                "Recognition connection error. Check Flask server.";

        }

    }


    finally {

        recognizing = false;

    }

}


// =====================================================
// SCAN NEXT STUDENT
// =====================================================

function scanNextStudent() {

    const nextButton =
        document.querySelector(
            "#nextStudent"
        );


    if (nextButton) {

        nextButton.style.display =
            "none";

    }


    startCamera();

}


// =====================================================
// NEXT BUTTON
// =====================================================

const nextButton =
    document.querySelector(
        "#nextStudent"
    );


if (nextButton) {

    nextButton.addEventListener(
        "click",
        scanNextStudent
    );

}


// =====================================================
// SEARCH ATTENDANCE
// =====================================================

const searchInput =
    document.querySelector(
        "#searchInput"
    );


if (
    searchInput &&
    records
) {

    searchInput.addEventListener(
        "input",
        function () {

            const searchValue =
                this.value
                    .toLowerCase()
                    .trim();


            const rows =
                records.querySelectorAll(
                    "tr"
                );


            rows.forEach(row => {

                const text =
                    row.textContent
                        .toLowerCase();


                row.style.display =
                    text.includes(
                        searchValue
                    )
                        ? ""
                        : "none";

            });

        }
    );

}


// =====================================================
// INITIAL LOAD
// =====================================================

loadRecords();

loadDashboard();

loadHistory();

startCamera();