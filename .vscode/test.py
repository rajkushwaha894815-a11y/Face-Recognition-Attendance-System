import cv2

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Camera open nahi ho raha!")
    exit()

print("Camera successfully opened!")

while True:
    ret, frame = cap.read()

    if not ret:
        print("Frame nahi mil raha!")
        break

    cv2.imshow("Camera Test", frame)

    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()