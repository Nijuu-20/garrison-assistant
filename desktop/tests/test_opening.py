import copy,json
from pathlib import Path
import pytest
from garrison.core import Database,new_state,recommend,validate_actions,validate_state,fingerprint
from garrison.opening import availability,recommendation,recompute,apply_snapshot,rules,confirmation_problem,ban_summary
from garrison.recognition import StabilityGate,apply_fields
from garrison.coach import make_context

@pytest.fixture(scope='module')
def db():return Database()

def opening(db,big=(),small=(),mode='coop'):
    return recompute(db,{'mode':mode,'selected':None,'groups':{},
     'core':[{'name':c['name'],'state':'grey' if c['name'] in big else 'lit'} for c in db.covenants if c['type']=='核心盟约'],
     'additional':[{'name':c['name'],'state':'grey' if c['name'] in small else 'lit'} for c in db.covenants if c['type']!='核心盟约']})

def status(db,o,name):return availability(db,o)[db.by_name[name]['operator_id']]['status']

def test_primary_core_follows_html_not_any_core(db):
    assert status(db,opening(db,['莱塔尼亚']),'复奏')=='available'
    assert status(db,opening(db,['叙拉古']),'复奏')=='banned'
    assert status(db,opening(db,['卡西米尔','莱塔尼亚']),'锏')=='available'
    assert status(db,opening(db,['谢拉格']),'锏')=='banned'

def test_additional_all_not_any_only_without_core(db):
    assert status(db,opening(db,small=['坚守']),'摆渡人')=='available'
    assert status(db,opening(db,small=['坚守','不屈']),'摆渡人')=='banned'
    assert status(db,opening(db,small=['不屈']),'折桠')=='available'

def test_hellagur_uses_primary_core_even_when_assault_banned(db):
    o=opening(db,small=['突袭']);oid=db.by_name['赫拉格']['operator_id']
    assert status(db,o,'赫拉格')=='available'
    assert status(db,o,'杰克')=='banned'
    assert status(db,opening(db,['乌萨斯']),'赫拉格')=='banned'
    s=new_state();s.update(opening=o,gold=30,level=6,phase='整备',shop=[{'op_id':oid,'cost':4,'slot':0}])
    assert any(r['op_id']==oid for r in recommend(db,s,True))
    assert validate_actions(db,s,[{'type':'buy','slot':0}])[0]['valid']
    from garrison.advice import ban_context
    from garrison.tracking import normalize_items
    context=ban_context(db,s)
    assert oid in context['available_operator_ids'] and all(x['op_id']!=oid for x in context['banned_operators'])
    assert normalize_items(db,[{'kind':'operator','op_id':oid}],s)

def test_solo_trait_not_bannable_and_no_add_is_not_vacuously_banned(db):
    assert status(db,opening(db,small=['独行']),'地灵')=='available'
    assert status(db,opening(db,small=rules()['small']),'烈夏')=='available'

def test_unknown_primary_cannot_be_resolved_by_additional_covenants(db):
    o=opening(db);next(e for e in o['core'] if e['name']=='乌萨斯')['state']='unknown'
    assert status(db,o,'折桠')=='unknown'
    next(e for e in o['additional'] if e['name']=='不屈')['state']='grey'
    assert status(db,o,'折桠')=='unknown'

def test_side_change_recomputes_restrictions_and_does_not_union_bans(db):
    o=opening(db,['乌萨斯']);s=new_state();apply_snapshot(s,o);old=set(s['opening']['banned_ids'])
    new=opening(db,['莱塔尼亚']);apply_snapshot(s,new)
    assert s['opening']['banned_ids']==new['banned_ids'] and set(new['banned_ids'])!=old
    assert status(db,s['opening'],'烈夏')=='available'

def test_banned_pool_filters_local_and_rejects_ai_buy(db):
    s=new_state();s['opening']=opening(db,['乌萨斯']);oid=db.by_name['烈夏']['operator_id']
    s.update(gold=10,shop=[{'op_id':oid,'cost':2}])
    assert recommend(db,s,True)==[]
    action=validate_actions(db,s,[{'type':'buy','slot':0}])[0]
    assert not action['valid'] and '主核心' in action['validation']
    assert oid in make_context(db,s)['state']['opening']['banned_ids']

