const video = document.querySelector('#video');
const canvas = document.querySelector('#canvas');
const status = document.querySelector('#status');
const records = document.querySelector('#records');

let cameraStream = null;
let scanInterval = null;
let attendanceMarked = false;

async function loadRecords() {
    const data = await (await fetch('/api/attendance')).json();

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

    video.srcObject = null;
}

async function recognize() {
    if (attendanceMarked || video.readyState < 2) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    canvas.getContext('2d').drawImage(
        video,
        0,
        0
    );

    try {
        const r = await fetch('/api/recognize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image: canvas.toDataURL('image/jpeg', 0.85)
            })
        });

        const d = await r.json();

        if (d.found) {
            const s = d.student;

            status.textContent =
                d.student.already_marked
                    ? `${s.name} (${s.enrollment_id}) was already marked at ${s.time}`
                    : `Marked: ${s.name} | ${s.enrollment_id} | ${s.date} ${s.time}`;

            attendanceMarked = true;

            // Camera automatically OFF
            stopCamera();

            loadRecords();

        } else {
            status.textContent =
                d.message || 'Trying to recognize face…';
        }

    } catch (error) {
        status.textContent = 'Connection error. Please try again.';
    }
}

navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
        cameraStream = stream;
        video.srcObject = stream;

        status.textContent =
            'Look at the camera to mark attendance.';

        scanInterval = setInterval(recognize, 3000);
    })
    .catch(() => {
        status.textContent =
            'Camera permission is required.';
    });

loadRecords();