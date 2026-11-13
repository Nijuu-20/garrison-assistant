import types
import numpy as np
import pytest
from garrison.capture import GraphicsSession


class FakeCapture:
    def __init__(self,**options):self.options=options;self.events={};self.stopped=False
    def event(self,handler):self.events[handler.__name__]=handler;return handler
    def start_free_threaded(self):return self
    def stop(self):self.stopped=True
    def emit(self,buffer):self.events['on_frame_arrived'](types.SimpleNamespace(frame_buffer=buffer),self)


def test_capture_targets_handle_and_owns_single_frame():
    s=GraphicsSession(12345,FakeCapture)
    assert s.capture.options['window_hwnd']==12345
    assert s.capture.options['monitor_index'] is None and s.capture.options['window_name'] is None
    pixels=np.full((10,20,4),90,np.uint8);s.capture.emit(pixels);pixels[:]=0
    image=s.read(timeout=0);assert image.shape==(10,20,3) and image.min()==90
    image[:]=1;assert s.read(timeout=0).min()==90
    preview=s.peek();preview[:]=2;assert s.peek().min()==90
    s.capture.emit(pixels);assert s.read(timeout=0).max()==0
    s.stop();assert s.frame is None and s.capture.stopped
    assert s.peek() is None
    with pytest.raises(RuntimeError):s.read(timeout=0)


def test_stale_or_closed_capture_is_not_a_fresh_observation():
    s=GraphicsSession(12345,FakeCapture)
    with pytest.raises(RuntimeError):s.read(timeout=0)
    s.capture.emit(np.zeros((10,20,4),np.uint8));s.updated=0
    assert s.peek() is None
    with pytest.raises(RuntimeError):s.read(timeout=0)
    s.capture.events['on_closed']()
    with pytest.raises(RuntimeError):s.read(timeout=0)
    s.stop()
