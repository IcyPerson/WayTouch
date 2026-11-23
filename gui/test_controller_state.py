#!/usr/bin/env python3
"""Regression test: the GUI must track F1 capture and F2 mapping-suspend state.

The Rust controller prints ``MOUSE_CAPTURE`` / ``MOUSE_BUTTON_MAPPING`` state
lines when the F1/F2 hotkeys are used. The session panel must follow them in
order, keep the suspended flag across an F1 release (the host preserves the F2
preference), and reset it when the controller exits.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QProcess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))
from waytouch import WayTouchBackend  # noqa: E402


class _FakeProcess:
    """Just enough of QProcess for _read_process_output."""

    def __init__(self, text: str) -> None:
        self._data = text.encode("utf-8")

    def readAllStandardOutput(self) -> bytes:
        return self._data


app = QCoreApplication([])
backend = WayTouchBackend(auto_probe=False)


def feed(chunk: str) -> None:
    backend._read_process_output(_FakeProcess(chunk), "controller")


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}")
        print(f"  controllerState={backend.controllerState!r}")
        print(f"  mouseMappingSuspended={backend.mouseMappingSuspended!r}")
        sys.exit(1)


# Startup: capture is opt-in via F1, mapping starts enabled.
feed(
    "Connected to Android WTCH v2\n"
    "ANDROID_MOUSE_CONNECTED address=127.0.0.1:27186\n"
)
check(backend.controllerState == "Stopped", "banner must not imply capture")
check(backend.mouseMappingSuspended is False, "mapping starts enabled")

# F1 captures the mouse.
feed("MOUSE_CAPTURE state=active source=F1\n")
check(backend.controllerState == "Capturing", "F1 must surface Capturing")

# F2 suspends mouse-button mapping while capture stays active.
feed("MOUSE_BUTTON_MAPPING state=disabled source=F2\n")
check(backend.controllerState == "Capturing", "F2 must not change capture state")
check(backend.mouseMappingSuspended is True, "F2 must surface suspension")

# Releasing capture with F1 keeps the F2 preference (host-side rule).
feed("MOUSE_CAPTURE state=inactive source=F1\n")
check(backend.controllerState == "Connected", "F1 release must surface Connected")
check(backend.mouseMappingSuspended is True, "F1 release must keep suspension")

# Recapturing keeps the suspended flag; F2 resumes mapping.
feed("MOUSE_CAPTURE state=active source=F1\n")
check(backend.mouseMappingSuspended is True, "recapture must keep suspension")
feed("MOUSE_BUTTON_MAPPING state=enabled source=F2\n")
check(backend.mouseMappingSuspended is False, "F2 must resume mapping")

# A rapid F1 release + F2 suspend pair inside one chunk applies in order.
feed(
    "MOUSE_CAPTURE state=inactive source=F1\n"
    "MOUSE_BUTTON_MAPPING state=disabled source=F2\n"
)
check(backend.controllerState == "Connected", "ordered chunk: capture released")
check(backend.mouseMappingSuspended is True, "ordered chunk: mapping suspended")

# Link interruption and recovery keep working.
feed("CONTROL_SESSION_INTERRUPTED reason=touch_transport\n")
check(backend.controllerState == "Reconnecting", "interruption must surface Reconnecting")
feed("Connected to Android WTCH v2\n")
check(backend.controllerState == "Connected", "recovery must surface Connected")

# Controller exit resets the suspended flag for the next session.
backend._controller_finished(0, QProcess.ExitStatus.NormalExit)
check(backend.controllerState == "Stopped", "exit must surface Stopped")
check(backend.mouseMappingSuspended is False, "exit must reset suspension")

# Unrelated log noise must not corrupt the state.
feed("TOUCH_STATS count=42 tcp_dropped=3\nWAYTOUCH version=2\n")
check(backend.controllerState == "Stopped", "noise must not change state")
check(backend.mouseMappingSuspended is False, "noise must not change suspension")

print("controller-state regression checks passed")
