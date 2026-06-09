import cv2
from face_auth import verify_face

cam = cv2.VideoCapture(0)

print("Press SPACE to verify")

while True:

    ret, frame = cam.read()

    cv2.imshow("Face Verification", frame)

    key = cv2.waitKey(1)

    if key == 32:

        if verify_face(frame):
            print("FACE VERIFIED")
        else:
            print("FACE REJECTED")

        break

cam.release()
cv2.destroyAllWindows()