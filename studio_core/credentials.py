"""HS-021: provider credentials live only in the operating system's credential store.

Never in project files, workspace snapshots, the journal, browser storage, logs, evidence or Git.
Studio reads a key only to put it in the request it is about to send, and never returns it to the
editor: the editor learns *whether* a key is stored, nothing more.

Backends, chosen by platform:
* **Windows:** Credential Manager (``CredWriteW`` / ``CredReadW`` / ``CredDeleteW``, generic credentials,
  per user).
* **Linux:** the Secret Service through ``secret-tool`` (libsecret). The secret goes in on stdin, never on
  a command line other processes can read.
* **Anywhere:** the ``keyring`` package, if it is installed.
* **Otherwise:** no store. Studio refuses to save a key rather than fall back to a file. macOS's
  ``security`` command takes the secret as an argument, so it is not used.

``HORIZON_STUDIO_CREDENTIALS=memory`` selects an in-memory store for tests; nothing in it outlives the
process.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

SERVICE = "horizon-studio"
NAMES = ("anthropic",)
MAX_SECRET = 512


class CredentialError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _name(name: str) -> str:
    if name not in NAMES:
        raise CredentialError("UNKNOWN_CREDENTIAL", f"No credential named {name!r}")
    return name


def _secret(value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_SECRET or "\n" in value or "\0" in value:
        raise CredentialError("BAD_SECRET", "Expected a single-line key of at most 512 characters")
    return value.strip()


class MemoryStore:
    kind = "memory"

    def __init__(self):
        self._items: dict[str, str] = {}

    def get(self, name):
        return self._items.get(_name(name))

    def set(self, name, secret):
        self._items[_name(name)] = _secret(secret)

    def delete(self, name):
        self._items.pop(_name(name), None)


class SecretToolStore:
    """libsecret's ``secret-tool``: store reads the secret from stdin."""
    kind = "secret-service"

    def __init__(self, tool: str):
        self.tool = tool

    def _run(self, args, data=None):
        try:
            return subprocess.run([self.tool, *args], input=data, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CredentialError("STORE_UNAVAILABLE", f"The Secret Service did not answer: {exc}") from None

    def get(self, name):
        done = self._run(["lookup", "service", SERVICE, "account", _name(name)])
        if done.returncode != 0:
            return None
        return done.stdout.rstrip("\n") or None

    def set(self, name, secret):
        done = self._run(["store", f"--label=Horizon Studio {name}", "service", SERVICE, "account", _name(name)],
                         data=_secret(secret))
        if done.returncode != 0:
            raise CredentialError("STORE_FAILED", "The Secret Service refused to store the key")

    def delete(self, name):
        self._run(["clear", "service", SERVICE, "account", _name(name)])


class KeyringStore:
    kind = "keyring"

    def __init__(self, module):
        self.keyring = module

    def get(self, name):
        return self.keyring.get_password(SERVICE, _name(name))

    def set(self, name, secret):
        self.keyring.set_password(SERVICE, _name(name), _secret(secret))

    def delete(self, name):
        try:
            self.keyring.delete_password(SERVICE, _name(name))
        except Exception:  # noqa: BLE001 - absent is fine
            pass


class WindowsStore:
    """Windows Credential Manager, generic credentials persisted for the local user."""
    kind = "windows-credential-manager"

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self.ctypes, self.CREDENTIAL = ctypes, CREDENTIAL
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self.read, self.write, self.remove, self.free = advapi.CredReadW, advapi.CredWriteW, advapi.CredDeleteW, advapi.CredFree
        self.read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        self.write.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        self.remove.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.free.argtypes = [ctypes.c_void_p]

    GENERIC, LOCAL_MACHINE = 1, 2  # CRED_TYPE_GENERIC, CRED_PERSIST_LOCAL_MACHINE (this user, this machine)

    def _target(self, name):
        return f"{SERVICE}/{_name(name)}"

    def get(self, name):
        pointer = self.ctypes.POINTER(self.CREDENTIAL)()
        if not self.read(self._target(name), self.GENERIC, 0, self.ctypes.byref(pointer)):
            return None
        try:
            blob = self.ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize)
            return blob.decode("utf-16-le")
        finally:
            self.free(pointer)

    def set(self, name, secret):
        data = _secret(secret).encode("utf-16-le")
        buffer = self.ctypes.create_string_buffer(data, len(data))
        credential = self.CREDENTIAL(Type=self.GENERIC, TargetName=self._target(name), Persist=self.LOCAL_MACHINE,
                                     CredentialBlobSize=len(data),
                                     CredentialBlob=self.ctypes.cast(buffer, self.ctypes.POINTER(self.ctypes.c_char)),
                                     UserName=SERVICE)
        if not self.write(self.ctypes.byref(credential), 0):
            raise CredentialError("STORE_FAILED", f"Credential Manager refused the key ({self.ctypes.get_last_error()})")

    def delete(self, name):
        self.remove(self._target(name), self.GENERIC, 0)


def default_store(environ=os.environ):
    """The platform's store, or ``None`` when there is no safe one."""
    if environ.get("HORIZON_STUDIO_CREDENTIALS") == "memory":
        return MemoryStore()
    if sys.platform == "win32":
        try:
            return WindowsStore()
        except (OSError, AttributeError):
            return None
    if sys.platform.startswith("linux"):
        tool = shutil.which("secret-tool")
        if tool:
            return SecretToolStore(tool)
    try:
        import keyring  # noqa: PLC0415 - optional
        return KeyringStore(keyring)
    except ImportError:
        return None
