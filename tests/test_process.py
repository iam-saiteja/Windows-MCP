import pytest
from unittest.mock import MagicMock, patch
from windows_mcp.desktop.service import Desktop

@pytest.fixture
def desktop():
    with patch.object(Desktop, '__init__', lambda self: None):
        d = Desktop()
        return d

def create_proc_mock(pid, name, cpu, mem_rss):
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "cpu_percent": cpu,
        "memory_info": MagicMock(rss=mem_rss) if mem_rss is not None else None
    }
    return proc

class TestListProcesses:
    @patch("psutil.process_iter")
    def test_list_processes_limit(self, mock_iter, desktop):
        # Create 5 mock processes
        mock_iter.return_value = [
            create_proc_mock(1, "proc1", 1.0, 100 * 1024 * 1024),
            create_proc_mock(2, "proc2", 2.0, 200 * 1024 * 1024),
            create_proc_mock(3, "proc3", 3.0, 300 * 1024 * 1024),
            create_proc_mock(4, "proc4", 4.0, 400 * 1024 * 1024),
            create_proc_mock(5, "proc5", 5.0, 500 * 1024 * 1024),
        ]

        # Default sort is by memory (descending)
        # 5: 500MB, 4: 400MB, 3: 300MB, 2: 200MB, 1: 100MB

        # Test limit < total
        result = desktop.list_processes(limit=2)
        assert "Processes (2 shown):" in result
        assert "proc5" in result
        assert "proc4" in result
        assert "proc3" not in result

        # Test limit > total
        result = desktop.list_processes(limit=10)
        assert "Processes (5 shown):" in result
        assert "proc1" in result

        # Test limit = 0
        result = desktop.list_processes(limit=0)
        assert "No processes found" in result

    @patch("psutil.process_iter")
    @patch("thefuzz.fuzz.partial_ratio")
    def test_list_processes_filtering_and_limit(self, mock_fuzz, mock_iter, desktop):
        mock_iter.return_value = [
            create_proc_mock(1, "apple", 1.0, 100 * 1024 * 1024),
            create_proc_mock(2, "apply", 2.0, 200 * 1024 * 1024),
            create_proc_mock(3, "banana", 3.0, 300 * 1024 * 1024),
        ]

        # Mock fuzz.partial_ratio: > 60 for apple/apply, <= 60 for banana
        def side_effect(query, target):
            if "appl" in target.lower(): return 100
            return 0
        mock_fuzz.side_effect = side_effect

        # Test filtering then limit
        # Filtered: apply (200MB), apple (100MB)
        result = desktop.list_processes(name="appl", limit=1)
        assert "Processes (1 shown):" in result
        assert "apply" in result
        assert "apple" not in result
        assert "banana" not in result

    @patch("psutil.process_iter")
    def test_list_processes_sorting_and_limit(self, mock_iter, desktop):
        mock_iter.return_value = [
            create_proc_mock(1, "a", 10.0, 100 * 1024 * 1024),
            create_proc_mock(2, "b", 5.0, 200 * 1024 * 1024),
            create_proc_mock(3, "c", 1.0, 300 * 1024 * 1024),
        ]

        # Sort by CPU (descending), limit 2
        # sorted: a (10.0), b (5.0), c (1.0)
        result = desktop.list_processes(sort_by="cpu", limit=2)
        assert "Processes (2 shown):" in result
        assert "a" in result
        assert "b" in result
        assert "c" not in result

        # Sort by Name (ascending), limit 1
        # sorted: a, b, c
        result = desktop.list_processes(sort_by="name", limit=1)
        assert "Processes (1 shown):" in result
        assert "a" in result
        assert "b" not in result

class TestProcessTool:
    @patch("windows_mcp.analytics.with_analytics", lambda *args, **kwargs: (lambda f: f))
    def test_process_tool_list_limit(self):
        from windows_mcp.tools.process import register

        mcp = MagicMock()
        get_desktop = MagicMock()
        get_analytics = MagicMock()
        desktop_mock = get_desktop.return_value
        desktop_mock.list_processes.return_value = "Mocked List"

        # Capture the tool function
        captured_tool = None
        def mock_tool(*args, **kwargs):
            def decorator(f):
                nonlocal captured_tool
                captured_tool = f
                return f
            return decorator

        mcp.tool.side_effect = mock_tool
        register(mcp, get_desktop=get_desktop, get_analytics=get_analytics)

        # Call the captured tool function
        result = captured_tool(mode="list", limit=5, name="test", sort_by="cpu")

        desktop_mock.list_processes.assert_called_once_with(name="test", sort_by="cpu", limit=5)
        assert result == "Mocked List"
