import copy,time
import pytest
from garrison.core import Database,new_state,fingerprint,unit
from garrison.advice import overlay_advice,analysis_text,target_candidates,ban_context,action_title
from garrison.coach import normalize_result,make_context
from garrison.opening import recompute

@pytest.fixture(scope='module')
def db():return Database()

def restrictions(db):
    return recompute(db,{'mode':'coop','selected':None,'groups':{},
      'core':[{'name':c['name'],'state':'grey' if c['name']=='乌萨斯' else 'lit'} for c in db.covenants if c['type']=='核心盟约'],
      'additional':[{'name':c['name'],'state':'grey' if c['name'] in ('迅捷','坚守') else 'lit'} for c in db.covenants if c['type']!='核心盟约']})

def sample(db):
    state=new_state();state.update(gold=8,round=3,phase='整备',level=2,shop=[{'op_id':db.by_name['野鬃']['operator_id'],'cost':2,'slot':4}],
                                  units=[unit(db.by_name['砾']['operator_id'])],target='卡西米尔')
    return state

def response(db,state):
    result=normalize_result({'goal':'优先买野鬃补齐卡西米尔成员','assessment':'已有砾，商店有野鬃，可推进目标。',
       'actions':[{'type':'buy','slot':0,'reason':'现有资金足够并符合目标','expected_gain':'增加一名不同的卡西米尔成员','condition':'确认商店仍是野鬃'}],
       'economy':'买入花费2，余6；先不刷新。','formation':['补齐成员后再核对站位。'],
       'alternative':'商品变化时先保留资金。','next_round':'留意下一名卡西米尔成员。','warnings':[]},db,state)
    return {**result,'fingerprint':fingerprint(state)}

def test_current_ai_precedes_local_and_has_named_steps(db):
    s=sample(db);r=response(db,s);view=overlay_advice(db,s,r,ai_enabled=True)
    assert view['source']=='AI 分析'
    assert all(t in view['analysis'] for t in ('购买 野鬃','第 5 格','理由：','预期：','条件：','剩余 6'))
    assert not any(t in view['analysis'] for t in ('OP','confidence','elapsed_ms','valid','区域','条件核验'))

def test_full_analysis_keeps_specific_detail(db):
    s=sample(db);r=response(db,s);detail=analysis_text(db,s,r)
    assert all(t in detail for t in ('资金安排','站位与装备','后续目标','备选方案'))

def test_stale_result_not_displayed_or_used_for_target(db):
    s=sample(db);r=response(db,s);r['goal']='STALE_ACTION';s['gold']=1
    view=overlay_advice(db,s,r,ai_enabled=True)
    assert view['source']=='本地攻略' and 'STALE_ACTION' not in view['analysis']
    assert 'STALE_ACTION' not in analysis_text(db,s,r)

def test_unconfirmed_ban_change_suppresses_cached_ai(db):
    s=sample(db);s['opening']=restrictions(db);r=response(db,s)
    s['field_meta']['opening_snapshot']={'uncertain':True}
    view=overlay_advice(db,s,r,ai_enabled=True)
    assert view['source']=='本地攻略' and not view['targets'] and '确认本局禁选' in view['analysis']

def test_live_metadata_revalidated_even_without_fingerprint_change(db):
    s=sample(db);r=response(db,s);s['field_meta']['gold']={'source':'自动识别','time':time.time()-20}
    assert '暂缓购买' in analysis_text(db,s,r,True)
    assert '优先考虑购买' not in overlay_advice(db,s)['analysis']

def test_target_pool_excludes_banned_core_even_if_user_target(db):
    s=sample(db);s['opening']=restrictions(db);s['target']='乌萨斯'
    assert all(t['name']!='乌萨斯' for t in target_candidates(db,s,10))

def test_bans_explicit_in_ai_input_and_target_output_checked(db):
    s=sample(db);s['opening']=restrictions(db);s['target']='乌萨斯';context=make_context(db,s)
    assert context['ban_constraints']['status']=='confirmed'
    assert context['ban_constraints']['core_banned']==['乌萨斯']
    assert set(context['ban_constraints']['additional_banned'])=={'迅捷','坚守'}
    assert any(o['name']=='烈夏' for o in context['ban_constraints']['banned_operators'])
    assert all(t['name']!='乌萨斯' for t in context['target_candidates'])
    result=normalize_result({'goal':'建议补强','actions':[],'target_recommendation':{'name':'乌萨斯','reason':'忽略禁选'}},db,s)
    assert result['target_recommendation']=={} and result['warnings']

def test_absent_bans_are_unknown_not_everyone_available(db):
    c=ban_context(db,new_state());assert c['status']=='unknown' and not c['available_operator_ids']

def test_structured_provider_noise_not_printed_as_python_objects(db):
    s=sample(db);r=normalize_result({'goal':'补强','actions':[{'type':{},'op_id':{},'reason':{'debug':'do not display'}}],
      'warnings':{'trace':'do not display'},'formation':None},db,s)
    r['fingerprint']=fingerprint(s)
    assert 'do not display' not in analysis_text(db,s,r)
    assert not r['actions'][0]['valid']

def test_move_and_equipment_use_human_instance_name(db):
    s=sample(db);uid=s['units'][0]['uid']
    assert '砾' in action_title(db,s,{'type':'move','uid':uid,'zone':'bench'})
    assert uid not in action_title(db,s,{'type':'equip','uid':uid,'equipment':'维式重锤'})
