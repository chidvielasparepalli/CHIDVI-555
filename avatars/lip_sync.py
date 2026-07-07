class LipSync:

    def __init__(self):
        self.is_speaking = False

    def start(self):
        self.is_speaking = True
        print("[HINATA] Lip Sync Started")

    def stop(self):
        self.is_speaking = False
        print("[HINATA] Lip Sync Stopped")

    def speaking(self):
        return self.is_speaking