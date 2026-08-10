"""Process resource sampling without a third-party dependency."""
from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from ctypes import wintypes


@dataclass(frozen=True, slots=True)
class ProcessUsage:
    cpu_percent: float | None
    memory_mebibytes: float | None


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class ResourceMonitor:
    """Read this process's CPU and working-set memory via Windows' native APIs."""

    def __init__(self) -> None:
        self._available = os.name == "nt"
        self._last_cpu_time = 0.0
        self._last_wall_time = time.perf_counter()
        if self._available:
            try:
                self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                self._psapi = ctypes.WinDLL("psapi", use_last_error=True)
                # ctypes defaults to a 32-bit integer return type. Explicit signatures are
                # essential here: a 64-bit Windows process handle must never be truncated.
                self._kernel32.GetCurrentProcess.restype = wintypes.HANDLE
                self._kernel32.GetProcessTimes.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                    ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                    ctypes.POINTER(wintypes.FILETIME),
                ]
                self._kernel32.GetProcessTimes.restype = wintypes.BOOL
                self._psapi.GetProcessMemoryInfo.argtypes = [
                    wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD,
                ]
                self._psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
                self._handle = self._kernel32.GetCurrentProcess()
                self._last_cpu_time = self._cpu_time()
            except (AttributeError, OSError):
                # Monitoring is optional: a machine that cannot report it must still play video.
                self._available = False

    @staticmethod
    def _filetime_value(value) -> int:
        return (value.dwHighDateTime << 32) | value.dwLowDateTime

    def _cpu_time(self) -> float:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not self._kernel32.GetProcessTimes(self._handle, ctypes.byref(creation),
                                              ctypes.byref(exit_time), ctypes.byref(kernel),
                                              ctypes.byref(user)):
            raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
        return (self._filetime_value(kernel) + self._filetime_value(user)) / 10_000_000

    def sample(self) -> ProcessUsage:
        if not self._available:
            return ProcessUsage(None, None)
        try:
            current_wall = time.perf_counter()
            current_cpu = self._cpu_time()
            elapsed = max(current_wall - self._last_wall_time, 0.001)
            cpu = 100 * (current_cpu - self._last_cpu_time) / elapsed
            self._last_wall_time, self._last_cpu_time = current_wall, current_cpu

            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if not self._psapi.GetProcessMemoryInfo(self._handle, ctypes.byref(counters),
                                                     wintypes.DWORD(counters.cb)):
                raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
            return ProcessUsage(cpu, counters.WorkingSetSize / (1024 * 1024))
        except OSError:
            return ProcessUsage(None, None)
