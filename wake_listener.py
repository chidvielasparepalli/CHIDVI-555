import speech_recognition as sr
import subprocess
import psutil
import time
import sys
import cv2
from face_auth import verify_face

WAKE_WORD = "wake up"

def jarvis_running():
    """
    Check if main.py is already running
    """
    for proc in psutil.process_iter(['cmdline']):
        try:
            cmdline = proc.info['cmdline']

            if cmdline:
                for arg in cmdline:
                    if "main.py" in str(arg):
                        return True

        except Exception:
            pass

    return False

def verify_owner():

    cam = cv2.VideoCapture(0)

    print("Verifying face...")

    start = time.time()

    while time.time() - start < 10:

        ret, frame = cam.read()

        if not ret:
            continue

        if verify_face(frame):

            cam.release()
            cv2.destroyAllWindows()

            print("Face verified")
            return True

    cam.release()
    cv2.destroyAllWindows()

    print("Face verification failed")
    return False

def launch_jarvis():
    """
    Launch Jarvis only if not already running
    """
    if not jarvis_running():
        print("[INFO] Launching Jarvis...")
        subprocess.Popen(
            [sys.executable, "main.py"]
        )


recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True

mic = sr.Microphone()

print("=" * 50)
print("JARVIS WAKE LISTENER ACTIVE")
print(f"Wake Phrase: {WAKE_WORD}")
print("=" * 50)

# Calibrate microphone
with mic as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)

while True:

    try:

        # If Jarvis is running, pause listener
        while jarvis_running():
            print("[INFO] Jarvis running - listener paused")
            time.sleep(1)

        print("[LISTENING] Waiting for wake phrase...")

        with mic as source:
            audio = recognizer.listen(
                source,
                timeout=1,
                phrase_time_limit=3
            )

        text = recognizer.recognize_google(audio).lower()

        print(f"[HEARD] {text}")

        if WAKE_WORD in text:

            print("Wake word detected")

            if verify_owner():

                print("Access granted")

                launch_jarvis()

            else:

                print("Access denied")

            # Give Jarvis time to start
            time.sleep(2)

            # Pause listener until Jarvis closes
            while jarvis_running():
                time.sleep(1)

            print("[INFO] Jarvis closed.")
            print("[INFO] Listener active again.")

    except sr.WaitTimeoutError:
        # Nobody spoke
        pass

    except sr.UnknownValueError:
        # Speech not understood
        pass

    except sr.RequestError as e:
        print(f"[ERROR] Speech service error: {e}")
        time.sleep(2)

    except Exception as e:
        print(f"[ERROR] {e}")
        time.sleep(2)