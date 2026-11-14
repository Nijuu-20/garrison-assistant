import copy
import json
import pytest
from garrison.core import Database,new_state,shop_review_note,fingerprint,recommend
from garrison.advice import overlay_advice
from garrison.recognition import interpret,shop_snapshot,apply_fields,applicable_fields,StabilityGate
from garrison.coach import make_context


@pytest.fixture(scope='module')
def db():return Database()


def field(key,value,score=.99):return {'key':key,'value':value,'confidence':score}


def scene(db):
    fields=[interpret('item:0',[('烈夏',.99)],db),field('cost:0',2),
            interpret('item:1',[('维式重锤',.99)],db),field('cost:1',1),
            interpret('item:2',[],db),field('cost:2',3)]
    layout={'grid_valid':True,'slots':[{'slot':i,'key':f'item:{i}','kind':'unknown'} for i in range(3)],'notes':[]}
    regions=[{'key':f'item:{i}'} for i in range(3)]
    return fields,regions,layout


def test_generic_slot_recovers_operator_and_equipment_without_guessing(db):
    fields,regions,layout=scene(db);snap=shop_snapshot(fields,regions,layout,db)
    assert fields[0]['value']==db.by_name['烈夏']['operator_id']
    assert fields[2]['value']=='维式重锤'
    assert [s['kind'] for s in layout['slots']]==['operator','equipment','unknown']
    assert [r['key'] for r in regions]==['shop:0','offer:1','offer:2']
    assert snap['partial'] and snap['pending_slots']==[2] and not layout['shop_valid']
    assert len(json.loads(snap['value']))==4
    assert interpret('item:4',[('烈厦',.99)],db)['value'] is None


def test_partial_shop_requires_stability_clears_old_unknown_and_informs_ai(db):
    fields,regions,layout=scene(db);snap=shop_snapshot(fields,regions,layout,db)
    state=new_state();state['shop']=[{'op_id':'OP001','slot':2,'cost':3}]
    gate=StabilityGate(2)
    assert not gate.accept([snap],.92)
    apply_fields(state,applicable_fields({'mode':'auto'},gate.accept(fields+[snap],.92)))
    assert state['shop']==[{'op_id':db.by_name['烈夏']['operator_id'],'slot':0,'cost':2}]
    assert state['recognized_offers']=={'1':{'name':'维式重锤','cost':1}}
    assert not state['inventory']
    assert '第 3 格' in shop_review_note(state)
    context=make_context(db,state)
    assert context['shop_observation']=={'partial':True,'pending_slots':[2],'slot_count':3}
    assert context['shop_note']==shop_review_note(state)
    fields[4].update(key='shop:2',value='OP002',confidence=.99);layout['slots'][2].update(key='shop:2',kind='operator')
    full=shop_snapshot(fields,regions,layout,db)
    assert not gate.accept([full],.92)
    apply_fields(state,gate.accept([full],.92))
    assert len(state['shop'])==2 and not shop_review_note(state)


@pytest.mark.parametrize('cause',['geometry','name','price'])
def test_untrusted_geometry_or_pair_cannot_be_published(db,cause):
    fields,regions,layout=scene(db)
    if cause=='geometry':layout['grid_valid']=False
    else:fields[0 if cause=='name' else 1]['confidence']=.91
    snap=shop_snapshot(fields,regions,layout,db)
    if cause=='geometry':assert snap['value'] is None
    else:
        assert snap['pending_slots']==[0,2]
        assert all(f['key'].endswith(':1') for f in json.loads(snap['value']))


def test_manual_slot_lock_survives_partial_update(db):
    fields,regions,layout=scene(db);snap=shop_snapshot(fields,regions,layout,db)
    state=new_state();state['shop']=[{'op_id':'OP001','slot':0,'cost':5}]
    state['field_meta']['shop:0']={'locked':True};old=copy.deepcopy(state['shop'])
    apply_fields(state,[snap])
    assert state['shop']==old and state['field_meta']['shop_snapshot']['uncertain']


def test_partial_shop_advice_is_visible_but_stale_snapshot_is_not(db):
    fields,regions,layout=scene(db);snap=shop_snapshot(fields,regions,layout,db)
    state=new_state();apply_fields(state,[snap])
    state['field_meta']['cost:2']={'uncertain':True}
    result={'fingerprint':fingerprint(state),'goal':'确认商品优先','actions':[]}
    view=overlay_advice(db,state,result,None,True)
    assert view['source']=='AI 分析' and '第 3 格待确认' in view['analysis']
    assert len(recommend(db,state,True))==1
    state['field_meta']['shop_snapshot']['uncertain']=True
    assert overlay_advice(db,state,result,None,True)['source']=='本地攻略'
    assert not recommend(db,state,True)
