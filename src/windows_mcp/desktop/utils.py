"""Desktop utilities. Input sanitization and text processing helpers."""

import os
import re
from xml.sax.saxutils import escape as xml_escape

import pywintypes
from win32com.shell import shell

__all__ = [
    "ps_quote",
    "ps_quote_for_xml",
    "resolve_known_folder_guid_path",
    "remove_private_use_chars",
]

def ps_quote(value: str) -> str:
    """Wrap value in PowerShell single-quoted string literal (escapes ' as '')."""
    return "'" + value.replace("'", "''") + "'"


def ps_quote_for_xml(value: str) -> str:
    """XML-escape then ps_quote. Use for values in XML passed to PowerShell."""
    escaped = xml_escape(value, {'"': '&quot;', "'": '&apos;'})
    return ps_quote(escaped)


_GUID_PATH_RE = re.compile(r"^\{([0-9A-Fa-f-]{36})}(?:\\(.*))?$")


def resolve_known_folder_guid_path(path_text: str) -> str:
    """Resolve a Windows Known Folder GUID path to an absolute filesystem path.

    Some Start Menu shortcuts store their target as a GUID-based path such as
    ``{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\msinfo32.exe``,
    where the leading ``{...}`` is a Known Folder ID (e.g. the Windows directory).
    ``Start-Process`` cannot launch these paths directly, so this function calls
    ``SHGetKnownFolderPath`` to resolve the GUID to its actual location.

    Args:
        path_text: A raw path string, possibly prefixed with a Known Folder GUID.

    Returns:
        The resolved absolute path if the GUID is valid, or *path_text* unchanged
        if it does not match the ``{GUID}\\...`` pattern or the GUID is unrecognised.
    """
    m = _GUID_PATH_RE.match(path_text)
    if not m:
        return path_text

    guid_text = "{" + m.group(1) + "}"
    rest = m.group(2)
    try:
        folder_id = pywintypes.IID(guid_text)
        base = shell.SHGetKnownFolderPath(folder_id, 0, 0)
    except Exception:
        # If the GUID is not a known folder id, just return the original text
        return path_text

    return base if not rest else os.path.join(base, rest)


_PRIVATE_USE_RE = re.compile(
    r'['
    r'\uE000-\uF8FF'          # BMP Private Use Area
    r'\U000F0000-\U000FFFFD'  # Supplementary Private Use Area-A
    r'\U00100000-\U0010FFFD'  # Supplementary Private Use Area-B
    r']+'
)


def remove_private_use_chars(text: str) -> str:
    """Remove Unicode Private Use Area characters that may cause rendering issues."""
    return _PRIVATE_USE_RE.sub('', text)
