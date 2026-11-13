import copy,json,time
import numpy as np
import pytest
from pathlib import Path
from garrison.core import Database,new_state,fingerprint
from garrison.coach import normalize_result,make_context
from garrison.advice import analysis_text,ban_context
from garrison.tracking import normalize_items,item_key,current_candidates,ShopWatch,same_shop_pixels,valid_rect
from garrison.storage import Storage

@pytest.fixture(scope='module')
def db():return Database()

def observation(db,oid='OP001',kind='operator',slot=0,rect=None):
    rect=rect or [.30,.75,.12,.22];key=('shop:' if kind=='operator' else 'offer:')+str(slot)
    value=oid if kind=='operator' else next(iter(db.equipment))
    return {'mode':'auto','layout_valid':True,'size':[2048,1152],
            'fields':[{'key':key,'value':value,'confidence':.99}],
            'regions':[{'key':key,'rect':[rect[0]+.01,.93,.08,.03]}],
            'shop_slots':[{'key':key,'slot':slot,'kind':kind,'rect':rect}]}

def test_normalized_list_is_explicit_typed_database_only(db):
    gear=next(iter(db.equipment));op={'kind':'operator','op_id':'OP001'}
    result=normalize_items(db,[op,op,{'kind':'operator','name':db.ops['OP002']['name']},
       {'kind':'operator','op_id':'FAKE'},{'kind':'equipment','name':gear+' · 进阶'},
       {'kind':'equipment','name':gear},{'kind':'equipment','name':[]},'buy OP001',None])
    assert len(result)==2 and result[0]['name']==db.ops['OP001']['name'] and result[1]['name']==gear

def test_bans_filter_ai_list_and_catalog(db):
    opening=json.loads((Path(__file__).parents[1]/'build/opening-recognition/solo-result.json').read_text('utf8'))['opening']
    state=new_state();state['opening']=opening;c=ban_context(db,state)
    banned=c['banned_operators'][0]['op_id'];available=c['available_operator_ids'][0]
    raw={'goal':'保持当前阵容','actions':[],'recommendation_list':[{'kind':'operator','op_id':banned},{'kind':'operator','op_id':available}]}
    result=normalize_result(raw,db,state)
    assert [i['op_id'] for i in result['recommendation_list']]==[available]
    ctx=make_context(db,state,tracked=[{'kind':'operator','op_id':banned}])
    assert banned not in [i['op_id'] for i in ctx['recommendation_catalog']['operators']]
    assert ctx['player_tracking'][0]['op_id']==banned and ctx['ban_constraints']['banned_operators']
    assert len(ctx['recommendation_catalog']['equipment'])==len(db.equipment)

def test_list_is_not_in_advice_or_automatically_tracked(db):
    state=new_state();raw={'goal':'先核对商店','actions':[],
        'recommendation_list':[{'kind':'equipment','name':next(iter(db.equipment)),'reason':'PRIVATE_LIST_REASON'}]}
    result=normalize_result(raw,db,state);result['fingerprint']=fingerprint(state)
    assert 'PRIVATE_LIST_REASON' not in analysis_text(db,state,result)
    assert raw['recommendation_list'][0]['name'] not in analysis_text(db,state,result)
    assert current_candidates(db,state,result)
    state['gold']=8
    assert not current_candidates(db,state,result)
    assert not current_candidates(db,new_state(),result,False)

def test_unknown_bans_annotated_and_legacy_reply_supported(db):
    s=new_state();r=normalize_result({'goal':'核对','actions':[],'recommendation_list':[{'kind':'operator','op_id':'OP001'}]},db,s)
    assert '待确认' in r['recommendation_list'][0]['reason']
    assert normalize_result({'goal':'核对','actions':[]},db,s)['recommendation_list']==[]

def test_tracking_survives_storage_and_is_outside_tactical_fingerprint(db,tmp_path,monkeypatch):
    monkeypatch.setenv('GARRISON_DATA_DIR',str(tmp_path));store=Storage();s=new_state();before=fingerprint(s)
    items=normalize_items(db,[{'kind':'operator','op_id':'OP001'},{'kind':'equipment','name':next(iter(db.equipment))}])
    store.save_tracking(items)
    assert Storage().tracking==items and fingerprint(s)==before
    store.save_tracking(items[1:]);assert Storage().tracking==items[1:]

@pytest.mark.parametrize('kind',['operator','equipment'])
def test_current_shop_highlights_require_repeat_and_expire_when_absent(db,kind):
    gate=ShopWatch();r=observation(db,kind=kind)
    assert not gate.accept(db,r)
    stable=gate.accept(db,r);assert len(stable)==1
    assert gate.matches(stable) and not gate.matches([])
    r['fields'][0]['value']=None
    assert not gate.accept(db,r) and not gate.matches(stable)

def test_identity_position_type_and_confidence_are_independent_guards(db):
    gate=ShopWatch();r=observation(db);gate.accept(db,r);gate.accept(db,r)
    moved=observation(db,rect=[.46,.75,.12,.22]);assert not gate.accept(db,moved)
    assert gate.accept(db,moved)
    swapped=observation(db,'OP002',rect=[.46,.75,.12,.22]);assert not gate.accept(db,swapped)
    gear=observation(db,kind='equipment');assert not gate.accept(db,gear);assert gate.accept(db,gear)
    gear['fields'][0]['confidence']=.91;assert not gate.accept(db,gear)

def test_shop_closure_opening_and_resize_missing_layout_clear(db):
    for change in ({'layout_valid':False},{'opening':{'mode':'solo'}},{'shop_slots':[]}):
        gate=ShopWatch();r=observation(db);gate.accept(db,r);gate.accept(db,r)
        assert not gate.accept(db,{**r,**change})

def test_real_frame_dynamic_slot_rects(db):
    from garrison.hud import locate,price_badges
    import cv2
    from PIL import Image
    root=Path(__file__).parents[1]/'build/recognition-real'
    for fixture in ('pc-round3','pc-level5','pc-level6'):
        result=json.loads((root/f'{fixture}-result-2048.json').read_text('utf8'))
        frame=cv2.cvtColor(np.array(Image.open(root/(fixture+'.png')).convert('RGB')),cv2.COLOR_RGB2BGR)
        layout=locate(result['words'],price_badges(frame),db,frame.shape[1]/frame.shape[0])
        assert len(layout['slots'])==(4 if fixture=='pc-round3' else 6)
        assert all(valid_rect(s['rect']) for s in layout['slots'])
        for slot in layout['slots']:
            x,y,w,h=slot['rect'];name=next(r['rect'] for r in layout['regions'] if r['key']==slot['key'])
            assert x<name[0]+name[2]/2<x+w and y<name[1]+name[3]/2<y+h

def test_fast_pixels_reject_refresh_and_accept_animated_portrait(db):
    rng=np.random.default_rng(3);frame=rng.integers(0,256,(400,800,3),dtype=np.uint8)
    rows=[{'sample_rect':[.3,.9,.12,.05]}]
    assert same_shop_pixels(frame,frame,rows)
    changed=frame.copy();changed[:300]=0
    assert same_shop_pixels(changed,frame,rows)
    changed[360:380,240:336]=0
    assert not same_shop_pixels(changed,frame,rows)
    assert not same_shop_pixels(None,frame,rows)
    assert not same_shop_pixels(frame[:200],frame,rows)

@pytest.mark.parametrize('rect',[[0,0,1,1],[0,0,0,1],[-.1,0,.1,1],[0,0,float('nan'),1],[.9,0,.2,1],None])
def test_rectangle_bounds(rect):assert valid_rect(rect)==(rect==[0,0,1,1])
