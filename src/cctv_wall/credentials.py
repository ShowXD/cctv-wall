"""Per-user encryption for the camera passwords kept in workspace.json.

Windows DPAPI ties the ciphertext to the logged-in account, so a copied
configuration file yields nothing on another machine or under another user.
Every other field stays plain text and hand-editable.

Values without the prefix are returned untouched, which keeps existing
configurations and workspace.example.json working.
"""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

PREFIX = "dpapi:"
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt32():
    if os.name != "nt":
        return None
    try:
        library = ctypes.WinDLL("crypt32", use_last_error=True)
    except OSError:
        return None
    for name in ("CryptProtectData", "CryptUnprotectData"):
        function = getattr(library, name)
        function.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                             ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                             ctypes.POINTER(_Blob)]
        function.restype = wintypes.BOOL
    return library


def _call(function, payload: bytes) -> bytes | None:
    buffer = ctypes.create_string_buffer(payload, len(payload))
    source = _Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    result = _Blob()
    if not function(ctypes.byref(source), None, None, None, None,
                    _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(result)):
        return None
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.WinDLL("kernel32").LocalFree(result.pbData)


def is_available() -> bool:
    return _crypt32() is not None


def protect(value: str) -> str:
    """Encrypt a password for storage. An unavailable DPAPI leaves it as it was."""
    if not value or value.startswith(PREFIX):
        return value
    library = _crypt32()
    if library is None:
        return value
    encrypted = _call(library.CryptProtectData, value.encode("utf-8"))
    if encrypted is None:
        return value
    return PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect(value: str) -> str:
    """Decrypt a stored password. An undecryptable value becomes empty, never a crash."""
    if not value.startswith(PREFIX):
        return value
    library = _crypt32()
    if library is None:
        return ""
    try:
        payload = base64.b64decode(value[len(PREFIX):], validate=True)
    except ValueError:
        return ""
    decrypted = _call(library.CryptUnprotectData, payload)
    if decrypted is None:
        return ""
    return decrypted.decode("utf-8", errors="replace")
