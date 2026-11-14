"""Exercise production callbacks with queued jobs; no window or capture is opened."""
import copy
import time
from types import SimpleNamespace
import numpy as np
import pytest
from garrison import ui
from garrison.core import new_state,fingerprint
from garrison.recognition import StabilityGate,apply_fields
from garrison.battle import observation_fields


def observed():
    return observation_fields({'detections':[dict(track_id='one',op_id='OP001',name='测试',zone='field',
        rect=[.4,.3,.05,.1],reliable=True,confidence=.96,matches=12,correlation=.8)]})


def setup():
    state=new_state();state.update(round=3,phase='整备')
    jobs=[];notices=[];refresh=[]
    result={'time':time.time(),'regions':[], 'fields':[{'key':k,'value':state[k],'confidence':.99} for k in ('round','phase')]}
    battle={'fields':observed(),'regions':[],'battlefield':{'active':True}}
    window=SimpleNamespace(store=SimpleNamespace(state=state),live=True,battle_busy=False,capture_busy=False,capture_generation=2,
        settings={'battle_enabled':True,'recognition_threshold':.92,'auto_apply':True},review_opening=False,
        battle_gate=StabilityGate(2),gate=StabilityGate(2),last_recognition=copy.deepcopy(result),
        recognizer=SimpleNamespace(recognize_battle=lambda *args:battle),
        canvas=SimpleNamespace(update=lambda:None,regions=[]),refresh_all=lambda:refresh.append(True),
        maybe_auto_analyze=lambda:None,notify=notices.append,
        run_job=lambda work,success,failure,done:jobs.append((work,success,failure,done)))
    return window,result,jobs,notices,refresh


def finish(job):
    work,success,failure,done=job
    try:success(work())
    finally:done()


def test_sprite_queue_is_bounded_and_separate_from_shop_gate():
    w,result,jobs,_,_=setup();w.gate.accept(result['fields'],.92)
    old=copy.deepcopy(w.gate.counts)
    ui.MainWindow.queue_battle_recognition(w,None,result,{})
    ui.MainWindow.queue_battle_recognition(w,None,result,{})
    assert len(jobs)==1 and w.battle_busy and not w.capture_busy
    finish(jobs.pop());assert not w.store.state['units'] and w.gate.counts==old
    # A newer shop image must never receive delayed sprite boxes.
    w.last_recognition={**result,'time':result['time']+1,'fields':[]}
    ui.MainWindow.queue_battle_recognition(w,None,result,{})
    finish(jobs.pop())
    assert len(w.store.state['units'])==1 and w.gate.counts==old
    assert w.last_recognition['fields']==[] and not w.battle_busy


@pytest.mark.parametrize('change',['generation','session','manual_roster','pause','round','phase','expired','review'])
def test_delayed_battle_does_not_overwrite_changed_state(change):
    w,result,jobs,_,refresh=setup();w.battle_gate=StabilityGate(1)
    if change=='expired':result['time']-=11
    ui.MainWindow.queue_battle_recognition(w,None,result,{})
    if change=='generation':w.capture_generation+=1
    elif change=='session':w.store.state['session_id']='new'
    elif change=='manual_roster':apply_fields(w.store.state,observed(),True)
    elif change=='pause':w.live=False
    elif change=='round':w.store.state['round']=4
    elif change=='phase':w.store.state['phase']='作战'
    elif change=='review':w.review_opening=True
    before=copy.deepcopy(w.store.state);finish(jobs.pop())
    assert w.store.state==before and not refresh and not w.battle_busy


def test_battle_failure_keeps_roster_and_does_not_stop_shop():
    w,result,jobs,notices,_=setup();apply_fields(w.store.state,observed())
    ui.MainWindow.queue_battle_recognition(w,None,result,{})
    jobs[0][2]('test failure');jobs[0][3]()
    assert w.store.state['units'][0]['sprite_missing']
    assert not w.capture_busy and not w.battle_busy and w.live and notices


@pytest.mark.parametrize('concurrent_change',['battle','gold'])
def test_shop_result_not_dropped_by_concurrent_roster_update(monkeypatch,concurrent_change):
    w,result,jobs,_,_=setup();received=[];profiles=[]
    frame=np.zeros((8,12,3),np.uint8)
    monkeypatch.setattr(ui,'capture_window',lambda *args,**kwargs:frame)
    w.window_combo=SimpleNamespace(currentData=lambda:{'hwnd':123,'pid':456})
    w.active_profile=lambda:{};w.set_frame=lambda *args,**kwargs:None
    w.receive_recognition=lambda res,before:received.append(before==fingerprint(w.store.state))
    w.queue_battle_recognition=lambda *args:None
    w.recognizer.recognize=lambda frame,profile:(profiles.append(profile),copy.deepcopy(result))[1]
    w.battle_busy=True
    ui.MainWindow.capture_once(w)
    payload=jobs[0][0]()
    if concurrent_change=='battle':apply_fields(w.store.state,observed())
    else:w.store.state['gold']=99
    jobs[0][1](payload);jobs[0][3]()
    assert profiles[0]['battle_enabled'] is False
    assert received==[concurrent_change=='battle'] and not w.capture_busy


@pytest.mark.parametrize('uncertain',[False,True])
def test_auto_coach_accepts_only_stable_partial_shop(uncertain):
    w,result,_,_,_=setup();calls=[]
    keys=['phase','round','gold','level','shop:0','cost:0','offer:1','cost:1','shop_snapshot']
    w.last_recognition={'fields':[{'key':k} for k in keys]}
    w.store.state['field_meta']={k:{'time':time.time(),'uncertain':False} for k in keys}
    w.store.state['field_meta']['offer:1']['uncertain']=True
    w.store.state['field_meta']['shop_snapshot'].update(partial=True,pending_slots=[1],slot_count=2,uncertain=uncertain)
    w.visible_opening=lambda:None;w.ai_busy=False;w.auto_keys=set();w.coach=SimpleNamespace(last_started=0)
    w.settings.update(ai_enabled=True,ai_auto=True,ai_on_change=True,ai_min_interval=1)
    w.analyze=lambda **kwargs:calls.append(kwargs)
    ui.MainWindow.maybe_auto_analyze(w)
    assert bool(calls)==(not uncertain)
