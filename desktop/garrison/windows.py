"""Native desktop services for the application. Capture only; never inject game input."""
import ctypes
from ctypes import wintypes as w
import os
import atexit
import threading
import numpy as np
from .capture import GraphicsSession

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.GetDC.argtypes = [w.HWND]; user32.GetDC.restype = w.HDC
user32.GetWindowDC.argtypes = [w.HWND]; user32.GetWindowDC.restype = w.HDC
user32.ReleaseDC.argtypes = [w.HWND, w.HDC]
user32.PrintWindow.argtypes = [w.HWND, w.HDC, w.UINT]
user32.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user32.IsWindow.argtypes = [w.HWND]; user32.IsIconic.argtypes = [w.HWND]
user32.IsWindowVisible.argtypes = [w.HWND]
user32.GetWindowTextLengthW.argtypes = [w.HWND]
user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
gdi32.CreateCompatibleDC.argtypes = [w.HDC]; gdi32.CreateCompatibleDC.restype = w.HDC
gdi32.CreateCompatibleBitmap.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int]; gdi32.CreateCompatibleBitmap.restype = w.HBITMAP
gdi32.SelectObject.argtypes = [w.HDC, w.HGDIOBJ]; gdi32.SelectObject.restype = w.HGDIOBJ
gdi32.DeleteObject.argtypes = [w.HGDIOBJ]; gdi32.DeleteDC.argtypes = [w.HDC]


def enum_windows():
    result = []
    @ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length: return True
        title = ctypes.create_unicode_buffer(length + 1); user32.GetWindowTextW(hwnd, title, length + 1)
        pid = w.DWORD(); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid(): return True
        rect = w.RECT(); user32.GetClientRect(hwnd, ctypes.byref(rect))
        if rect.right < 200 or rect.bottom < 150: return True
        result.append({'hwnd': int(hwnd), 'pid': pid.value, 'title': title.value,
                       'width': rect.right, 'height': rect.bottom})
        return True
    user32.EnumWindows(callback, 0)
    return result


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('width', w.LONG), ('height', w.LONG), ('planes', w.WORD),
                ('bits', w.WORD), ('compression', w.DWORD), ('image_size', w.DWORD),
                ('x', w.LONG), ('y', w.LONG), ('used', w.DWORD), ('important', w.DWORD)]


gdi32.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.POINTER(BitmapInfoHeader), w.UINT]


def _validate_window(hwnd, expected_pid=None):
    if not user32.IsWindow(hwnd): raise RuntimeError('游戏窗口已关闭，请重新选择')
    if user32.IsIconic(hwnd): raise RuntimeError('游戏窗口已最小化，识别已暂停')
    pid = w.DWORD(); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if expected_pid and pid.value != expected_pid: raise RuntimeError('窗口已变更，请重新选择')
    rect = w.RECT(); user32.GetClientRect(hwnd, ctypes.byref(rect)); width, height = rect.right, rect.bottom
    if not (100 <= width <= 8192 and 100 <= height <= 8192): raise RuntimeError('窗口尺寸不可用')
    return width,height


_session=None
_session_lock=threading.Lock()


def stop_capture():
    global _session
    with _session_lock:
        session,_session=_session,None
    if session is not None:
        try:session.stop()
        except RuntimeError:pass


atexit.register(stop_capture)


def _client_image(hwnd,image,width,height):
    if image.shape[:2]==(height,width):return image
    # WGC includes a normal window's caption/frame. Align its visible DWM
    # bounds to the client origin rather than stretching the non-client area.
    bounds=w.RECT();point=w.POINT(0,0)
    user32.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    dwm=ctypes.windll.dwmapi
    dwm.DwmGetWindowAttribute.argtypes=[w.HWND,w.DWORD,ctypes.c_void_p,w.DWORD]
    if dwm.DwmGetWindowAttribute(hwnd,9,ctypes.byref(bounds),ctypes.sizeof(bounds)) or not user32.ClientToScreen(hwnd,ctypes.byref(point)):
        raise RuntimeError('窗口边框尺寸不可用，请使用无边框窗口')
    bw,bh=bounds.right-bounds.left,bounds.bottom-bounds.top
    if bw<=0 or bh<=0:raise RuntimeError('游戏窗口尺寸正在变化，请稍后重试')
    sx,sy=image.shape[1]/bw,image.shape[0]/bh
    x,y=round((point.x-bounds.left)*sx),round((point.y-bounds.top)*sy)
    cw,ch=round(width*sx),round(height*sy)
    if x<0 or y<0 or x+cw>image.shape[1] or y+ch>image.shape[0]:
        raise RuntimeError('游戏窗口尺寸正在变化，请稍后重试')
    return image[y:y+ch,x:x+cw].copy()


def capture_window(hwnd, expected_pid=None, keep_alive=False):
    global _session
    width,height=_validate_window(hwnd,expected_pid)
    try:
        with _session_lock:
            old=None
            if _session is None or _session.hwnd!=hwnd or _session.closed:
                old,_session=_session,None
                if old:old.stop()
                _session=GraphicsSession(hwnd)
            session=_session
        image=session.read()
        width,height=_validate_window(hwnd,expected_pid)
        image=_client_image(hwnd,image,width,height)
        if float(image.std())<3:raise RuntimeError('游戏返回空白画面，请恢复窗口')
        return image
    except (RuntimeError,ImportError,OSError) as error:
        stop_capture()
        # Compatibility path remains window-only; never read the desktop when
        # the target is occluded or its Graphics Capture connection fails.
        try:return _print_window(hwnd,expected_pid)
        except RuntimeError as fallback:
            raise RuntimeError(f'游戏窗口截取失败：{error}；请保持窗口打开或使用无边框模式') from fallback
    finally:
        if not keep_alive:stop_capture()


