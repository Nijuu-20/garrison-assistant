import copy
import json
import time
import pytest
from garrison.core import *
from garrison.recognition import exact_entity, interpret, StabilityGate, apply_fields, ready_for_auto
from garrison.storage import Storage, protect
from garrison.windows import parse_hotkey
from garrison.coach import endpoint

@pytest.fixture(scope='module')
def db():return Database()

def oid(db,name):return db.by_name[name]['operator_id']
def status(db,s,name):return next(c for c in covenant_status(db,s) if c['name']==name)
def member(db,cv):return [o['operator_id'] for o in db.ops.values() if cv in o['covenants']]

def test_data_links_and_search(db):
    assert len(db.ops)==143 and len(db.skills)==360
    assert '折桠' in [x['name'] for x in db.search('zy')]
    assert all(x['tier']==2 for x in db.search(tier=2))

def test_duplicate_covenants_do_not_double_count(db):
    s=new_state();a=member(db,'谢拉格')[0];s['units']=[unit(a),unit(a),unit(a)]
    assert status(db,s,'谢拉格')['count']==1
    assert not status(db,s,'谢拉格')['active']

@pytest.mark.parametrize('cv',['远见','奇迹','投资人'])
def test_bench_economic_covenants(db,cv):
    s=new_state();c=next(c for c in db.covenants if c['name']==cv)
    s['units']=[unit(x,'bench') for x in member(db,cv)[:c['activation_count']]]
    assert status(db,s,cv)['active']

def test_bench_does_not_activate_core(db):
    s=new_state();s['units']=[unit(x,'bench') for x in member(db,'谢拉格')[:6]]
    assert status(db,s,'谢拉格')['count']==0

def test_lone_duplicate_disables(db):
    s=new_state();a=member(db,'独行')[0];s['units']=[unit(a)]
    assert status(db,s,'独行')['active']
    s['units'].append(unit(a));assert not status(db,s,'独行')['active']

def test_elite_counts_and_bench(db):
    s=new_state();a=next(iter(db.ops));s['units']=[unit(a,elite=True),unit(a,elite=True),unit(a,'bench',True)]
    assert status(db,s,'绝技')['count']==2 and status(db,s,'绝技')['active']

def test_harmony_does_not_activate_absent_core(db):
    s=new_state();s['units']=[unit(member(db,'调和')[0])]
    c=status(db,s,'谢拉格')
    if c['count']==0:assert c['effective']==0

def test_formulas_are_arithmetic_only():
    assert safe_formula('23+0.9×层数',100)==113
    assert '【113】' in evaluated_effect('攻击+(23+0.9×层数)%',100)
    with pytest.raises(ValueError):safe_formula('__import__("os").system("echo nope")',0)

def test_cost_discount(db):
    s=new_state();a=member(db,'远见')[0];s['stacks']['远见']=150
    assert cost_for(db,s,a)==max(0,db.ops[a]['recruit_cost']-2)
    assert cost_for(db,s,a,3)==3

def test_sequential_budget_and_repeated_purchase(db):
    s=new_state();a=next(iter(db.ops));s.update(gold=5,upgrade_cost=3,level=2,shop=[{'op_id':a,'cost':3}])
    rows=validate_actions(db,s,[{'type':'buy','slot':0},{'type':'upgrade'},{'type':'buy','slot':0}])
    assert [r['valid'] for r in rows]==[True,False,False]
    assert rows[-1]['balance_after']==2
    assert s['gold']==5

def test_unknown_price_rejected_and_refresh_invalidates_shop(db):
    s=new_state();a=next(iter(db.ops));s.update(gold=9,refresh_cost=0,shop=[{'op_id':a,'cost':None}])
    assert not validate_actions(db,s,[{'type':'buy','slot':0}])[0]['valid']
    s['shop'][0]['cost']=2
    result=validate_actions(db,s,[{'type':'refresh'},{'type':'buy','slot':0},{'type':'refresh'}])
    assert [r['valid'] for r in result]==[True,False,False]

def test_promote_uses_initial_copies_only(db):
    s=new_state();a=oid(db,'星极');s['units']=[unit(a),unit(a,elite=True)]
    assert not validate_actions(db,s,[{'type':'promote','op_id':a}])[0]['valid']
    s['units'].append(unit(a));assert validate_actions(db,s,[{'type':'promote','op_id':a}])[0]['valid']

def test_equip_capacity_and_inventory(db):
    s=new_state();u=unit(next(iter(db.ops)));s['units']=[u];e=next(iter(db.equipment))+' · 进阶';s['inventory']=[e]*3
    actions=[{'type':'equip','uid':u['uid'],'equipment':e}]*3
    assert [r['valid'] for r in validate_actions(db,s,actions)]==[True,True,False]

def test_duplicate_equipment_upgrades_and_consumables_rejected(db):
    s=new_state();u=unit('OP001');s['units']=[u];e='维式重锤';s['inventory']=[e,e]
    equip_item(db,s,u['uid'],e);equip_item(db,s,u['uid'],e)
    assert u['equipment']==[e+' · 进阶'] and not s['inventory']
    consumable=next((n for n,v in db.equipment.items() if v['consumable']),None)
    if consumable:
        s['inventory']=[consumable]
        with pytest.raises(ValueError):equip_item(db,s,u['uid'],consumable)

