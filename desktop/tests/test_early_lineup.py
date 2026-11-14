import pytest
from garrison.core import Database,new_state,unit,fingerprint
from garrison.opening import recompute,availability
from garrison.strategy import route_matches,local_plan,ai_material
from garrison.advice import overlay_advice
from garrison.coach import make_context,SYSTEM


@pytest.fixture
def db():return Database()


def briefing(db,banned=()):
    return recompute(db,{'mode':'coop','selected':None,'groups':{},
        'core':[{'name':c['name'],'state':'grey' if c['name'] in banned else 'lit'} for c in db.covenants if c['type']=='核心盟约'],
        'additional':[{'name':c['name'],'state':'grey' if c['name'] in banned else 'lit'} for c in db.covenants if c['type']!='核心盟约']})


def early(db,round=3):
    s=new_state();s.update(round=round,phase='整备',opening=briefing(db),units=[unit(db.by_name['幽灵鲨']['operator_id'])])
    return s


def test_round_three_starts_without_core_shop_gold_level_or_roster_review(db):
    s=early(db,2);assert not route_matches(db,s) and not local_plan(db,s)['recommendation_list']
    s['round']=3;s['field_meta']['battle_roster']={'uncertain':True};s['units'][0]['sprite_missing']=True
    plan=local_plan(db,s)
    assert plan['routes'] and plan['recommendation_list'] and '一键追踪' in plan['analysis']
    assert any(i['kind']=='equipment' for i in plan['recommendation_list'])
    assert any(i['kind']=='operator' for i in plan['recommendation_list'])
    assert '当前优先：购买' not in plan['analysis'] and '后续目标' in plan['analysis']
    assert make_context(db,s)['strategy_guide']['lineup_planning']['ready']
    assert 'strategy_guide.lineup_planning.ready=true' in SYSTEM


@pytest.mark.parametrize('phase',['整备','作战'])
def test_planning_stays_available_while_battling(db,phase):
    s=early(db);s['phase']=phase
    assert local_plan(db,s)['recommendation_list']


def test_unknown_round_does_not_claim_round_three(db):
    s=early(db,None)
    assert not ai_material(db,s)['lineup_planning']['ready']
    assert not route_matches(db,s)


def test_bans_and_strategy_requirements_still_apply(db):
    s=early(db);s['opening']=briefing(db,['卡西米尔','突袭'])
    rows=route_matches(db,s,20)
    assert rows and not any(r['route_id'] in ('R02','R03','R05','R06','R07','R09','R10','R11','R01') for r in rows)
    allowed={oid for oid,v in availability(db,s['opening']).items() if v['status']=='available'}
    assert all(i['op_id'] in allowed for i in local_plan(db,s)['recommendation_list'] if i['kind']=='operator')
    s['opening']=briefing(db,['卡西米尔','乌萨斯','莱塔尼亚'])
    assert not route_matches(db,s) and not local_plan(db,s)['recommendation_list']


def test_unknown_bans_are_provisional_and_conflicting_bans_block(db):
    s=early(db);s['opening']=None;plan=local_plan(db,s)
    assert plan['recommendation_list'] and '禁选尚未确认' in plan['analysis']
    assert all('可用性待确认' in i['reason'] for i in plan['recommendation_list'] if i['kind']=='operator')
    s['opening']=briefing(db);s['field_meta']['opening_snapshot']={'uncertain':True}
    assert not local_plan(db,s)['recommendation_list']


def test_transition_members_help_choose_authored_route(db):
    s=early(db);s['units']=[unit(db.by_name['罗比菈塔']['operator_id']),unit(db.by_name['摆渡人']['operator_id'])]
    rows=route_matches(db,s,20)
    match=next(r for r in rows if r['id']=='R02')
    assert match['transition_ids'] and '过渡成员' in match['match_reason']
    assert not match['present_ids']


def test_early_lock_survives_new_cards_and_later_rounds(db):
    s=early(db);chosen=route_matches(db,s)[0]['id'];s['route_lock']=chosen
    s.update(round=9,level=5,target='精准',units=[unit(db.by_name['空弦']['operator_id'])])
    assert [m['id'] for m in route_matches(db,s,20)]==[chosen]
    assert '已锁定路线' in local_plan(db,s)['analysis']


def test_ai_pending_or_empty_list_keeps_local_targets_and_selected_route(db):
    s=early(db)
    assert overlay_advice(db,s,None,None,True)['recommendation_list']
    result={'fingerprint':fingerprint(s),'goal':'起步规划','actions':[],'guide_profile_id':'R02','recommendation_list':[],
            'target_recommendation':{'name':'卡西米尔','reason':'采用低本路线'}}
    view=overlay_advice(db,s,result,None,True)
    expected=local_plan(db,s,True,'R02')['recommendation_list']
    assert view['source']=='AI 分析' and view['recommendation_list']==expected
    assert any(i['name']=='玛恩纳' for i in view['recommendation_list'])
    supplied=[{'kind':'equipment','name':'维式重锤'}];result['recommendation_list']=supplied
    assert overlay_advice(db,s,result,None,True)['recommendation_list']==supplied
