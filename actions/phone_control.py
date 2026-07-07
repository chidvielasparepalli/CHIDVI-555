import socket

PHONE_IP = "192.168.137.183"
PHONE_PORT = 5555

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((PHONE_IP, PHONE_PORT))

    print("CONNECTED")

    s.send(b"open_settings\n")

    print("SENT open_settings")

    s.close()

except Exception as e:
    print("ERROR:", e)