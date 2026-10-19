"""Resolve redirected Windows known folders without guessing user paths."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import uuid

PICTURES = "33E28130-4E1E-4676-835A-98395C3BC3BB"
SCREENSHOTS = "B7BEDE81-DF94-4682-A7D8-57A52620B86F"


def known_folder(folder_id: str) -> Path:
    if os.name != "nt":
        raise OSError("Automatic Screenshots discovery requires Windows; specify --source.")
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    guid = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(folder_id).bytes_le)
    pointer = ctypes.c_void_p()
    shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                         wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    # DONT_VERIFY: resolve the location without creating the folder.
    result = shell.SHGetKnownFolderPath(ctypes.byref(guid), 0x4000, None, ctypes.byref(pointer))
    if result != 0:
        raise OSError(f"Windows known-folder lookup failed (HRESULT {result & 0xffffffff:08X}).")
    try:
        return Path(ctypes.wstring_at(pointer))
    finally:
        ole.CoTaskMemFree(pointer)


def screenshots_folder() -> Path:
    try:
        return known_folder(SCREENSHOTS)
    except OSError:
        return known_folder(PICTURES) / "Screenshots"