def test_uncertain_changed_opening_blocks_stale_recommendations(db):
    s=new_state();s['opening']=opening(db);s['field_meta']['opening_snapshot']={'uncertain':True}
    s.update(gold=10,shop=[{'op_id':db.by_name['烈夏']['operator_id'],'cost':2}])
    assert not recommend(db,s,True)
    assert not validate_actions(db,s,[{'type':'buy','slot':0}])[0]['valid']

def test_group_recommendation_only_solo_recalculates_alternate_pool(db):
    o=opening(db);assert recommendation(db,o) is None
    names=[e['name'] for e in o['core']];o.update(mode='solo',groups={'left':names[:5],'right':names[5:]},selected='left')
    for e in o['core']:e['state']='lit' if e['name'] in names[:5] else 'grey'
    recompute(db,o);result=recommendation(db,o,names[6])
    assert result['side']=='right'
    for group in result['groups']:
        statuses=availability(db,o,group['side'])
        assert group['available_count']==sum(v['status']=='available' for v in statuses.values())
        if group['route']:
            assert all(statuses[db.by_name[name]['operator_id']]['status']=='available' for name in group['route']['operators'])
    assert o['selected']=='left'

def test_full_snapshot_stabilizes_and_new_session_clears(db):
    o=opening(db,['乌萨斯']);s=new_state();before=fingerprint(s)
    f={'key':'opening_snapshot','value':json.dumps(o,sort_keys=True),'confidence':.97}
    gate=StabilityGate();assert not gate.accept([f],.92)
    apply_fields(s,gate.accept([f],.92))
    assert s['opening']==o and s['phase']=='开局' and fingerprint(s)!=before
    assert new_state()['opening'] is None

def test_import_validates_and_recomputes_instead_of_trusting_cached_bans(db):
    s=new_state();s['opening']=opening(db,['乌萨斯']);s['opening']['banned_ids']=[]
    assert validate_state(s,db)['opening']['banned_ids']
    s['opening']['core'][0]['name']='非数据库盟约'
    with pytest.raises(ValueError):validate_state(s,db)

def test_html_has_two_documented_extra_database_entries(db):
    assert set(db.by_name)-set(rules()['operators'])=={'盟约·辅助干员','“暴躁铁皮”'}

@pytest.mark.parametrize('count',[0,1,2,5])
def test_no_core_bans_and_variable_additional_bans_can_confirm(db,count):
    o=opening(db,small=rules()['small'][:count],mode='fixed')
    assert not confirmation_problem(db,o) and o['ban_status']=='derived'
    assert ban_summary(o,'core')=='无（全部启用）' and recommendation(db,o) is None
    assert all(availability(db,o)[oid]['status']=='available' for oid,op in db.ops.items() if rules()['operators'].get(op['name'],{}).get('core'))
    s=new_state();apply_snapshot(s,o);assert validate_state(s,db)['opening']==o
    from garrison.advice import ban_context
    context=ban_context(db,s)
    assert context['core_banned']==[] and len(context['core_available'])==10 and len(context['additional_banned'])==count

@pytest.mark.parametrize('mutation',[lambda o:o['core'].clear(),lambda o:o['core'].pop(),lambda o:o['core'][0].update(state='unknown'),lambda o:o['additional'].pop(),lambda o:o['core'][0].update(name=o['core'][1]['name'])])
def test_missing_or_unknown_icons_are_not_no_bans(db,mutation):
    o=opening(db,mode='fixed');mutation(o)
    assert confirmation_problem(db,o)

def test_in_match_snapshot_preserves_all_tactical_state(db):
    from garrison.core import unit
    s=new_state();s.update(phase='整备',round=8,level=5,gold=18,units=[unit('OP001')],shop=[{'op_id':'OP001','cost':2}],inventory=['测试装备'],target='乌萨斯')
    s['opening']=opening(db,['乌萨斯']);before=copy.deepcopy(s)
    o=opening(db,small=rules()['small'][:2],mode='fixed');o['context']='in_match'
    apply_fields(s,[{'key':'opening_snapshot','value':json.dumps(o),'confidence':.97}],True)
    assert all(s[k]==v for k,v in before.items() if k not in ('opening','field_meta'))
    assert s['opening']==o and s['field_meta']['opening_snapshot']['source']=='手动确认'
