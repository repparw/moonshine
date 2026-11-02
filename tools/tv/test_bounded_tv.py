"""Offline tests for bounded TV runs. All external actions are simulated."""

import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import verify_tv
import bounded_tv
import tv_state

UUID = "123e4567-e89b-12d3-a456-426614174000"
TV = {"power": {"returnValue": True, "state": "ACTIVE", "sub state": "active"},
      "foreground": {"returnValue": True, "appId": "com.webos.app.home"},
      "video": {"returnValue": True, "video": [{"connected": False}]}, "volume": {"returnValue": True, "muteStatus": True, "volume": 7}}


class BoundedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        lock_patch = patch.object(bounded_tv, "LOCK_PATH", str(Path(self.temp.name)/"test.lock"))
        lock_patch.start()
        self.addCleanup(lock_patch.stop)
        state_patch = patch.object(tv_state, "STATE_PATH", Path(self.temp.name) / "pending.json")
        state_patch.start()
        self.addCleanup(state_patch.stop)
        self.out = Path(self.temp.name) / "new"
        self.args = ["run", "--device", "tv", "--ssh-alias", "tv-ssh", "--app-id", "com.example.app",
                     "--host-uuid", UUID, "--host-app-id", "1", "--host-pid", "123", "--journal-unit", "host.service",
                     "--duration", "1", "--interval", "1", "--settings-confirmed", "--confirm", "--out", str(self.out)]
        self.commands = []

    def command(self, cmd, **kwargs):
        self.commands.append(cmd)
        if cmd[0] == "ares-launch" and "--running" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "[Info] Set target device : tv\n", "")
        if cmd[0] == "ares-launch":
            return subprocess.CompletedProcess(cmd, 0, "accepted", "")
        if cmd[0] == "journalctl":
            return subprocess.CompletedProcess(cmd, 0, "timestamped journal\n", "")
        raise AssertionError(cmd)

    def run_simulated(self, host=None, tv=None, command=None):
        with patch.object(verify_tv.shutil, "which", return_value="/fake/ares"), \
             patch.object(bounded_tv, "host_status", side_effect=host or (lambda *a: "<root/>")), \
             patch.object(bounded_tv, "tv_status", side_effect=tv or (lambda *a: TV)), \
             patch("subprocess.run", side_effect=command or self.command), \
             patch.object(bounded_tv.time, "sleep"):
            with patch.object(bounded_tv.time, "monotonic", side_effect=[0, 2]):
                return verify_tv.main(self.args)

    def report(self):
        return json.loads((self.out / "run-report.json").read_text())

    def test_confirmation_required_before_any_action(self):
        self.args.remove("--confirm")
        with patch("subprocess.run") as cmd, self.assertRaises(SystemExit):
            verify_tv.main(self.args)
        cmd.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_running_client_refused(self):
        def active(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, "[Info] Set target device : tv\ncom.example.app\n", "")
        self.assertEqual(self.run_simulated(command=active), 2)
        self.assertFalse(self.report()["launch_attempted"])

    def test_active_or_unknown_host_refused(self):
        for error in ("busy", "procfs inaccessible", "server unavailable"):
            with self.subTest(error=error):
                self.out = Path(self.temp.name) / error.replace(" ", "_")
                self.args[-1] = str(self.out)
                self.assertEqual(self.run_simulated(host=lambda *a: (_ for _ in ()).throw(OSError(error))), 2)
                self.assertFalse(self.report()["launch_attempted"])

    def test_unknown_or_active_tv_refused(self):
        for tv in ({**TV, "volume": {"muteStatus": False}}, {**TV, "foreground": {}},
                   {**TV, "foreground": {"appId": "com.example.other"}},
                   {**TV, "video": {"video": [{"connected": True}]}}, {**TV, "video": {}}):
            self.out = Path(self.temp.name) / str(len(list(Path(self.temp.name).iterdir())))
            self.args[-1] = str(self.out)
            self.assertEqual(self.run_simulated(tv=lambda *a: tv), 2)
            self.assertFalse(self.report()["launch_attempted"])

    def test_launch_failure_preserves_evidence_and_manual_cleanup(self):
        def fail(cmd, **kw):
            if cmd[0] == "ares-launch" and "--running" not in cmd:
                return subprocess.CompletedProcess(cmd, 1, "failed", "")
            return self.command(cmd, **kw)
        self.assertEqual(self.run_simulated(command=fail), 2)
        self.assertTrue(self.report()["launch_attempted"])
        self.assertFalse(self.report()["launch_request_accepted"])
        self.assertIn("normal UI", self.report()["cleanup"])
        self.assertEqual((self.out / "launch" / "ares-launch.log").read_text(), "failed")
        self.assertFalse(any("--close" in c for c in self.commands))

    def test_success_collects_without_claiming_playback_or_stopping(self):
        self.assertEqual(self.run_simulated(), 0)
        report = self.report()
        self.assertTrue(report["launch_request_accepted"])
        self.assertFalse(report["playback_verified"])
        self.assertIn("No automatic stop", report["cleanup"])
        self.assertTrue((self.out / "sample-0000.json").exists())
        self.assertTrue((self.out / "journal-0000.log").exists())
        self.assertTrue((self.out / "launch" / "report.json").exists())
        self.assertTrue(any(c[0] == "journalctl" and "--unit" in c and "--system" not in c for c in self.commands))
        self.assertFalse(any("--close" in c for c in self.commands))
        self.assertEqual(self.run_simulated(), 2)
        self.assertEqual(self.report(), report)

    def test_tv_becoming_active_before_launch_is_refused(self):
        def status(*args):
            return {**TV, "video": {"video": [{"connected": True}]}} if any(command[0] == "journalctl" for command in self.commands) else TV
        self.assertEqual(self.run_simulated(tv=status), 2)
        self.assertFalse(self.report()["launch_attempted"])

    def test_interrupt_after_launch_leaves_session_and_report(self):
        interrupted = []
        def status(*args):
            if not interrupted and any(command[0] == "ares-launch" and "--running" not in command for command in self.commands):
                interrupted.append(True)
                raise KeyboardInterrupt
            return TV
        self.assertEqual(self.run_simulated(tv=status), 130)
        self.assertEqual(self.report()["phase"], "interrupted")
        self.assertTrue(self.report()["launch_request_accepted"])
        self.assertFalse(any("--close" in c for c in self.commands))

    def test_unmuted_idle_tv_is_muted_and_restored(self):
        status = json.loads(json.dumps(TV))
        status["volume"]["muteStatus"] = False
        actions = []
        def request(alias, endpoint, data):
            self.assertEqual(endpoint, "com.webos.audio/setMuted")
            self.assertTrue((self.out / "tv-state.json").exists())
            actions.append(data["muted"])
            status["volume"]["muteStatus"] = data["muted"]
        with patch.object(bounded_tv, "tv_request", side_effect=request):
            self.assertEqual(self.run_simulated(tv=lambda *args: status), 0)
        self.assertEqual(actions, [True, False])
        self.assertTrue(self.report()["tv_state_restored"])

    def test_restore_state_requires_confirmation_before_device_access(self):
        with patch("subprocess.run") as command, self.assertRaises(SystemExit):
            verify_tv.main(["restore-state", "--device", "tv", "--ssh-alias", "tv-ssh",
                            "--app-id", "com.example.app", "--out", str(self.out)])
        command.assert_not_called()

    def test_recovery_command_restores_original_mute_from_durable_journal(self):
        status = json.loads(json.dumps(TV))
        status["volume"]["muteStatus"] = False
        self.out.mkdir()
        def request(alias, endpoint, data):
            self.assertEqual(endpoint, "com.webos.audio/setMuted")
            status["volume"]["muteStatus"] = data["muted"]
        with patch.object(bounded_tv, "tv_status", side_effect=lambda alias: status), \
             patch.object(bounded_tv, "tv_request", side_effect=request), \
             patch("subprocess.run", side_effect=self.command):
            guard = bounded_tv.state_guard(self.out, "tv-ssh", "tv", "com.example.app", lambda device: [])
            guard.begin()
            self.assertTrue(status["volume"]["muteStatus"])
            self.assertEqual(verify_tv.main(["restore-state", "--device", "tv", "--ssh-alias", "tv-ssh",
                                            "--app-id", "com.example.app", "--out", str(self.out), "--confirm"]), 0)
            self.assertFalse(status["volume"]["muteStatus"])
            self.assertFalse(tv_state.STATE_PATH.exists())

    def test_lock_refuses_concurrent_run(self):
        with open(bounded_tv.LOCK_PATH, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch("subprocess.run") as cmd:
                self.assertEqual(verify_tv.main(self.args), 2)
                cmd.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_unknown_running_response_fails_closed(self):
        with self.assertRaises(RuntimeError):
            verify_tv.running_apps(subprocess.CompletedProcess([], 0, "unknown output", ""))

class HostStatusTests(unittest.TestCase):
    def test_real_local_server_and_procfs_reject_busy_and_unknown_states(self):
        import sys
        server_code = '''
import http.server, sys
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        game, state = sys.argv[2:]
        body = (f'<root status_code="200"><uniqueid>{sys.argv[1]}</uniqueid>'
                f'<currentgame>{game}</currentgame><state>{state}</state></root>').encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()
'''
        for game, state, allowed in (("0", "MOONSHINE_SERVER_FREE", True),
                                     ("1", "MOONSHINE_SERVER_BUSY", False),
                                     ("0", "unknown", False)):
            with self.subTest(state=state):
                proc = subprocess.Popen([sys.executable, "-u", "-c", server_code, UUID, game, state],
                                        stdout=subprocess.PIPE, text=True)
                try:
                    port = int(proc.stdout.readline())
                    if allowed:
                        self.assertIn("MOONSHINE_SERVER_FREE", bounded_tv.host_status(proc.pid, port, UUID))
                        with self.assertRaises((OSError, RuntimeError)):
                            bounded_tv.host_status(999999999, port, UUID)
                    else:
                        with self.assertRaises(RuntimeError):
                            bounded_tv.host_status(proc.pid, port, UUID)
                finally:
                    proc.terminate()
                    proc.wait(timeout=5)
                    proc.stdout.close()


class TvStatusTests(unittest.TestCase):
    def test_queries_videooutput_service(self):
        responses = iter([
            json.dumps(TV["power"]), json.dumps(TV["foreground"]), json.dumps(TV["video"]), json.dumps(TV["volume"])
        ])
        with patch.object(bounded_tv, "checked", side_effect=lambda cmd: next(responses)) as checked:
            self.assertEqual(bounded_tv.tv_status("tv"), TV)
        self.assertIn("luna://com.webos.service.videooutput/getStatus", checked.call_args_list[2].args[0])


if __name__ == "__main__":
    unittest.main()
