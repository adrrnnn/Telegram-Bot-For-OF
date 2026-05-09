"""Ensure only one GUI instance runs at a time."""

import ctypes
import sys
from typing import Any, Optional

_holder: Optional[Any] = None


def acquire_single_instance() -> bool:
    """
    Acquire a process-wide lock. Returns True if this process should run,
    False if another instance is already active.
    """
    global _holder

    if sys.platform == "win32":
        ERROR_ALREADY_EXISTS = 183
        h = ctypes.windll.kernel32.CreateMutexW(
            None,
            False,
            "Local\\TelegramBotManager_SingleInstance_92c4f8a1",
        )
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Telegram Bot Manager is already running.\n\n"
                "Use the open window or check the taskbar.",
                "Already running",
                0x40,
            )
            return False
        _holder = h
        return True

    try:
        from PyQt5.QtCore import QSharedMemory
    except ImportError:
        return True

    mem = QSharedMemory("TelegramBotManager_92c4f8a1_shared")
    if not mem.create(1):
        if mem.error() == QSharedMemory.AlreadyExists:
            print("Telegram Bot Manager is already running.", file=sys.stderr)
            return False
    _holder = mem
    return True
