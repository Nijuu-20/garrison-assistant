import json
import numpy as np
import pytest
from garrison import hud
from garrison.recognition import interpret, vote, Recognizer, StabilityGate, apply_fields, applicable_fields, mark_uncertain
from garrison.core import Database, new_state, recommend, validate_state


@pytest.fixture(scope='module')
def db():return Database()


def word(text,x,y,w=.035,h=.025):
    return {'text':text,'rect':[x,y,w,h],'x':x+w/2,'y':y+h/2,'confidence':.99}


@pytest.mark.parametrize('count,level_x,equipment_slot',[(4,.36,0),(6,.16,3),(7,.08,6)])
def test_shop_tracks_level_position_count_and_equipment(db,count,level_x,equipment_slot):
    words=[word('回合',.36,.03),word('LEVEL',level_x,.8),word('升级',level_x,.9),word('刷新',.94,.65)]
    badges=[[level_x,.75,.025,.034],[.91,.75,.064,.036]]
    start=level_x+.10;pitch=(.85-start)/max(1,count-1)
    for i in range(count):
        bx=start+i*pitch
        name='维式重锤' if i==equipment_slot else ['幽灵鲨','艾丝黛尔','陨星'][i%3]
        words.append(word(name,bx-pitch*.4,.93,min(.045,pitch*.6)))
        badges.append([bx,.75,.025,.034])
    layout=hud.locate(words,badges,db)
    assert layout['valid'] and layout['shop_valid']
    assert len(layout['slots'])==count
    assert layout['slots'][equipment_slot]['kind']=='equipment'
    assert all(s['kind']=='operator' for s in layout['slots'] if s['slot']!=equipment_slot)
    region=next(r for r in layout['regions'] if r['key']=='level')
    assert abs(region['rect'][0]-level_x)<.001


def test_unrelated_hud_and_hidden_shop_abstain(db):
    words=[word('规程等级15',.1,.02),word('23',.6,.03),word('幽灵鲨',.8,.9)]
    assert not hud.locate(words,[],db)['valid']


@pytest.mark.parametrize('roman,value',[('Ⅰ',1),('II',2),('Ⅲ',3),('IV',4),('Ⅴ',5),('VI',6),('已满级',6)])
def test_roman_levels(db,roman,value):
    assert interpret('level',[(roman,.99)],db)['value']==value


def test_digit_vote_refuses_conflicts_and_ambiguous_region(db):
    assert vote('gold',[('6',.999),('8',.99)],db)['value'] is None
    assert vote('gold',[('6',.999)],db)['value'] is None
    assert vote('gold',[('6',.999),('6',.999),('16',.7)],db)['value']==6
    assert vote('gold',[('18 / 20',.99),('18',.99),('18',.99)],db)['value'] is None


def snapshot(values):
    return {'key':'shop_snapshot','value':json.dumps([{'key':k,'value':v} for k,v in values.items()]),'confidence':.99}


def test_snapshot_reorders_equipment_removes_old_slots_and_never_adds_inventory(db):
    s=new_state();s['shop']=[{'op_id':'OP001','slot':5,'cost':5}]
    f=snapshot({'shop:0':'OP003','cost:0':2,'offer:1':'维式重锤','cost:1':1})
    apply_fields(s,[f])
    assert s['shop']==[{'op_id':'OP003','slot':0,'cost':2}]
    assert s['recognized_offers']=={'1':{'name':'维式重锤','cost':1}}
    assert s['inventory']==[] and s['recognized_inventory']=={}
    assert validate_state(s,db)['recognized_offers']==s['recognized_offers']
    f=snapshot({'offer:0':'维式重锤','cost:0':1,'shop:1':'OP003','cost:1':2})
    apply_fields(s,[f]);assert s['shop'][0]['slot']==1
    assert list(s['recognized_offers'])==['0']


def test_unstable_or_missing_shop_blocks_old_recommendations(db):
    s=new_state();apply_fields(s,[snapshot({'shop:0':'OP003','cost:0':2})])
    accepted=[{'key':'shop:0','value':'OP002','confidence':.99}]
    apply_fields(s,applicable_fields({'mode':'auto'},accepted))
    assert s['shop'][0]['op_id']=='OP003'
    mark_uncertain(s,[{'key':'shop_snapshot','value':None,'confidence':0}],.92)
    assert recommend(db,s,True)==[]


def test_snapshot_respects_manual_locks():
    s=new_state();apply_fields(s,[snapshot({'shop:0':'OP003','cost:0':2})])
    s['field_meta']['shop:0']['locked']=True
    apply_fields(s,[snapshot({'shop:0':'OP002','cost:0':1})])
    assert s['shop'][0]['op_id']=='OP003'
    assert s['field_meta']['shop_snapshot']['uncertain']


def test_maximum_level_works_without_level_label_and_clears_old_cost(db):
    layout=hud.locate([word('回合',.36,.03),word('已满级',.12,.91),word('刷新',.94,.65)],[],db)
    assert layout['valid']
    assert any(r['key']=='level' and r['seed']['text']=='已满级' for r in layout['regions'])
    assert not any(r['key']=='upgrade_cost' for r in layout['regions'])
    s=new_state();s.update(level=5,upgrade_cost=12)
    apply_fields(s,[{'key':'level','value':6,'confidence':.99},{'key':'upgrade_cost','value':12,'confidence':.99}])
    assert s['level']==6 and s['upgrade_cost'] is None


def test_roman_shape_rejects_frame_and_v():
    crop=np.full((60,60,3),180,np.uint8);crop[10:42,26:35]=20
    assert hud.roman_bars(crop)==1
    crop[:]=180;crop[0:50,26:35]=20
    assert hud.roman_bars(crop) is None
