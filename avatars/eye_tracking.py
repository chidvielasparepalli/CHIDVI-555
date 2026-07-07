class EyeTracking:

    def __init__(self):
        self.enabled = False

    def enable(self):
        self.enabled = True
        print("[HINATA] Eye Tracking Enabled")

    def disable(self):
        self.enabled = False
        print("[HINATA] Eye Tracking Disabled")

    def is_enabled(self):
        return self.enabled