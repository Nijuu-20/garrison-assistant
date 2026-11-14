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
    assert s.capture.options['draw_border'] is False
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


def test_border_default_compatibility_is_explicit():
    s=GraphicsSession(12345,FakeCapture,draw_border=None)
    assert s.capture.options['draw_border'] is None
    s.stop()


@pytest.mark.parametrize('failure',[None,'constructor','read'])
def test_window_border_request_and_fallback_stay_window_only(monkeypatch,failure):
    from garrison import windows
    calls=[];instances=[];fallbacks=[]
    pixels=np.arange(20*30*3,dtype=np.uint8).reshape(20,30,3)
    class Session:
        def __init__(self,hwnd,draw_border):
            calls.append((hwnd,draw_border))
            if failure=='constructor' and draw_border is False:raise RuntimeError('unsupported border setting')
            self.hwnd=hwnd;self.closed=False;instances.append(self)
        def read(self):
            if failure=='read':raise RuntimeError('stale frame')
            return pixels.copy()
        def stop(self):self.closed=True
    monkeypatch.setattr(windows,'GraphicsSession',Session)
    monkeypatch.setattr(windows,'_validate_window',lambda *args:(30,20))
    monkeypatch.setattr(windows,'_client_image',lambda hwnd,image,*args:image)
    monkeypatch.setattr(windows,'_session',None)
    monkeypatch.setattr(windows,'_border_fallback',False)
    monkeypatch.setattr(windows,'_print_window',lambda hwnd,pid:(fallbacks.append((hwnd,pid)),pixels.copy())[1])
    assert np.array_equal(windows.capture_window(12345,567),pixels)
    assert calls==([(12345,False),(12345,None)] if failure=='constructor' else [(12345,False)])
    assert fallbacks==([(12345,567)] if failure=='read' else [])
    assert windows._border_fallback==(failure=='constructor')
    assert windows._session is None and all(s.closed for s in instances)