def _print_window(hwnd,expected_pid=None):
    width,height=_validate_window(hwnd,expected_pid)
    dc = user32.GetDC(hwnd); mem = gdi32.CreateCompatibleDC(dc)
    bmp = gdi32.CreateCompatibleBitmap(dc, width, height); old = gdi32.SelectObject(mem, bmp)
    try:
        if not user32.PrintWindow(hwnd, mem, 3): raise RuntimeError('无法截取窗口，请使用窗口化或导入截图')
        info = BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader), width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
        buffer = (ctypes.c_ubyte * (width * height * 4))()
        gdi32.SelectObject(mem, old)
        if not gdi32.GetDIBits(mem, bmp, 0, height, buffer, ctypes.byref(info), 0):
            raise RuntimeError('读取窗口图像失败')
        image = np.frombuffer(buffer, dtype=np.uint8).reshape(height, width, 4)[:, :, :3].copy()
        if float(image.std()) < 3: raise RuntimeError('检测到黑屏或空白；请切换窗口化模式或导入截图')
        return image
    finally:
        gdi32.SelectObject(mem, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem); user32.ReleaseDC(hwnd, dc)


def set_capture_excluded(hwnd):
    # Keep helper windows out of captured screen streams where Windows supports it.
    user32.SetWindowDisplayAffinity.argtypes = [w.HWND, w.DWORD]
    user32.SetWindowDisplayAffinity(hwnd, 0x11)


def client_geometry(hwnd,expected_pid=None):
    width,height=_validate_window(hwnd,expected_pid)
    if not user32.IsWindowVisible(hwnd):return None
    user32.GetForegroundWindow.restype=w.HWND
    foreground=user32.GetForegroundWindow()
    if foreground!=hwnd:return None
    point=w.POINT(0,0);user32.ClientToScreen.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    if not user32.ClientToScreen(hwnd,ctypes.byref(point)):return None
    return (point.x,point.y,width,height)


def place_highlight(hwnd,geometry):
    # Physical client pixels, including negative monitor origins; Qt paints in
    # its own logical coordinates after the native move/resize notification.
    user32.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
    user32.SetWindowPos(hwnd,-1,*geometry,0x0010|0x0040)  # NOACTIVATE | SHOWWINDOW


def peek_capture(hwnd,expected_pid=None):
    # Never starts capture or falls back to the desktop. Read the existing
    # user-started session only; do not wait for a frame on the UI thread.
    if not _session_lock.acquire(blocking=False):return None
    try:session=_session
    finally:_session_lock.release()
    if session is None or session.hwnd!=hwnd:return None
    image=session.peek()
    if image is None:return None
    try:
        width,height=_validate_window(hwnd,expected_pid)
        return _client_image(hwnd,image,width,height)
    except RuntimeError:return None


def parse_hotkey(sequence):
    parts = sequence.upper().replace('CONTROL', 'CTRL').split('+')
    modifiers = 0x4000  # MOD_NOREPEAT
    for p in parts[:-1]:
        if p not in ('CTRL', 'ALT', 'SHIFT'): raise ValueError('快捷键仅支持 Ctrl、Alt、Shift 组合')
        modifiers |= {'CTRL': 2, 'ALT': 1, 'SHIFT': 4}[p]
    if modifiers == 0x4000: raise ValueError('请包含 Ctrl、Alt 或 Shift，避免干扰游戏按键')
    key = parts[-1]
    special = {'SPACE': 32, 'TAB': 9, 'HOME': 36, 'END': 35, 'INSERT': 45, 'DELETE': 46}
    if key in special: vk = special[key]
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24: vk = 111 + int(key[1:])
    elif len(key) == 1 and key.isascii() and key.isalnum(): vk = ord(key)
    else: raise ValueError('请选择字母、数字、空格或功能键')
    return modifiers, vk


class Hotkeys:
    def __init__(self, hwnd):
        self.hwnd = hwnd; self.registered = {}; self.sequences = {}
        user32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
        user32.UnregisterHotKey.argtypes = [w.HWND, ctypes.c_int]

    def configure(self, entries):
        parsed = {i: parse_hotkey(seq) for i, seq in entries.items()}
        if len(set(parsed.values())) != len(parsed): raise ValueError('快捷键重复，请分别设置')
        previous = self.sequences.copy(); self.clear()
        for i, (mods, key) in parsed.items():
            if not user32.RegisterHotKey(self.hwnd, i, mods, key):
                self.clear()
                for j, seq in previous.items():
                    m, k = parse_hotkey(seq)
                    if user32.RegisterHotKey(self.hwnd, j, m, k): self.registered[j] = True
                self.sequences = previous
                raise ValueError(f'{entries[i]} 已被占用；已恢复此前可用快捷键')
            self.registered[i] = True
        self.sequences = entries.copy()

    def clear(self):
        for i in self.registered: user32.UnregisterHotKey(self.hwnd, i)
        self.registered.clear()
