import unittest

from core.runtime import run_desktop_app, start_background_runtime


class FakeRoot:
    def __init__(self):
        self.started = False

    def mainloop(self):
        self.started = True


class FakeUI:
    def __init__(self, face_path="face.png"):
        self.face_path = face_path
        self.root = FakeRoot()
        self.waited = False

    def wait_for_api_key(self):
        self.waited = True


class FakeLive:
    def __init__(self, ui):
        self.ui = ui

    def run(self):
        return "runtime-result"


class RuntimeBootstrapTests(unittest.TestCase):
    def test_background_runtime_waits_for_key_and_runs_live(self):
        ui = FakeUI()
        seen = []

        thread = start_background_runtime(
            ui,
            FakeLive,
            run_async=seen.append,
        )
        thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        self.assertTrue(ui.waited)
        self.assertEqual(seen, ["runtime-result"])

    def test_desktop_app_starts_mainloop(self):
        created = []
        seen = []

        def ui_factory(face_path):
            ui = FakeUI(face_path)
            created.append(ui)
            return ui

        run_desktop_app(
            ui_factory,
            FakeLive,
            face_path="custom.png",
            run_async=seen.append,
        )

        self.assertEqual(created[0].face_path, "custom.png")
        self.assertTrue(created[0].root.started)
        self.assertEqual(seen, ["runtime-result"])


if __name__ == "__main__":
    unittest.main()
