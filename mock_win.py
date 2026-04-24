import sys
class MockWinreg:
    HKEY_CLASSES_ROOT = None
    def OpenKey(self, *args, **kwargs):
        class Ctx:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return Ctx()
    def EnumKey(self, *args): raise OSError()

sys.modules['winreg'] = MockWinreg()

class MockWin32:
    def __getattr__(self, name):
        return MockWin32()
    def __call__(self, *args, **kwargs):
        pass

sys.modules['pywintypes'] = MockWin32()
sys.modules['win32process'] = MockWin32()
sys.modules['win32gui'] = MockWin32()
sys.modules['win32con'] = MockWin32()
sys.modules['win32clipboard'] = MockWin32()
sys.modules['win32api'] = MockWin32()
sys.modules['win32com'] = MockWin32()
sys.modules['win32com.shell'] = MockWin32()

class MockComtypes:
    def __getattr__(self, name):
        return MockComtypes()
    def __call__(self, *args, **kwargs):
        return MockComtypes()
sys.modules['comtypes'] = MockComtypes()
sys.modules['comtypes.client'] = MockComtypes()
sys.modules['comtypes.automation'] = MockComtypes()

import ctypes
import _ctypes
_ctypes.COMError = Exception
ctypes.HRESULT = ctypes.c_long
ctypes.wintypes = MockComtypes()
ctypes.windll = MockComtypes()
ctypes.oledll = MockComtypes()
ctypes.WINFUNCTYPE = lambda *args: lambda x: x
