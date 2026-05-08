from __future__ import annotations

import atexit
import contextlib
import ctypes
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any


if os.name == "nt":
    from ctypes import wintypes


_ORIGINAL_POPEN = subprocess.Popen
_INSTALLED = False
_CLEANING_UP = False
_TRACKED: list["_TrackedProcess"] = []
_LOCK = RLock()


def _close_windows_handle(handle: Any) -> None:
    if os.name != "nt" or not handle:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def _create_windows_kill_on_close_job(pid: int) -> Any | None:
    if os.name != "nt":
        return None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    assigned = False
    process_handle = None
    try:
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None

        process_handle = kernel32.OpenProcess(0x0100 | 0x0001, False, pid)
        if not process_handle:
            return None
        if not kernel32.AssignProcessToJobObject(job, process_handle):
            return None
        assigned = True
        return job
    finally:
        if process_handle:
            _close_windows_handle(process_handle)
        if job and not assigned:
            _close_windows_handle(job)


def _terminate_windows_job(handle: Any) -> bool:
    if os.name != "nt" or not handle:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    return bool(kernel32.TerminateJobObject(handle, 1))


def _run_untracked(args: list[str]) -> None:
    process = _ORIGINAL_POPEN(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with contextlib.suppress(Exception):
        process.wait(timeout=5)


@dataclass
class _TrackedProcess:
    process: subprocess.Popen[str]
    job_handle: Any | None

    def close(self) -> None:
        if self.job_handle:
            _close_windows_handle(self.job_handle)
            self.job_handle = None

    def terminate_tree(self) -> None:
        if os.name == "nt":
            if not _terminate_windows_job(self.job_handle):
                _run_untracked(["taskkill", "/PID", str(self.process.pid), "/T", "/F"])
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.process.poll() is None:
            time.sleep(0.05)
        if self.process.poll() is None:
            if os.name == "nt":
                with contextlib.suppress(Exception):
                    self.process.kill()
            else:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(self.process.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            self.process.wait(timeout=5)
        self.close()


def _tracked_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[str]:
    if _CLEANING_UP:
        return _ORIGINAL_POPEN(*args, **kwargs)

    popen_kwargs = dict(kwargs)
    if os.name != "nt":
        popen_kwargs.setdefault("start_new_session", True)
    process = _ORIGINAL_POPEN(*args, **popen_kwargs)
    tracked = _TrackedProcess(
        process=process,
        job_handle=_create_windows_kill_on_close_job(process.pid) if os.name == "nt" else None,
    )
    with _LOCK:
        _TRACKED.append(tracked)
    return process


def cleanup_child_processes() -> None:
    global _CLEANING_UP
    with _LOCK:
        tracked = list(reversed(_TRACKED))
        _TRACKED.clear()
    _CLEANING_UP = True
    try:
        for item in tracked:
            if item.process.poll() is None:
                item.terminate_tree()
            else:
                item.close()
    finally:
        _CLEANING_UP = False


def install_child_process_cleanup() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    subprocess.Popen = _tracked_popen
    atexit.register(cleanup_child_processes)
    with contextlib.suppress(ValueError):
        previous = signal.getsignal(signal.SIGTERM)

        def handle_sigterm(signum: int, frame: Any) -> None:
            cleanup_child_processes()
            if callable(previous):
                previous(signum, frame)
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, handle_sigterm)
    _INSTALLED = True
