import sys
from unittest.mock import MagicMock

# Mock Windows-specific and other missing modules before importing the tested modules
sys.modules["winreg"] = MagicMock()
mock_ctypes = MagicMock()
mock_ctypes.windll = MagicMock()
mock_ctypes.wintypes = MagicMock()
sys.modules["ctypes"] = mock_ctypes
sys.modules["ctypes.wintypes"] = mock_ctypes.wintypes
sys.modules["win32gui"] = MagicMock()
sys.modules["win32process"] = MagicMock()
sys.modules["win32con"] = MagicMock()
sys.modules["pywintypes"] = MagicMock()
sys.modules["win32com"] = MagicMock()
sys.modules["win32com.shell"] = MagicMock()
sys.modules["win32com.shell.shell"] = MagicMock()
sys.modules["posthog"] = MagicMock()
sys.modules["comtypes"] = MagicMock()
sys.modules["comtypes.client"] = MagicMock()
sys.modules["psutil"] = MagicMock()

import subprocess

# Add Windows-specific attributes to subprocess for Linux testing
if not hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
    subprocess.CREATE_NEW_PROCESS_GROUP = 0x00000200
if not hasattr(subprocess, "STARTUPINFO"):
    subprocess.STARTUPINFO = MagicMock

import signal

if not hasattr(signal, "CTRL_BREAK_EVENT"):
    signal.CTRL_BREAK_EVENT = 1

from unittest.mock import patch

# Mock some parts of src to avoid further imports
sys.modules["windows_mcp.analytics"] = MagicMock()

from windows_mcp.desktop.powershell import PowerShellExecutor
from windows_mcp.desktop.utils import run_with_graceful_timeout


def is_abs_windows(path):
    """Check if a path is absolute on Windows."""
    return (len(path) > 2 and path[0].isalpha() and path[1:3] == ":\\") or path.startswith("\\\\")


def test_powershell_executor_uses_absolute_path_for_powershell():
    """Verify that PowerShellExecutor uses an absolute path for powershell.exe when pwsh is missing."""
    with patch("shutil.which", return_value=None):
        with patch("windows_mcp.desktop.powershell.run_with_graceful_timeout") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"output", stderr=b"", returncode=0)

            PowerShellExecutor.execute_command("Get-Date")

            # Get the first argument of the first call to run_with_graceful_timeout
            args_list = mock_run.call_args[0][0]
            shell_cmd = args_list[0]

            assert is_abs_windows(shell_cmd)
            assert shell_cmd.lower().endswith("powershell.exe")
            assert "System32" in shell_cmd


def test_powershell_executor_resolves_literal_powershell_to_absolute_path():
    """Verify that passing 'powershell' as the shell argument resolves to an absolute path."""
    with patch("windows_mcp.desktop.powershell.run_with_graceful_timeout") as mock_run:
        mock_run.return_value = MagicMock(stdout=b"output", stderr=b"", returncode=0)

        PowerShellExecutor.execute_command("Get-Date", shell="powershell")

        args_list = mock_run.call_args[0][0]
        shell_cmd = args_list[0]

        assert is_abs_windows(shell_cmd)
        assert shell_cmd.lower().endswith("powershell.exe")


def test_powershell_executor_explicitly_sets_shell_false():
    """Verify that PowerShellExecutor explicitly passes shell=False to run_with_graceful_timeout."""
    with patch("windows_mcp.desktop.powershell.run_with_graceful_timeout") as mock_run:
        mock_run.return_value = MagicMock(stdout=b"output", stderr=b"", returncode=0)

        PowerShellExecutor.execute_command("Get-Date")

        kwargs = mock_run.call_args[1]
        assert kwargs.get("shell") is False


def test_run_with_graceful_timeout_defaults_shell_false():
    """Verify that run_with_graceful_timeout sets shell=False by default for subprocess.Popen."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"out", b"err")
        mock_process.poll.return_value = 0
        mock_process.args = ["cmd"]
        mock_process.__enter__.return_value = mock_process
        mock_popen.return_value = mock_process

        run_with_graceful_timeout(["some-cmd"])

        kwargs = mock_popen.call_args[1]
        assert kwargs.get("shell") is False


def test_run_with_graceful_timeout_uses_absolute_path_for_taskkill():
    """Verify that run_with_graceful_timeout uses an absolute path for taskkill.exe and shell=False."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = MagicMock()
        # Simulate timeout to trigger taskkill path
        mock_process.communicate.side_effect = [
            subprocess.TimeoutExpired(["cmd"], timeout=1),
            subprocess.TimeoutExpired(["cmd"], timeout=1),
            (b"out", b"err"),
        ]
        mock_process.poll.return_value = 0
        mock_process.args = ["cmd"]
        mock_process.pid = 1234
        mock_process.__enter__.return_value = mock_process
        mock_popen.return_value = mock_process

        with patch("subprocess.run") as mock_run:
            try:
                run_with_graceful_timeout(["some-cmd"], timeout=1)
            except subprocess.TimeoutExpired:
                pass

            # Check if subprocess.run was called with taskkill
            taskkill_call = None
            for call in mock_run.call_args_list:
                if "taskkill.exe" in call[0][0][0].lower():
                    taskkill_call = call
                    break

            assert taskkill_call is not None
            assert is_abs_windows(taskkill_call[0][0][0])
            assert taskkill_call[1].get("shell") is False
