import face_recognition

owner_image = face_recognition.load_image_file(
    "security/owner.jpg"
)

owner_encoding = face_recognition.face_encodings(
    owner_image
)[0]

def verify_face(frame):

    face_locations = face_recognition.face_locations(frame)

    if not face_locations:
        return False

    face_encodings = face_recognition.face_encodings(
        frame,
        face_locations
    )

    for encoding in face_encodings:

        match = face_recognition.compare_faces(
            [owner_encoding],
            encoding,
            tolerance=0.5
        )

        if match[0]:
            return True

    return False