def test_uncertain_purchase_not_marked_executable(db):
    s=new_state();s.update(gold=9,shop=[{'op_id':'OP001','cost':2}]);s['field_meta']['shop:0']={'uncertain':True}
    assert not validate_actions(db,s,[{'type':'buy','slot':0}])[0]['valid']

def test_unknown_actions_rejected(db):
    assert not validate_actions(db,new_state(),[{'type':'sell','op_id':'OP001'}])[0]['valid']

def test_shop_identity_guard(db):
    s=new_state();s.update(gold=9,shop=[{'op_id':'OP001','cost':2}])
    assert not validate_actions(db,s,[{'type':'buy','slot':0,'op_id':'OP002'}])[0]['valid']

def test_crafting_counts(db):
    r=db.raw['equipment_recipes'][0]
    assert not craft_options(db,[r['component_a']])[0]['ready']
    assert craft_options(db,[r['component_a'],r['component_b']])[0]['ready']

def test_undo_redo_and_transaction():
    store=StateStore();store.change(lambda s:s.update(gold=10));assert store.undo();assert store.state['gold'] is None
    assert store.redo();assert store.state['gold']==10
    def fail(s):s['gold']=99;raise ValueError()
    with pytest.raises(ValueError):store.change(fail)
    assert store.state['gold']==10

def test_import_validation(db):
    s=new_state();s['units']=[unit('unknown')]
    with pytest.raises(ValueError):validate_state(s,db)
    s=new_state();s['gold']=-10
    with pytest.raises(ValueError):validate_state(s,db)
    s=new_state();s['units']=[unit('OP001')];s['units'][0]['capacity']=4
    with pytest.raises(ValueError):validate_state(s,db)

def test_entity_matching_abstains(db):
    assert exact_entity('折桠',db.by_name)=='折桠'
    assert exact_entity('山地行动',db.by_name) is None
    assert exact_entity('折桠 角峰',db.by_name) is None

def test_numeric_ambiguity(db):
    assert interpret('gold',[('资金 18',.98)],db)['value']==18
    assert interpret('gold',[('资金 18 / 20',.99)],db)['value'] is None
    assert interpret('level',[('等级 9',.99)],db)['value'] is None

def test_stability_and_confidence():
    gate=StabilityGate(2);f={'key':'gold','value':10,'confidence':.99}
    assert not gate.accept([f],.92);assert gate.accept([f],.92)
    assert not gate.accept([{**f,'value':11}],.92)
    assert not gate.accept([{**f,'confidence':.6}],.92)
    assert not gate.accept([f],.92)
    gate.reset();assert not gate.accept([f],.92)

def test_partial_updates_and_manual_lock(db):
    s=new_state();s['gold']=15;s['field_meta']['gold']={'locked':True}
    f={'key':'gold','value':9,'confidence':.99}
    apply_fields(s,[f]);assert s['gold']==15
    apply_fields(s,[f],True);assert s['gold']==9
    apply_fields(s,[{'key':'shop:0','value':'OP001','confidence':1}]);assert s['shop'][0]['cost'] is None
    apply_fields(s,[{'key':'cost:0','value':3,'confidence':1},{'key':'shop:0','value':'OP002','confidence':1}]);assert s['shop'][0]['cost']==3

def test_identity_change_does_not_inherit_equipment():
    s=new_state();apply_fields(s,[{'key':'field:0','value':'OP001','confidence':1}]);u=s['units'][0];u['elite']=True;u['equipment']=['item']
    apply_fields(s,[{'key':'field:0','value':'OP002','confidence':1}]);assert not s['units'][0]['elite'];assert not s['units'][0]['equipment']

def test_stale_manual_money_blocks_auto():
    s=new_state();s['field_meta']['gold']={'locked':True,'time':time.time()-30}
    assert ready_for_auto(s,['gold'])==['gold']

def test_dpapi_and_share(tmp_path,monkeypatch,db):
    secret='test-only-placeholder';assert protect(protect(secret),True)==secret
    monkeypatch.setenv('GARRISON_DATA_DIR',str(tmp_path));storage=Storage();storage.save_key('test',secret)
    assert secret not in (tmp_path/'secrets.json').read_text();assert storage.get_key('test')==secret
    s=new_state();s['secrets']=secret;path=tmp_path/'share.json';storage.export_team(path,s,db.raw['metadata']['version'])
    exported=path.read_text(encoding='utf-8')
    assert secret not in exported;assert 'ai_profiles' not in exported;assert 'session_id' not in exported

@pytest.mark.parametrize('url',['https://example.invalid/v1','http://127.0.0.1:9123/v1'])
def test_endpoint(url):assert endpoint(url).endswith('/chat/completions')
@pytest.mark.parametrize('url',['http://example.com/v1','https://user:pass@example.com','https://example.com/?key=test','file:///x'])
def test_bad_endpoint(url):
    with pytest.raises(ValueError):endpoint(url)

def test_hotkey_parser():
    assert parse_hotkey('Ctrl+Alt+M')==(0x4003,77)
    assert parse_hotkey('Ctrl+Alt+Space')==(0x4003,32)
    with pytest.raises(ValueError):parse_hotkey('M')

def test_fingerprint_metadata_does_not_retrigger():
    s=new_state();before=fingerprint(s);s['field_meta']['gold']={'time':time.time()};assert fingerprint(s)==before
    s['gold']=10;assert fingerprint(s)!=before
