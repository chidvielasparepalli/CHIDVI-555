from offline.offline_status import offline_status


class OfflineManager:

    def __init__(self):
        self.mode = "ONLINE"

    def update(self):

        if offline_status.check():
            self.mode = "ONLINE"
        else:
            self.mode = "OFFLINE"

        return self.mode

    def is_online(self):
        return self.mode == "ONLINE"

    def is_offline(self):
        return self.mode == "OFFLINE"


offline_manager = OfflineManager()