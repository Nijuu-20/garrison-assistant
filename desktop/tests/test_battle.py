import copy
import time
from garrison.battle import (BattleRecognizer,default_zones,observation_fields,apply_observations,mark_missing,roster_signature,update_roster_status)
from garrison.core import Database,new_state,unit,fingerprint,covenant_status,validate_actions,recommend
from garrison.recognition import StabilityGate,apply_fields,ready_for_auto
from garrison.coach import make_context


def observed(tid='a',oid='OP001',zone='field',x=.4,y=.3):
    return observation_fields({'detections':[dict(track_id=tid,op_id=oid,name='测试',zone=zone,rect=[x,y,.05,.1],
        reliable=True,confidence=.96,matches=12,correlation=.8)]})[0]


def test_sprite_stability_includes_zone_but_ignores_idle_position():
    gate=StabilityGate(2);a=observed();b=observed(x=.401)
    assert not gate.accept([a],.92)
    assert gate.accept([b],.92)
    assert not gate.accept([observed(zone='bench')],.92)


def test_moving_instance_keeps_identity_and_equipment():
    s=new_state();apply_fields(s,[observed()]);u=s['units'][0];uid=u['uid']
    u.update(equipment=['维式重锤'],elite=True,sprite_elite_unknown=False)
    apply_fields(s,[observed(tid='new',zone='bench',x=.7,y=.6)])
    assert len(s['units'])==1 and u['uid']==uid and u['zone']=='bench'
    assert u['equipment']==['维式重锤'] and u['elite'] and not u['sprite_elite_unknown']


def test_two_same_name_instances_never_merge():
    s=new_state();fs=[observed(),observed('b',zone='bench',x=.7,y=.6)]
    apply_fields(s,fs);assert len(s['units'])==2
    ids=[u['uid'] for u in s['units']]
    apply_fields(s,list(reversed(fs)));assert [u['uid'] for u in s['units']]==ids


def test_ambiguous_manual_copy_does_not_duplicate_or_overwrite():
    s=new_state();s['units']=[unit('OP001')];before=copy.deepcopy(s['units'])
    apply_fields(s,[observed()]);assert s['units']==before
    assert s['field_meta']['sprite:a']['uncertain']


def test_missing_is_retained_but_not_used_for_covenants_or_actions():
    db=Database();s=new_state();apply_fields(s,[observed()]);u=s['units'][0]
    u.update(elite=True,sprite_elite_unknown=False,equipment=['维式重锤'])
    mark_missing(s,set());assert len(s['units'])==1 and u['sprite_missing']
    assert not any(c['count'] for c in covenant_status(db,s))
    assert not validate_actions(db,s,[{'type':'move','uid':u['uid'],'zone':'bench'}])[0]['valid']
    assert make_context(db,s)['state']['units']==[]
    apply_fields(s,[observed()]);assert not u['sprite_missing'] and u['elite'] and u['equipment']


def test_unknown_elite_is_not_a_promotion_copy_or_an_ai_fact():
    db=Database();s=new_state();apply_fields(s,[observed('a',x=.2),observed('b',x=.4),observed('c',x=.6)])
    assert len(s['units'])==3
    assert not validate_actions(db,s,[{'type':'promote','op_id':'OP001'}])[0]['valid']
    assert all(u['elite'] is None for u in make_context(db,s)['state']['units'])
    assert all(u['elite'] is False for u in s['units'])


def test_manual_identity_correction_clears_old_equipment_and_elite():
    s=new_state();apply_fields(s,[observed()]);u=s['units'][0];u.update(elite=True,equipment=['维式重锤'])
    apply_fields(s,[observed(oid='OP002')],manual=True)
    assert len(s['units'])==1 and u['op_id']=='OP002' and not u['elite'] and not u['equipment']


def test_idle_coordinates_and_tracker_refresh_do_not_expire_advice():
    s=new_state();apply_fields(s,[observed()]);before=fingerprint(s)
    apply_fields(s,[observed('new',x=.402)])
    assert fingerprint(s)==before
    apply_fields(s,[observed('new',zone='bench',x=.7,y=.6)])
    assert fingerprint(s)!=before


def test_complete_roster_confirmation_expires_on_round_or_roster_change():
    s=new_state();apply_fields(s,[observed()]);update_roster_status(s)
    assert ready_for_auto(s,['battle_roster'])==['battle_roster']
    s['field_meta']['battle_roster']['signature']=roster_signature(s);update_roster_status(s)
    assert not ready_for_auto(s,['battle_roster'])
    s['round']=2;update_roster_status(s);assert ready_for_auto(s,['battle_roster'])


def test_regions_follow_shifted_shop_anchor():
    a=default_zones([{'key':'cost:1','rect':[.4,.75,.02,.03]}])
    b=default_zones([{'key':'cost:1','rect':[.4,.70,.02,.03]}])
    assert abs(a['bench'][1]-b['bench'][1]-.05)<1e-6
    assert default_zones([]) is None


def test_tracker_keeps_duplicate_instances_distinct():
    detector=BattleRecognizer();ds=[observed()['detection'],observed('b',x=.7,y=.6)['detection']]
    detector.track(ds);ids=[d['track_id'] for d in ds]
    assert len(set(ids))==2
    detector.track(ds);assert [d['track_id'] for d in ds]==ids
