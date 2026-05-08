from __future__ import annotations

import contextlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .common import DelegateError



class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: Any | None = None

    def try_acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.handle.close()
            self.handle = None
            return False

    def release(self, remove: bool = False) -> None:
        if self.handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    self.handle.seek(0)
                    with contextlib.suppress(OSError):
                        msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    with contextlib.suppress(OSError):
                        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
        if remove:
            with contextlib.suppress(FileNotFoundError):
                self.path.unlink()



def acquire_file_lock(path: Path, timeout_seconds: int, poll_seconds: float, message: Callable[[], str]) -> FileLock:
    if timeout_seconds < 0:
        raise DelegateError(f"LockTimeoutSeconds must be >= 0. Current: {timeout_seconds}")
    if poll_seconds < 0.05:
        raise DelegateError(f"LockPollMilliseconds must be >= 50. Current: {int(poll_seconds * 1000)}")
    deadline = time.monotonic() + max(0, timeout_seconds)
    while True:
        lock = FileLock(path)
        if lock.try_acquire():
            return lock
        if time.monotonic() >= deadline:
            raise DelegateError(message())
        time.sleep(poll_seconds)



def pid_alive(pid: Any) -> bool:
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_int <= 0:
        return False
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid_int}", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid_int) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid_int, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
