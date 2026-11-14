import copy,json
from pathlib import Path
import pytest
from garrison.core import Database,new_state,unit,recommend,fingerprint,validate_state
from garrison.opening import recompute
from garrison.strategy import (library,skill_text,verify_bundle,route_matches,local_plan,ai_material,
                               resolve_ai_sources,sources_html,safe_excerpt,member_roles)
from garrison.coach import make_context,normalize_result
from garrison.storage import Storage

@pytest.fixture
def db():return Database()

def opening(db,banned=()):
    return recompute(db,{'mode':'coop','selected':None,'groups':{},
        'core':[{'name':c['name'],'state':'grey' if c['name'] in banned else 'lit'} for c in db.covenants if c['type']=='核心盟约'],
        'additional':[{'name':c['name'],'state':'grey' if c['name'] in banned else 'lit'} for c in db.covenants if c['type']!='核心盟约']})

def state(db,target='卡西米尔'):
    s=new_state();s.update(target=target,level=3,round=5,phase='整备',gold=8,opening=opening(db))
    return s

def test_bundle_uses_existing_authored_material_verbatim():
    assert verify_bundle() and len(library()['routes'])==11 and len(library()['sources'])==20
    base=Path(__file__).parents[2]/'outputs/strategy_library_2026-11-13/github-verified/garrison-strategy-guide'
    for path in ('SKILL.md','references/routes/R02.md','references/mechanics.md'):
        assert skill_text(path)==(base/path).read_text('utf8')


def test_route_lock_survives_changing_board_shop_target_and_level(db):
    s=state(db);assert route_matches(db,s,1)[0]['id']=='R02'
    before=fingerprint(s);s['route_lock']='R02';assert fingerprint(s)!=before
    s.update(target='乌萨斯',level=6,gold=20,units=[unit(db.by_name['塔露拉']['operator_id'])],shop=[])
    assert [r['id'] for r in route_matches(db,s,20)]==['R02']
    assert '已锁定路线' in local_plan(db,s)['analysis'] and validate_state(s,db)['route_lock']=='R02'
    assert new_state()['route_lock']==''
    s['route_lock']='';assert route_matches(db,s,1)[0]['id']!='R02'


def test_locked_route_cannot_bypass_bans_or_deleted_guide(db):
    s=state(db);s['route_lock']='R02';s['opening']=opening(db,['卡西米尔'])
    assert not route_matches(db,s) and not local_plan(db,s)['recommendation_list']
    assert '不会自动换线' in local_plan(db,s)['analysis'] and s['route_lock']=='R02'
    s['opening']=opening(db);db.disabled_guide_routes=['R02']
    assert not route_matches(db,s) and not ai_material(db,s)['route_lock_satisfied']


def test_locked_ai_context_and_response_cannot_silently_switch_routes(db):
    s=state(db);s['route_lock']='R02';context=make_context(db,s)
    assert context['strategy_guide']['locked_route']['id']=='R02'
    assert {m['id'] for m in context['strategy_guide']['matches']}=={'R02'}
    raw={'goal':'按路线推进','actions':[],'guide_profile_id':'R04'}
    bad=normalize_result(raw,db,s);assert bad['route_conflict'] and not bad['recommendation_list']
    raw['guide_profile_id']='R02';assert not normalize_result(raw,db,s)['route_conflict']
    del raw['guide_profile_id'];assert normalize_result(raw,db,s)['route_conflict']


def test_route_lock_keeps_specific_author_variant(db):
    s=state(db,'炎');s['strategies']=['御守之力'];s['route_lock']='R01-suzuran'
    assert route_matches(db,s)[0]['id']=='R01-suzuran'
    s['strategies']=['广交豪杰']
    assert not route_matches(db,s)  # Do not silently turn the lock into the other R01 author.

def test_strategy_gates_and_starter_remains_after_switch(db):
    s=state(db,'灵巧');s['opening']=None
    assert not any(m['route_id'] in ('R03','R05','R06','R07','R09','R10') for m in route_matches(db,s,20))
    s['strategies']=['暴躁铁皮'];assert any(m['route_id']=='R03' for m in route_matches(db,s,20))
    s['strategies']=[];s['units']=[unit(db.by_name['“暴躁铁皮”']['operator_id'])]
    assert any(m['route_id']=='R03' for m in route_matches(db,s,20))
    s['units'][0]['sprite_missing']=True
    match=next(m for m in route_matches(db,s,20) if m['route_id']=='R03')
    assert match['needs_review'] and match['present_ids']==[s['units'][0]['op_id']]
    assert '待核对' in local_plan(db,s)['analysis']

def test_yan_variants_not_combined(db):
    s=state(db,'炎');s['strategies']=['广交豪杰']
    rows=[m for m in route_matches(db,s,20) if m['route_id']=='R01']
    assert len(rows)==1 and rows[0]['source_ids']==['S04'] and rows[0]['variant']=='杜遥夜三炎兜底'
    assert all('铃兰' not in t for t in rows[0]['operation'])
    s['strategies']=['御守之力'];rows=[m for m in route_matches(db,s,20) if m['route_id']=='R01']
    assert len(rows)==1 and rows[0]['source_ids']==['S02'] and all('杜遥夜' not in t for t in rows[0]['operation'])
    assert 'S01' not in rows[0]['source_ids']

