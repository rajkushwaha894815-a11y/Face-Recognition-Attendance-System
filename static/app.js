const video = document.querySelector('#video');
const canvas = document.querySelector('#canvas');
const status = document.querySelector('#status');
const records = document.querySelector('#records');

let cameraStream = null;
let scanInterval = null;
let attendanceMarked = false;


// =========================
// LOAD DASHBOARD STATISTICS
// =========================

async function loadDashboard() {

    try {

        const response = await fetch('/api/dashboard');
        const data = await response.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        const totalStudents =
            document.querySelector('#totalStudents');

        const presentToday =
            document.querySelector('#presentToday');

        const absentToday =
            document.querySelector('#absentToday');

        const attendanceRate =
            document.querySelector('#attendanceRate');


        if (totalStudents) {
            totalStudents.textContent =
                data.total_students;
        }

        if (presentToday) {
            presentToday.textContent =
                data.present_today;
        }

        if (absentToday) {
            absentToday.textContent =
                data.absent_today;
        }

        if (attendanceRate) {
            attendanceRate.textContent =
                `${data.attendance_rate}%`;
        }

    } catch (error) {

        console.error(
            'Dashboard loading error:',
            error
        );

    }
}


// =========================
// LOAD ATTENDANCE RECORDS
// =========================

async function loadRecords() {

    try {

        const response =
            await fetch('/api/attendance');

        const data =
            await response.json();


        if (data.error) {
            records.innerHTML =
                '<tr><td colspan="4">Unable to load attendance</td></tr>';

            return;
        }


        records.innerHTML =
            data.map(x =>
                `<tr>
                    <td>${x.enrollment_id}</td>
                    <td>${x.name}</td>
                    <td>${x.attendance_date}</td>
                    <td>${x.attendance_time}</td>
                </tr>`
            ).join('') ||
            '<tr><td colspan="4">No attendance yet</td></tr>';


    } catch (error) {

        console.error(
            'Attendance loading error:',
            error
        );

        records.innerHTML =
            '<tr><td colspan="4">Unable to load attendance</td></tr>';
    }
}


// =========================
// STOP CAMERA
// =========================

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


    video.srcObject = null;
}


// =========================
// START CAMERA
// =========================

async function startCamera() {

    try {

        attendanceMarked = false;


        cameraStream =
            await navigator.mediaDevices.getUserMedia({
                video: true
            });


        video.srcObject =
            cameraStream;


        status.textContent =
            'Look at the camera to mark attendance.';


        scanInterval =
            setInterval(recognize, 3000);


    } catch (error) {

        console.error(
            'Camera error:',
            error
        );

        status.textContent =
            'Camera permission is required.';
    }
}


// =========================
// FACE RECOGNITION
// =========================

async function recognize() {

    if (
        attendanceMarked ||
        video.readyState < 2
    ) {
        return;
    }


    canvas.width =
        video.videoWidth;

    canvas.height =
        video.videoHeight;


    canvas
        .getContext('2d')
        .drawImage(
            video,
            0,
            0
        );


    try {

        const response =
            await fetch('/api/recognize', {

                method: 'POST',

                headers: {
                    'Content-Type':
                        'application/json'
                },

                body: JSON.stringify({

                    image:
                        canvas.toDataURL(
                            'image/jpeg',
                            0.85
                        )
                })
            });


        const data =
            await response.json();


        if (data.found) {

            const student =
                data.student;


            if (student.already_marked) {

                status.textContent =
                    `${student.name} (${student.enrollment_id}) was already marked at ${student.time}`;

            } else {

                status.textContent =
                    `Marked: ${student.name} | ${student.enrollment_id} | ${student.date} ${student.time}`;
            }


            attendanceMarked = true;


            // Camera OFF
            stopCamera();


            // Show Next Student button
            const nextButton =
                document.querySelector(
                    '#nextStudent'
                );


            if (nextButton) {

                nextButton.style.display =
                    'block';
            }


            // Refresh attendance table
            await loadRecords();


            // Refresh dashboard statistics
            await loadDashboard();


        } else {

            status.textContent =
                data.message ||
                'Trying to recognize face…';
        }


    } catch (error) {

        console.error(
            'Recognition error:',
            error
        );

        status.textContent =
            'Connection error. Please try again.';
    }
}


// =========================
// NEXT STUDENT
// =========================

function scanNextStudent() {

    const nextButton =
        document.querySelector(
            '#nextStudent'
        );


    if (nextButton) {

        nextButton.style.display =
            'none';
    }


    startCamera();
}


// =========================
// NEXT STUDENT BUTTON
// =========================

const nextButton =
    document.querySelector(
        '#nextStudent'
    );


if (nextButton) {

    nextButton.addEventListener(
        'click',
        scanNextStudent
    );
}


// =========================
// SEARCH ATTENDANCE
// =========================

const searchInput =
    document.querySelector(
        '#searchInput'
    );


if (searchInput) {

    searchInput.addEventListener(
        'input',
        function () {

            const searchValue =
                this.value
                    .toLowerCase()
                    .trim();


            const rows =
                records.querySelectorAll(
                    'tr'
                );


            rows.forEach(row => {

                const text =
                    row.textContent
                        .toLowerCase();


                row.style.display =
                    text.includes(
                        searchValue
                    )
                        ? ''
                        : 'none';
            });

        }
    );
}


// =========================
// INITIAL LOAD
// =========================

// Start camera
startCamera();

// Load attendance
loadRecords();

// Load dashboard statistics
loadDashboard();