"""Owned, bounded WGC frame buffer; captures one explicit HWND, never a monitor."""
from __future__ import annotations
import threading
import time


class GraphicsSession:
    def __init__(self, hwnd, factory=None):
        if factory is None:
            from windows_capture import WindowsCapture
            factory=WindowsCapture
        self.hwnd=hwnd;self.condition=threading.Condition();self.frame=None
        self.updated=0.;self.closed=False;self.control=None
        self.capture=factory(window_hwnd=hwnd,monitor_index=None,window_name=None,
                             cursor_capture=False,draw_border=None,minimum_update_interval=250)
        @self.capture.event
        def on_frame_arrived(frame, control):
            with self.condition:
                if self.closed:
                    control.stop();return
                # The native buffer's lifetime ends with the callback. Own one
                # BGR copy, replace it atomically and bound memory to one frame.
                self.frame=frame.frame_buffer[:,:,:3].copy()
                self.updated=time.monotonic();self.condition.notify_all()
        @self.capture.event
        def on_closed():
            with self.condition:
                self.closed=True;self.frame=None;self.condition.notify_all()
        self.control=self.capture.start_free_threaded()

    def read(self, timeout=4., max_age=2.5):
        deadline=time.monotonic()+timeout
        with self.condition:
            while not self.closed:
                if self.frame is not None and time.monotonic()-self.updated<=max_age:
                    return self.frame.copy()
                remaining=deadline-time.monotonic()
                if remaining<=0:raise RuntimeError('游戏画面未更新，请恢复游戏窗口后重试')
                self.condition.wait(remaining)
        raise RuntimeError('游戏窗口的画面连接已关闭，请重新连接')

    def peek(self,max_age=2.5):
        with self.condition:
            if self.closed or self.frame is None or time.monotonic()-self.updated>max_age:return None
            return self.frame.copy()

    def stop(self):
        with self.condition:
            self.closed=True;self.frame=None;self.condition.notify_all()
        if self.control is not None:
            control,self.control=self.control,None
            control.stop()
