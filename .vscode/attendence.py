import cv2
import numpy as np
import face_recognition
import os
from datetime import datetime
import pandas as pd

path = 'images'
images = []
classNames = []

for cl in os.listdir(path):
    curImg = cv2.imread(f'{path}/{cl}')
    images.append(curImg)
    classNames.append(os.path.splitext(cl)[0])

def findEncodings(images):
    encodeList = []
    for img in images:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        encode = face_recognition.face_encodings(img)[0]
        encodeList.append(encode)
    return encodeList

def markAttendance(name):
    date = datetime.now().strftime('%Y-%m-%d')
    file_name = f'attendance/Attendance_{date}.csv'

    if not os.path.exists(file_name):
        df = pd.DataFrame(columns=["Name", "Time", "Status"])
        df.to_csv(file_name, index=False)

    df = pd.read_csv(file_name)

    if name not in df["Name"].values:
        now = datetime.now()
        time = now.strftime('%H:%M:%S')

        status = "On Time"
        if now.hour >= 9:
            status = "Late"

        new_row = {"Name": name, "Time": time, "Status": status}
        df = df._append(new_row, ignore_index=True)
        df.to_csv(file_name, index=False)

encodeListKnown = findEncodings(images)

cap = cv2.VideoCapture(0)

while True:
    success, img = cap.read()
    imgS = cv2.resize(img, (0,0), None, 0.25, 0.25)
    imgS = cv2.cvtColor(imgS, cv2.COLOR_BGR2RGB)

    facesCurFrame = face_recognition.face_locations(imgS)
    encodesCurFrame = face_recognition.face_encodings(imgS, facesCurFrame)

    for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):
        matches = face_recognition.compare_faces(encodeListKnown, encodeFace)
        faceDis = face_recognition.face_distance(encodeListKnown, encodeFace)

        matchIndex = np.argmin(faceDis)

        if matches[matchIndex]:
            name = classNames[matchIndex].upper()
            markAttendance(name)

            y1, x2, y2, x1 = faceLoc
            y1, x2, y2, x1 = y1*4, x2*4, y2*4, x1*4

            cv2.rectangle(img,(x1,y1),(x2,y2),(0,255,0),2)
            cv2.putText(img,name,(x1,y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX,0.9,(255,255,255),2)

    cv2.imshow('Attendance System',img)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()