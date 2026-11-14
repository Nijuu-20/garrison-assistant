"""Missing frames preserve planning evidence without claiming fresh visibility."""
import copy
import pytest
from garrison.core import Database,new_state,unit,covenant_status,validate_state,fingerprint
from garrison.battle import mark_missing,update_roster_status,roster_signature
from garrison.recognition import apply_fields,StabilityGate
from garrison.advice import target_candidates,overlay_advice,analysis_text
from garrison.coach import make_context
from garrison.strategy import route_matches
from test_battle import observed


@pytest.fixture(scope='module')
def db():return Database()


def sample(db):
    s=new_state();s.update(round=3,level=2,phase='整备',gold=8,target='卡西米尔')
    fields=[observed('a',db.by_name['砾']['operator_id'],x=.25),
            observed('b',db.by_name['野鬃']['operator_id'],x=.45)]
    apply_fields(s,fields)
    s['units'][0].update(elite=True,sprite_elite_unknown=False,equipment=['维式重锤'])
    update_roster_status(s)
    return s,fields


def progress(db,s):
    return {c['name']:(c['count'],c['effective'],c['active'],c['members_present']) for c in covenant_status(db,s)}


def test_repeated_misses_keep_exact_team_and_recommendation_scores(db):
    s,fields=sample(db);members=copy.deepcopy(s['units']);before=progress(db,s)
    targets=target_candidates(db,s,10);routes=route_matches(db,s,10)
    for _ in range(5):mark_missing(s,set());update_roster_status(s)
    assert len(s['units'])==2 and progress(db,s)==before
    for old,new in zip(members,s['units']):
        for key in ('uid','op_id','zone','elite','equipment'):assert new[key]==old[key]
    assert [(r['name'],r['score']) for r in targets]==[(r['name'],r['score']) for r in target_candidates(db,s,10)]
    assert [(r['id'],r['score']) for r in routes]==[(r['id'],r['score']) for r in route_matches(db,s,10)]
    target=next(r for r in target_candidates(db,s,10) if r['name']=='卡西米尔')
    assert target['needs_review'] and '待核对' in target['progress']
    assert not {u['op_id'] for u in s['units']} & {c['op_id'] for c in target['candidates']}
    assert '待核对' in overlay_advice(db,s)['analysis']


def test_ai_keeps_pending_names_zone_elite_equipment_without_mutating_state(db):
    s,_=sample(db);mark_missing(s,set());update_roster_status(s);before=copy.deepcopy(s)
    ctx=make_context(db,s)
    assert s==before
    assert len(ctx['state']['units'])==2
    assert all(u['observation_status']=='needs_review' and u['last_confirmed_zone']=='field' for u in ctx['state']['units'])
    assert ctx['state']['units'][0]['elite'] is True
    assert ctx['state']['units'][0]['equipment']==['维式重锤']
    assert ctx['state']['units'][1]['elite'] is None
    assert set(ctx['roster_observation']['pending_uids'])=={u['uid'] for u in s['units']}
    cv=next(c for c in ctx['covenants'] if c['name']=='卡西米尔')
    assert cv['effective']==2 and cv['needs_review'] and cv['count_basis']=='last_confirmed_roster'
    rendered=analysis_text(db,s,{'fingerprint':fingerprint(s),'goal':'继续补齐盟约','actions':[]})
    assert '最后确认' in rendered and '待核对' in rendered


def test_stable_reappearance_clears_only_observed_pending_members(db):
    s,fields=sample(db);uids=[u['uid'] for u in s['units']];mark_missing(s,set())
    gate=StabilityGate(2)
    apply_fields(s,gate.accept([fields[0]],.92))
    assert all(u['sprite_missing'] for u in s['units'])
    apply_fields(s,gate.accept([fields[0]],.92))
    assert not s['units'][0]['sprite_missing'] and s['units'][1]['sprite_missing']
    changed=copy.deepcopy(fields[1]);changed['key']='sprite:new-track'
    apply_fields(s,[changed])
    assert [u['uid'] for u in s['units']]==uids and not any(u['sprite_missing'] for u in s['units'])
    assert not next(c for c in covenant_status(db,s) if c['name']=='卡西米尔')['needs_review']


@pytest.mark.parametrize('covenant,zone,expected',[('卡西米尔','bench',0),('卡西米尔','field',1),('远见','bench',1)])
def test_missing_retains_last_zone_and_bench_rules(db,covenant,zone,expected):
    oid=next(o['operator_id'] for o in db.ops.values() if covenant in o['covenants'])
    s=new_state();apply_fields(s,[observed(oid=oid,zone=zone)])
    mark_missing(s,set());cv=next(c for c in covenant_status(db,s) if c['name']==covenant)
    assert cv['count']==expected and cv['needs_review']==bool(expected)
    assert s['units'][0]['zone']==zone


def test_pending_harmony_marks_inherited_bonus_provisional(db):
    s,_=sample(db)
    oid=next(o['operator_id'] for o in db.ops.values() if '调和' in o['covenants'])
    apply_fields(s,[observed('h',oid,x=.7)])
    mark_missing(s,{'sprite:a','sprite:b'})
    cv=next(c for c in covenant_status(db,s) if c['name']=='卡西米尔')
    assert cv['bonus']==1 and cv['needs_review']
    assert cv['pending_uids']==[s['units'][-1]['uid']]


def test_pending_duplicates_still_count_distinct_members_once(db):
    s,_=sample(db);apply_fields(s,[observed('duplicate',s['units'][0]['op_id'],x=.8)])
    mark_missing(s,set())
    assert next(c for c in covenant_status(db,s) if c['name']=='卡西米尔')['count']==2


def test_saved_old_missing_records_are_retained_but_not_confirmed(db):
    s,_=sample(db);mark_missing(s,set());s=validate_state(s,db)
    s['field_meta']['battle_roster']={'signature':roster_signature(s)}
    update_roster_status(s)
    assert s['field_meta']['battle_roster']['uncertain']
    assert len(make_context(db,s)['state']['units'])==2
    assert next(c for c in covenant_status(db,s) if c['name']=='卡西米尔')['count']==2
    s['units'].pop();assert next(c for c in covenant_status(db,s) if c['name']=='卡西米尔')['count']==1
    assert not any(c['count'] for c in covenant_status(db,new_state()))


def test_empty_detection_never_creates_a_member(db):
    s=new_state();mark_missing(s,set());update_roster_status(s)
    unknown=observed();unknown.update(value=None,confidence=.6)
    apply_fields(s,[unknown])
    assert not s['units'] and not make_context(db,s)['state']['units']
