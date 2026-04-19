"""Static PowerShell command executor utility."""

import base64
import ctypes
import ctypes.wintypes
import logging
import os
import shutil
import socket
import subprocess

from windows_mcp.desktop.utils import run_with_graceful_timeout

logger = logging.getLogger(__name__)


def _prepare_env() -> dict[str, str]:
    """Prepare a complete environment block for the PowerShell subprocess.

    MCP hosts (e.g. Claude Desktop) may launch this server with a stripped
    environment block missing session-level variables. This function starts
    from os.environ and fills in missing variables from:
      1. System-level env vars from the registry (HKLM)
      2. User-level env vars from the registry (HKCU)
      3. Dynamic vars (COMPUTERNAME, USERNAME, etc.) via Win32 API / stdlib
    Existing values in os.environ are never overwritten, only missing ones
    are supplemented. PATH is special-cased: registry paths are prepended.
    """
    env = os.environ.copy()

    # 1) Supplement missing vars from registry
    machine_path = ""
    try:
        import winreg

        # System-level environment variables
        machine_pathext = ""
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    upper = name.upper()
                    if upper == "PATH":
                        machine_path = value
                    elif upper == "PATHEXT":
                        machine_pathext = value
                    else:
                        env.setdefault(name, value)
                    i += 1
                except OSError:
                    break

        # User-level environment variables
        user_path = ""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        if name.upper() == "PATH":
                            user_path = value
                        else:
                            env.setdefault(name, value)
                        i += 1
                    except OSError:
                        break
        except OSError:
            pass

        # PATH: prepend registry paths to ensure system executables are discoverable
        registry_path = ";".join(filter(None, [machine_path, user_path]))
        if registry_path:
            env["PATH"] = ";".join(filter(None, [registry_path, env.get("PATH", "")]))

        # PATHEXT: use registry value if the inherited one looks incomplete (e.g. venv strips it)
        if machine_pathext and ".EXE" not in env.get("PATHEXT", ""):
            env["PATHEXT"] = machine_pathext

    except Exception:
        logger.debug("Failed to read environment from registry")
        if ".EXE" not in env.get("PATHEXT", ""):
            env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.CPL;.PY;.PYW"

    # 2) Dynamic variables not stored in registry env keys — only fill if missing
    if not env.get("COMPUTERNAME"):
        env["COMPUTERNAME"] = socket.gethostname().upper()

    if not env.get("USERNAME"):
        try:
            buf = ctypes.create_unicode_buffer(256)
            size = ctypes.wintypes.DWORD(256)
            if ctypes.windll.advapi32.GetUserNameW(buf, ctypes.byref(size)):
                env["USERNAME"] = buf.value
        except Exception as e:
            logger.debug("Failed to get USERNAME via Win32 API: %s", e)

    user_profile = os.path.expanduser("~")
    env.setdefault("USERPROFILE", user_profile)
    drive, tail = os.path.splitdrive(user_profile)
    env.setdefault("HOMEDRIVE", drive)
    env.setdefault("HOMEPATH", tail)
    env.setdefault("USERDOMAIN", env.get("COMPUTERNAME", ""))

    return env


class PowerShellExecutor:
    """Static utility class for executing PowerShell commands."""

    @staticmethod
    def execute_command(
        command: str, timeout: int = 10, shell: str | None = None
    ) -> tuple[str, int]:
        try:
            # $OutputEncoding: controls how PS5.1 encodes output written to its stdout pipe.
            # Without this set to UTF-8, PS5.1 uses the system codepage and native process
            # stdout is silently lost when Python reads the pipe.
            # [Console]::OutputEncoding: controls how PS decodes bytes from native exe stdout.
            utf8_command = (
                "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                f"{command}"
            )
            encoded = base64.b64encode(utf8_command.encode("utf-16le")).decode("ascii")
            env = _prepare_env()
            # NO_COLOR suppresses ANSI escape sequences in pwsh 7.2+ (and many other CLI tools).
            # PS5.1 has no ANSI output, so this is harmlessly ignored there.
            # https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_ansi_terminals#disabling-ansi-output
            env["NO_COLOR"] = "1"

            shell = shell or ("pwsh" if shutil.which("pwsh") else "powershell")

            args = [shell, "-NoProfile"]
            # Only older Windows PowerShell (5.1) uses -OutputFormat Text successfully here
            shell_name = os.path.basename(shell).lower().replace(".exe", "")
            if shell_name == "powershell":
                args.extend(["-OutputFormat", "Text"])
            args.extend(["-EncodedCommand", encoded])

            result = run_with_graceful_timeout(
                args,
                stdin=subprocess.DEVNULL,  # Prevent child processes from inheriting the MCP pipe stdin
                capture_output=True,  # No errors='ignore' - let subprocess return bytes
                timeout=timeout,
                cwd=os.path.expanduser(path="~"),
                env=env,
            )
            # Handle both bytes and str output (subprocess behavior varies by environment)
            stdout = result.stdout
            stderr = result.stderr
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return stdout or stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "Command execution timed out", 1
        except Exception as e:
            return f"Command execution failed: {type(e).__name__}: {e}", 1
