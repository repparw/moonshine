import json
import shlex
from pathlib import Path
import tempfile
import subprocess
import sys
from unittest.mock import patch
import unittest

from tv_state import TvState


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.status = {
            "power": {"returnValue": True, "state": "ACTIVE", "sub state": "active"},
            "foreground": {"appId": "com.webos.app.home"},
            "video": {"video": [{"connected": False}]},
            "volume": {"muteStatus": False, "volume": 7},
        }
        self.actions = []
        self.running = []
        self.guard = self.make_guard("run")

    def make_guard(self, name):
        out = self.root / name
        out.mkdir()
        return TvState(out, "tv", "com.test.moonlight", lambda: self.status,
                       self.set_muted, lambda: self.running, self.root / "pending.json")

    def set_muted(self, muted):
        self.assertTrue(self.guard.registry.exists())
        self.assertTrue((self.guard.out / "tv-state.json").exists())
        self.actions.append(muted)
        self.status["volume"]["muteStatus"] = muted

    def test_recovery_command_is_executable_outside_the_checkout(self):
        command = shlex.split(self.guard.next_action("tv"))
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(Path(command[1]), Path(__file__).with_name("verify_tv.py").resolve())
        self.assertIn(str(self.guard.out), command)
        result = subprocess.run(command[:2] + ["restore-state", "--help"], cwd=self.root,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mutes_and_restores_original_audio_without_power_changes(self):
        self.guard.begin()
        self.assertEqual(self.actions, [True])
        self.guard.restore()
        self.assertEqual(self.actions, [True, False])
        self.assertEqual(self.status["volume"]["volume"], 7)
        self.assertEqual(self.status["power"]["sub state"], "active")
        self.assertFalse(self.guard.registry.exists())
        self.assertTrue(json.loads((self.guard.out / "tv-state.json").read_text())["restored"])

    def test_already_muted_is_not_unmuted(self):
        self.status["volume"]["muteStatus"] = True
        self.guard.begin()
        self.guard.restore()
        self.assertEqual(self.actions, [])

    def test_active_home_screensaver_is_on_not_standby(self):
        self.status["power"]["sub state"] = "screen saver"
        self.guard.begin()
        self.guard.restore()
        self.assertEqual(self.actions, [True, False])
        self.assertEqual(self.status["power"]["state"], "ACTIVE")

    def test_unknown_or_sleeping_power_is_refused_without_mutation(self):
        for power in ({}, {"state": "ACTIVE"}, {"state": "ACTIVE", "sub state": "active standby"},
                      {"state": "SUSPEND", "sub state": "suspend"}):
            with self.subTest(power=power):
                self.status["power"] = power
                with self.assertRaises(RuntimeError):
                    self.guard.begin()
                self.assertEqual(self.actions, [])
                self.assertFalse(self.guard.registry.exists())

    def test_unknown_audio_is_refused(self):
        self.status["volume"]["volume"] = True
        with self.assertRaises(RuntimeError):
            self.guard.begin()
        self.assertEqual(self.actions, [])

    def test_active_video_is_not_muted(self):
        self.status["video"]["video"][0]["connected"] = True
        with self.assertRaises(RuntimeError):
            self.guard.begin()
        self.assertEqual(self.actions, [])

    def test_force_kill_journal_can_be_recovered_by_new_process(self):
        self.guard.begin()
        replacement = TvState(self.guard.out, "tv", "com.test.moonlight", lambda: self.status,
                              self.set_muted, lambda: self.running, self.guard.registry)
        replacement.restore()
        replacement.restore()
        self.assertEqual(self.actions, [True, False])

    def test_pending_run_blocks_new_snapshot(self):
        self.guard.begin()
        with self.assertRaisesRegex(RuntimeError, "restore-state"):
            self.make_guard("other").begin()
        self.assertEqual(self.actions, [True])

    def test_active_client_defers_unmute_and_retains_recovery(self):
        self.guard.begin()
        self.running.append("com.test.moonlight")
        with self.assertRaisesRegex(RuntimeError, "normal UI"):
            self.guard.restore()
        self.assertEqual(self.actions, [True])
        self.assertTrue(self.guard.registry.exists())
        self.running.clear()
        self.guard.restore()
        self.assertEqual(self.actions, [True, False])

    def test_external_volume_change_is_not_overwritten(self):
        self.guard.begin()
        self.status["volume"]["volume"] = 12
        with self.assertRaisesRegex(RuntimeError, "volume changed"):
            self.guard.restore()
        self.assertEqual(self.status["volume"]["volume"], 12)
        self.assertEqual(self.actions, [True])

    def test_timeout_after_mute_is_recoverable(self):
        def timeout(muted):
            self.set_muted(muted)
            raise TimeoutError("reply lost")
        self.guard.set_muted = timeout
        with self.assertRaises(TimeoutError):
            self.guard.begin()
        self.guard.set_muted = self.set_muted
        self.guard.restore()
        self.assertEqual(self.actions, [True, False])

    def test_wrong_device_cannot_restore_another_lease(self):
        self.guard.begin()
        wrong = TvState(self.guard.out, "other-tv", "com.test.moonlight", lambda: self.status,
                        self.set_muted, lambda: self.running, self.guard.registry)
        with self.assertRaises(RuntimeError):
            wrong.restore()
        self.assertEqual(self.actions, [True])

    def test_kill_between_final_write_and_release_is_recoverable(self):
        self.guard.begin()
        self.guard.restore()
        self.guard.registry.write_text((self.guard.out / "tv-state.json").read_text())
        self.guard.restore()
        self.assertFalse(self.guard.registry.exists())
        self.assertEqual(self.actions, [True, False])

    def test_actual_sigkill_retains_original_state_for_recovery(self):
        hardware = self.root / "hardware.json"
        hardware.write_text(json.dumps(self.status))
        code = '''
import json, sys, time
from pathlib import Path
from tv_state import TvState
out, hardware, registry = map(Path, sys.argv[1:])
def read():
    return json.loads(hardware.read_text())
def mute(value):
    state = read()
    state["volume"]["muteStatus"] = value
    hardware.write_text(json.dumps(state))
guard = TvState(out, "tv", "com.test.moonlight", read, mute, lambda: [], registry)
guard.begin()
print("muted", flush=True)
time.sleep(600)
'''
        child = subprocess.Popen([sys.executable, "-B", "-c", code, str(self.guard.out), str(hardware), str(self.guard.registry)],
                                 cwd=Path(__file__).parent, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "muted")
            child.kill()
            child.wait(timeout=5)
            self.status = json.loads(hardware.read_text())
            self.assertTrue(self.status["volume"]["muteStatus"])
            self.guard.restore()
            self.assertEqual(self.actions, [False])
            self.assertFalse(self.guard.registry.exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()

    def test_session_starting_during_journal_write_is_not_muted(self):
        write = self.guard.write
        def external_session():
            write()
            self.status["foreground"]["appId"] = "com.external.app"
        with patch.object(self.guard, "write", side_effect=external_session):
            with self.assertRaisesRegex(RuntimeError, "foreground changed"):
                self.guard.begin()
        self.assertEqual(self.actions, [])

    def test_interrupted_initial_reservation_leaves_no_partial_registry(self):
        with patch("tv_state.os.fsync", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.guard.begin()
        self.assertFalse(self.guard.registry.exists())
        self.assertEqual(self.actions, [])


if __name__ == "__main__":
    unittest.main()
