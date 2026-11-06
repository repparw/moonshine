"""Durable audio restoration for explicitly authorized, already-on TV tests."""

import json
import os
from pathlib import Path
import sys
import tempfile


STATE_PATH = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "moonshine-tv/pending-state.json"


def write_json(path, state, exclusive=False):
    descriptor, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as target:
            target.write(json.dumps(state, indent=2) + "\n")
            target.flush()
            os.fsync(target.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def require_available(status):
    power = status.get("power", {})
    if power.get("returnValue") is not True or power.get("state") != "ACTIVE" or power.get("sub state") not in ("active", "screen saver"):
        raise RuntimeError("TV power is sleeping or unknown; no automatic wake is permitted")
    audio = status.get("volume", {})
    if type(audio.get("muteStatus")) is not bool or type(audio.get("volume")) is not int or not 0 <= audio["volume"] <= 100:
        raise RuntimeError("TV audio state is unknown")


def require_idle(status):
    if status.get("foreground", {}).get("appId") != "com.webos.app.home":
        raise RuntimeError("TV foreground changed; restore through the normal UI first")
    videos = status.get("video", {}).get("video")
    if not isinstance(videos, list) or not videos or any(not isinstance(video, dict) or video.get("connected") is not False for video in videos):
        raise RuntimeError("TV video is active or unknown; use the normal UI before restoration")


class TvState:
    def __init__(self, out, ssh_alias, app_id, read_status, set_muted, running_apps, registry=None):
        self.out = Path(out).resolve()
        self.ssh_alias = ssh_alias
        self.app_id = app_id
        self.read_status = read_status
        self.set_muted = set_muted
        self.running_apps = running_apps
        self.registry = Path(registry) if registry is not None else STATE_PATH
        self.state = None

    def next_action(self, device):
        import shlex
        return shlex.join([sys.executable, str(Path(__file__).with_name("verify_tv.py").resolve()), "restore-state", "--device", device,
                           "--ssh-alias", self.ssh_alias, "--app-id", self.app_id,
                           "--out", str(self.out), "--confirm"])

    def write(self):
        for path in (self.registry, self.out / "tv-state.json"):
            write_json(path, self.state)

    def begin(self):
        if self.registry.exists():
            raise RuntimeError(f"Previous TV state is pending; use restore-state with the run recorded in {self.registry}")
        status = self.read_status()
        require_available(status)
        require_idle(status)
        if self.app_id in self.running_apps():
            raise RuntimeError("Moonlight is already running; refusing to mute an active client")
        self.state = {"version": 1, "out": str(self.out), "ssh_alias": self.ssh_alias,
                      "app_id": self.app_id, "before": json.loads(json.dumps(status)),
                      "restored": False, "power_action": "none; leave the initially active TV on"}
        self.registry.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        write_json(self.registry, self.state, exclusive=True)
        self.write()
        if self.app_id in self.running_apps():
            raise RuntimeError("Moonlight started during preparation; use the normal UI before recovery")
        current = self.read_status()
        require_available(current)
        require_idle(current)
        if any(current["volume"][key] != status["volume"][key] for key in ("muteStatus", "volume")):
            raise RuntimeError("TV audio changed during preparation; refusing to mute")
        if status["volume"]["muteStatus"] is False:
            self.set_muted(True)
        muted = self.read_status()
        require_available(muted)
        require_idle(muted)
        if muted["volume"]["muteStatus"] is not True or muted["volume"]["volume"] != status["volume"]["volume"]:
            raise RuntimeError("TV mute or volume verification failed; original state retained for recovery")

    def restore(self):
        path = self.registry if self.registry.exists() else self.out / "tv-state.json"
        state = json.loads(path.read_text())
        if (state.get("version"), state.get("out"), state.get("ssh_alias"), state.get("app_id")) != (1, str(self.out), self.ssh_alias, self.app_id):
            raise RuntimeError("TV recovery journal belongs to another run or device")
        self.state = state
        if state.get("restored") is True:
            self.write()
            self.registry.unlink(missing_ok=True)
            return
        require_available(state["before"])
        current = self.read_status()
        require_available(current)
        before = state["before"]["volume"]
        if current["volume"]["volume"] != before["volume"]:
            raise RuntimeError("TV volume changed externally; refusing to overwrite operator state")
        if current["volume"]["muteStatus"] != before["muteStatus"]:
            if self.app_id in self.running_apps():
                raise RuntimeError("Moonlight is still running; stop the owned test through its normal UI, then restore-state")
            require_idle(current)
            self.set_muted(before["muteStatus"])
            current = self.read_status()
            require_available(current)
            if any(current["volume"][key] != before[key] for key in ("muteStatus", "volume")):
                raise RuntimeError("TV audio restoration verification failed")
        state["restored"] = True
        state["after"] = current
        self.write()
        self.registry.unlink()
