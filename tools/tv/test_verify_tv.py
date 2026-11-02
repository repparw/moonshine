"""Offline checks of webOS launch requests; no TV commands are executed."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

module_path = Path(__file__).with_name("verify_tv.py")
spec = importlib.util.spec_from_file_location("verify_tv", module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VerifyTVTests(unittest.TestCase):
    def test_webos_launch_payload_matches_moonlight_source_fields(self):
        cmd = module.launch_command("living-room", "com.example.moonlight", "123e4567-e89b-12d3-a456-426614174000", 4)
        self.assertEqual(cmd[:4], ["ares-launch", "--device", "living-room", "com.example.moonlight"])
        self.assertEqual(json.loads(cmd[-1]), {"host_uuid": "123e4567-e89b-12d3-a456-426614174000", "host_app_id": "4"})

    def test_plan_is_never_a_device_action(self):
        with patch.object(module, "get_running") as status, patch.object(module.subprocess, "run") as run:
            self.assertEqual(module.main(["plan", "--device", "a", "--app-id", "b", "--host-uuid", "123e4567-e89b-12d3-a456-426614174000", "--host-app-id", "3"]), 0)
            status.assert_not_called()
            run.assert_not_called()

    def test_start_refuses_existing_app(self):
        fake = type("Result", (), {"returncode": 0, "stdout": "com.example.moonlight", "stderr": ""})()
        with tempfile.TemporaryDirectory() as directory, patch.object(module.shutil, "which", return_value="/bin/true"), patch.object(module, "get_running", return_value=fake), patch.object(module.subprocess, "run") as run:
            rc = module.main(["start", "--device", "a", "--app-id", "com.example.moonlight", "--host-uuid", "123e4567-e89b-12d3-a456-426614174000", "--host-app-id", "3", "--out", directory, "--confirm"])
            self.assertEqual(rc, 2)
            run.assert_not_called()
            self.assertFalse((Path(directory) / "report.json").exists())


    def test_start_without_confirmation_never_queries_device(self):
        with patch.object(module, "get_running") as status, patch.object(module.shutil, "which") as lookup:
            with self.assertRaises(SystemExit) as caught:
                module.main(["start", "--device", "a", "--app-id", "b",
                             "--host-uuid", "123e4567-e89b-12d3-a456-426614174000",
                             "--host-app-id", "3", "--out", "unused"])
            self.assertEqual(caught.exception.code, 2)
            status.assert_not_called()
            lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
