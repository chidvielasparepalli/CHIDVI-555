import socket


class OfflineStatus:
    def __init__(self):
        self.online = True

    def check(self, timeout=2):
        try:
            socket.setdefaulttimeout(timeout)
            socket.create_connection(("8.8.8.8", 53))
            self.online = True
        except OSError:
            self.online = False

        return self.online


offline_status = OfflineStatus()
