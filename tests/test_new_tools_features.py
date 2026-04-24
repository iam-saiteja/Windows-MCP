import asyncio
import inspect
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from windows_mcp.desktop.views import DesktopState
from windows_mcp.tree.views import TreeState
from windows_mcp.tools import app as app_tools
from windows_mcp.tools import input as input_tools
from windows_mcp.tools.__init__ import ProxyMCP


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *, name, **kwargs):
        def decorator(func):
            self.tools[name] = func
            return func

        return decorator


def _register_input_tools(desktop):
    mcp = FakeMCP()
    input_tools.register(mcp, get_desktop=lambda: desktop, get_analytics=lambda: None)
    return mcp.tools


def _register_app_tools(desktop=None):
    mcp = FakeMCP()
    desktop = desktop or MagicMock()
    app_tools.register(mcp, get_desktop=lambda: desktop, get_analytics=lambda: None)
    return mcp.tools, desktop


class _FakeCenter:
    def __init__(self, value):
        self._value = value

    def to_string(self):
        return self._value


class _FakeNode:
    def __init__(self, name, coords="(10,20)"):
        self.name = name
        self.center = _FakeCenter(coords)
        self.control_type = "Button"
        self.window_name = "Test Window"
        self.metadata = {"enabled": True}


class _FakeControl:
    def __init__(self, exists=True):
        self._exists = exists
        self.last_text = None
        self.clicked = False
        self.typed = None

    def exists(self, timeout=None):
        return self._exists

    def set_edit_text(self, text):
        self.last_text = text

    def click(self):
        self.clicked = True

    def type_keys(self, value):
        self.typed = value


class _FakeDialog:
    def __init__(self, *, has_dialog=True, has_edit=True, has_open=True, has_save=False):
        self._has_dialog = has_dialog
        self.edit = _FakeControl(has_edit)
        self.open = _FakeControl(has_open)
        self.save = _FakeControl(has_save)

    def exists(self, timeout=None):
        return self._has_dialog

    def child_window(self, title=None, control_type=None, found_index=0):
        if title == "File name:" and control_type in {"Edit", "ComboBox"}:
            return self.edit
        if title == "Open" and control_type == "Button":
            return self.open
        if title == "Save" and control_type == "Button":
            return self.save
        return _FakeControl(False)


class _FakePywinautoDesktop:
    def __init__(self, dialog):
        self._dialog = dialog

    def window(self, **kwargs):
        return self._dialog


class TestInputNewTools:
    def test_wait_for_element_finds_matching_node(self):
        desktop = MagicMock()
        desktop.get_state.return_value = DesktopState(
            active_desktop={"name": "Desktop 1"},
            all_desktops=[],
            active_window=None,
            windows=[],
            tree_state=TreeState(
                interactive_nodes=[_FakeNode("Submit")],
                scrollable_nodes=[_FakeNode("List")],
            ),
        )
        tools = _register_input_tools(desktop)

        with patch("windows_mcp.tools.input.time.sleep", return_value=None):
            result = asyncio.run(tools["WaitForElement"](name="Submit", timeout=1))

        assert "Found 'Submit' at (10,20)" in result

    def test_wait_for_element_times_out(self):
        desktop = MagicMock()
        desktop.get_state.return_value = DesktopState(
            active_desktop={"name": "Desktop 1"},
            all_desktops=[],
            active_window=None,
            windows=[],
            tree_state=TreeState(interactive_nodes=[], scrollable_nodes=[]),
        )
        tools = _register_input_tools(desktop)

        result = asyncio.run(tools["WaitForElement"](name="NotFound", timeout=0))

        assert result == "Error: Timeout after 0 seconds waiting for element 'NotFound'."

    def test_find_element_supports_substring_and_regex(self):
        desktop = MagicMock()
        desktop.get_state.return_value = DesktopState(
            active_desktop={"name": "Desktop 1"},
            all_desktops=[],
            active_window=None,
            windows=[],
            tree_state=TreeState(
                interactive_nodes=[_FakeNode("Submit")],
                scrollable_nodes=[_FakeNode("Cancel-123", coords="(30,40)")],
            ),
        )
        tools = _register_input_tools(desktop)

        sub_results = asyncio.run(tools["FindElement"](query="sub"))
        regex_results = asyncio.run(tools["FindElement"](query=r"cancel-\d+"))

        assert len(sub_results) == 1
        assert sub_results[0]["name"] == "Submit"
        assert len(regex_results) == 1
        assert regex_results[0]["coords"] == "(30,40)"


class TestAppNewTools:
    def test_launch_uri_success(self):
        tools, _ = _register_app_tools()

        with patch("os.startfile") as startfile:
            result = asyncio.run(tools["LaunchURI"](uri="ms-settings:"))

        startfile.assert_called_once_with("ms-settings:")
        assert result == "Successfully launched URI: ms-settings:"

    def test_launch_uri_error(self):
        tools, _ = _register_app_tools()

        with patch("os.startfile", side_effect=OSError("bad uri")):
            result = asyncio.run(tools["LaunchURI"](uri="bad://uri"))

        assert "Error launching URI 'bad://uri':" in result

    def test_set_dialog_path_success(self, monkeypatch):
        tools, _ = _register_app_tools()
        dialog = _FakeDialog(has_dialog=True, has_edit=True, has_open=True)
        fake_module = SimpleNamespace(Desktop=lambda backend="uia": _FakePywinautoDesktop(dialog))
        monkeypatch.setitem(sys.modules, "pywinauto", fake_module)

        test_path = r"C:\tmp\file.txt"
        result = asyncio.run(tools["SetDialogPath"](path=test_path))

        assert result == f"Successfully set dialog path to: {test_path}"
        assert dialog.edit.last_text == test_path
        assert dialog.open.clicked is True

    def test_set_dialog_path_missing_dialog(self, monkeypatch):
        tools, _ = _register_app_tools()
        dialog = _FakeDialog(has_dialog=False)
        fake_module = SimpleNamespace(Desktop=lambda backend="uia": _FakePywinautoDesktop(dialog))
        monkeypatch.setitem(sys.modules, "pywinauto", fake_module)

        result = asyncio.run(tools["SetDialogPath"](path=r"C:\tmp\file.txt"))

        assert result == "Error: Could not find any active file dialog window."


class TestProxyMCP:
    def test_proxy_mcp_adds_wait_for_previous_and_strips_it(self):
        base_mcp = FakeMCP()
        proxy = ProxyMCP(base_mcp)
        captured = {}

        @proxy.tool(name="Dummy")
        def dummy_tool(value: int):
            captured["value"] = value
            return f"ok-{value}"

        wrapped = base_mcp.tools["Dummy"]
        signature = inspect.signature(wrapped)

        assert "wait_for_previous" in signature.parameters
        assert signature.parameters["wait_for_previous"].kind == inspect.Parameter.KEYWORD_ONLY

        result = wrapped(7, wait_for_previous=True)

        assert result == "ok-7"
        assert captured["value"] == 7
