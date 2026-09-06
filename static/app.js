const video = document.querySelector('#video');
const canvas = document.querySelector('#canvas');
const status = document.querySelector('#status');
const records = document.querySelector('#records');

let cameraStream = null;
let scanInterval = null;
let attendanceMarked = false;
let recognizing = false;

async function loadDashboard() {
try {
const response = await fetch('/api/dashboard');
const data = await response.json();

    if (data.error) {
        console.error(data.error);
        return;
    }

    const totalStudents = document.querySelector('#totalStudents');
    const presentToday = document.querySelector('#presentToday');
    const absentToday = document.querySelector('#absentToday');
    const attendanceRate = document.querySelector('#attendanceRate');

    if (totalStudents) {
        totalStudents.textContent = data.total_students ?? 0;
    }

    if (presentToday) {
        presentToday.textContent = data.present_today ?? 0;
    }

    if (absentToday) {
        absentToday.textContent = data.absent_today ?? 0;
    }

    if (attendanceRate) {
        attendanceRate.textContent = `${data.attendance_rate ?? 0}%`;
    }

} catch (error) {
    console.error('Dashboard loading error:', error);
}

}

async function loadRecords() {
try {
const response = await fetch('/api/attendance');
const data = await response.json();

    if (!response.ok || data.error) {
        if (records) {
            records.innerHTML =
                '<tr><td colspan="5">Unable to load attendance</td></tr>';
        }
        return;
    }

    if (!records) {
        return;
    }

    records.innerHTML = data.map(x => `
        <tr>
            <td>${x.enrollment_id ?? ''}</td>
            <td>${x.name ?? ''}</td>
            <td>${x.attendance_date ?? ''}</td>
            <td>${x.attendance_time ?? ''}</td>
            <td>
                <span class="status-present">Present</span>
            </td>
        </tr>
    `).join('') ||
    '<tr><td colspan="5">No attendance yet</td></tr>';

} catch (error) {
    console.error('Attendance loading error:', error);

    if (records) {
        records.innerHTML =
            '<tr><td colspan="5">Unable to load attendance</td></tr>';
    }
}

}

async function loadHistory() {
try {
const response = await fetch('/api/history');
const data = await response.json();

    const historyPanel = document.querySelector('#history');

    if (!historyPanel) {
        return;
    }

    if (!response.ok || data.error) {
        historyPanel.innerHTML = `
            <div class="panel-header">
                <div>
                    <h2>Attendance History</h2>
                    <p>Recent attendance activity</p>
                </div>
            </div>
            <div class="history-message">
                Unable to load attendance history.
            </div>
        `;
        return;
    }

    if (!data.length) {
        historyPanel.innerHTML = `
            <div class="panel-header">
                <div>
                    <h2>Attendance History</h2>
                    <p>Recent attendance activity</p>
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
                <h2>Attendance History</h2>
                <p>Recent attendance activity</p>
            </div>
        </div>

        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Enrollment ID</th>
                        <th>Student Name</th>
                        <th>Date</th>
                        <th>Time</th>
                        <th>Status</th>
                    </tr>
                </thead>

                <tbody>
                    ${data.map(x => `
                        <tr>
                            <td>${x.enrollment_id ?? ''}</td>
                            <td>${x.name ?? ''}</td>
                            <td>${x.attendance_date ?? ''}</td>
                            <td>${x.attendance_time ?? ''}</td>
                            <td>
                                <span class="status-present">
                                    Present
                                </span>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;

} catch (error) {
    console.error('History loading error:', error);
}

}

function stopCamera() {

if (scanInterval) {
    clearInterval(scanInterval);
    scanInterval = null;
}

if (cameraStream) {
    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
}

if (video) {
    video.srcObject = null;
}

}

async function startCamera() {

try {

    stopCamera();

    attendanceMarked = false;
    recognizing = false;

    if (!navigator.mediaDevices ||
        !navigator.mediaDevices.getUserMedia) {

        if (status) {
            status.textContent =
                'Camera is not supported by this browser.';
        }

        return;
    }

    cameraStream =
        await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'user'
            },
            audio: false
        });

    if (video) {
        video.srcObject = cameraStream;
        await video.play();
    }

    if (status) {
        status.textContent =
            'Camera started. Look at the camera...';
    }

    scanInterval =
        setInterval(recognize, 2000);

} catch (error) {

    console.error('Camera error:', error);

    if (status) {
        status.textContent =
            'Camera permission is required or camera is unavailable.';
    }
}

}

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

canvas.width = video.videoWidth;
canvas.height = video.videoHeight;

const context = canvas.getContext('2d');

context.drawImage(
    video,
    0,
    0,
    canvas.width,
    canvas.height
);

if (status) {
    status.textContent =
        'Detecting face...';
}

try {

    const imageBlob =
        await new Promise(resolve => {

            canvas.toBlob(
                resolve,
                'image/jpeg',
                0.85
            );

        });

    if (!imageBlob) {

        if (status) {
            status.textContent =
                'Could not capture camera image.';
        }

        return;
    }

    const formData =
        new FormData();

    formData.append(
        'image',
        imageBlob,
        'camera.jpg'
    );

    const response =
        await fetch(
            '/api/recognize',
            {
                method: 'POST',
                body: formData
            }
        );

    const data =
        await response.json();

    console.log(
        'Recognition response:',
        data
    );

    if (response.ok && data.found) {

        const student =
            data.student;

        if (student.already_marked) {

            if (status) {
                status.textContent =
                    `${student.name} (${student.enrollment_id}) was already marked at ${student.time}`;
            }

        } else {

            if (status) {
                status.textContent =
                    `Attendance Marked: ${student.name} | ${student.enrollment_id} | ${student.date} ${student.time}`;
            }
        }

        attendanceMarked = true;

        stopCamera();

        const nextButton =
            document.querySelector(
                '#nextStudent'
            );

        if (nextButton) {
            nextButton.style.display =
                'block';
        }

        await loadRecords();
        await loadHistory();
        await loadDashboard();

    } else {

        if (status) {
            status.textContent =
                data.message ||
                'Face not recognized. Please look at the camera clearly.';
        }
    }

} catch (error) {

    console.error(
        'Recognition error:',
        error
    );

    if (status) {
        status.textContent =
            'Recognition connection error.';
    }

} finally {

    recognizing = false;
}

}

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

const searchInput =
document.querySelector(
'#searchInput'
);

if (searchInput && records) {

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
                text.includes(searchValue)
                    ? ''
                    : 'none';
        });
    }
);

}

loadRecords();
loadDashboard();
loadHistory();
startCamera();