@pytest.mark.parametrize('ban',['卡西米尔','突袭'])
def test_banned_route_requirement_cannot_be_overridden_by_target(db,ban):
    s=state(db);s['opening']=opening(db,[ban])
    assert not any(m['route_id']=='R02' for m in route_matches(db,s,20))
    assert 'R02' not in [r['route_id'] for r in ai_material(db,s)['routes']]

def test_local_recommendation_has_authored_items_and_actual_cost(db):
    s=state(db);s['units']=[unit(db.by_name['砾']['operator_id'])]
    s['shop']=[{'op_id':db.by_name['瑕光']['operator_id'],'cost':3,'slot':4}]
    plan=local_plan(db,s)
    assert plan['source']=='本地攻略' and plan['routes'][0]['source_ids']==['S05']
    assert plan['source_ids'][0]=='S05'  # Round-three planning also cites a fallback route.
    assert '购买 瑕光，花费 3，余 5' in plan['analysis']
    assert any(i['kind']=='equipment' and i['name']=='精准狙击镜' for i in plan['recommendation_list'])
    mlynar=next(i for i in plan['recommendation_list'] if i['name']=='玛恩纳')
    assert '晋升奖励' in mlynar['reason'] and '不保证' in mlynar['reason']
    s['gold']=1;assert '当前优先：购买' not in local_plan(db,s)['analysis']

def test_local_buy_order_really_uses_guide(db):
    s=state(db);s['shop']=[{'op_id':db.by_name['夜莺']['operator_id'],'cost':1,'slot':0},
                         {'op_id':db.by_name['瑕光']['operator_id'],'cost':3,'slot':1}]
    assert recommend(db,s,True)[0]['name']=='瑕光'
    assert '攻略' in recommend(db,s,True)[0]['reasons'][0]

def test_forbidden_core_removed_from_local_list_and_disabled_route_from_ai(db):
    s=state(db);db.disabled_guide_routes=['R02']
    assert not any(m['route_id']=='R02' for m in route_matches(db,s,20))
    material=ai_material(db,s)
    assert material['disabled_routes']==['R02'] and not any(r['route_id']=='R02' for r in material['routes'])
    db.disabled_guide_routes=[];assert any(m['route_id']=='R02' for m in route_matches(db,s,20))

def test_unknown_or_unconfirmed_bans_not_claimed_confirmed(db):
    s=state(db);s['opening']=None;p=local_plan(db,s)
    assert '禁选尚未确认' in p['analysis']
    assert all('可用性待确认' in i['reason'] for i in p['recommendation_list'] if i['kind']=='operator')
    s['opening']=opening(db);s['field_meta']['opening_snapshot']={'uncertain':True}
    assert not local_plan(db,s)['recommendation_list'] and not ai_material(db,s)['routes']

def test_equipment_name_is_not_treated_as_banned_covenant_or_operator(db):
    s=state(db);s['opening']=opening(db,['精准','乌萨斯'])
    assert safe_excerpt(db,s,'精准狙击镜与乌萨斯呼吸器按当前携带条件选取。')
    assert not safe_excerpt(db,s,'转精准后开3精准。')
    assert not safe_excerpt(db,s,'前排使用烈夏。')

def test_exact_selected_skill_docs_and_provenance_in_context(db):
    s=state(db);context=make_context(db,s);material=context['strategy_guide']
    assert 1<=len(material['routes'])<=3
    r=next(r for r in material['routes'] if r['route_id']=='R02')
    assert r['content']==skill_text('references/routes/R02.md') and material['mechanics']==skill_text('references/mechanics.md')
    source=next(s for s in material['sources'] if s['id']=='S05')
    assert source['authors'][0]['name']=='某中二的鸽子' and source['url'].startswith('https://www.bilibili.com/')

def test_model_sources_are_limited_to_retrieved_documents(db):
    s=state(db);assert resolve_ai_sources(db,s,['S05','S99','https://fake','S05'])==['S05']
    r=normalize_result({'goal':'按攻略补齐成员','actions':[],'guide_source_ids':['S05']},db,s)
    assert r['guide_source_ids']==['S05'] and r['guide_source_label']=='攻略来源'
    fallback=normalize_result({'goal':'核对局面','actions':[]},db,s)
    assert '未标明' in fallback['guide_source_label']
    assert '某中二的鸽子' in sources_html(['S05']) and 'href=' in sources_html(['S05'])

def test_delete_api_key_only_removes_selected_profile(tmp_path,monkeypatch):
    monkeypatch.setenv('GARRISON_DATA_DIR',str(tmp_path));store=Storage()
    store.save_key('a','test-a');store.save_key('b','test-b');store.delete_key('a')
    assert store.get_key('a')=='' and store.get_key('b')=='test-b'
    store.delete_key('a')
