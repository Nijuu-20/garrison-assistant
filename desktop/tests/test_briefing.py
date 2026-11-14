import copy,json
import pytest
from garrison.core import Database
from garrison.opening import recompute,snapshot_key
from garrison.briefing import SoloBriefing
from garrison.recognition import StabilityGate

@pytest.fixture(scope='module')
def db():return Database()

def sample(db,side='left'):
    core=[c['name'] for c in db.covenants if c['type']=='核心盟约']
    adds=[c['name'] for c in db.covenants if c['type']!='核心盟约']
    o=recompute(db,{'mode':'solo','selected':side,'groups':{'left':core[:5],'right':core[5:]},
      'core':[{'name':n,'state':'lit' if (i<5)==(side=='left') else 'grey'} for i,n in enumerate(core)],
      'additional':[{'name':n,'state':'grey' if i<5 else 'lit'} for i,n in enumerate(adds)]})
    return {'opening':o,'fields':[{'key':'opening_snapshot','value':json.dumps(o),'confidence':.97}]}

def push(t,db,result,now=1):return t.observe(db,result,.92,2,now)

def test_order_changes_do_not_reset_snapshot_stability(db):
    a=sample(db);b=copy.deepcopy(a)
    for k in ('core','additional'):b['opening'][k].reverse()
    for names in b['opening']['groups'].values():names.reverse()
    b['fields'][0]['value']=json.dumps(b['opening']);t=SoloBriefing();g=StabilityGate()
    push(t,db,a);push(t,db,b,2)
    assert t.ready_field and snapshot_key(t.opening)==snapshot_key(a['opening'])
    assert not g.accept(a['fields'],.92) and g.accept(b['fields'],.92)

def test_one_dropout_keeps_whole_snapshot_and_allows_agreement(db):
    a=sample(db);t=SoloBriefing();push(t,db,a)
    push(t,db,{'fields':[]},2)
    assert t.held and t.opening==a['opening'] and not t.conflict and not t.ready_field
    push(t,db,a,3);assert t.ready_field and not t.held

def test_sustained_loss_never_looks_fresh_or_invents_icons(db):
    t=SoloBriefing();a=sample(db);push(t,db,a)
    for now in (2,3,4):push(t,db,{'fields':[]},now)
    assert t.opening==a['opening'] and t.held and t.uncertain and not t.ready_field
    assert not t.conflict  # Lost visibility alone is not proof the pool changed.
    push(t,db,a,5);assert not t.ready_field
    push(t,db,a,6);assert t.ready_field

def test_new_group_requires_repeated_complete_agreement(db):
    t=SoloBriefing();a=sample(db);b=sample(db,'right');push(t,db,a);push(t,db,a,2)
    push(t,db,b,3)
    assert t.opening['selected']=='left' and t.conflict and t.held and not t.ready_field
    push(t,db,b,4)
    assert t.opening['selected']=='right' and t.ready_field and not t.conflict

def test_partial_conflicting_frame_does_not_replace_view_or_complete_it(db):
    t=SoloBriefing();a=sample(db);push(t,db,a);b=sample(db,'right')
    b['opening']['additional'].pop();b['fields'][0]['value']=None
    for now in range(2,8):push(t,db,b,now)
    assert t.opening==a['opening'] and t.conflict and not t.ready_field

def test_alternating_complete_groups_never_auto_confirm(db):
    t=SoloBriefing();a=sample(db);b=sample(db,'right')
    for i in range(8):
        push(t,db,a if i%2==0 else b,i+1)
        assert not t.ready_field
    assert t.opening['selected']=='left'

def test_old_frame_time_does_not_count_as_agreement(db):
    t=SoloBriefing();a=sample(db);push(t,db,a,1);push(t,db,a,20)
    assert not t.ready_field

def test_full_hud_transition_releases_briefing_only_after_two_frames(db):
    t=SoloBriefing();push(t,db,sample(db))
    hud={'fields':[{'key':k,'value':v,'confidence':.99} for k,v in [('phase','整备'),('round',1),('level',1),('gold',6)]]}
    assert push(t,db,hud,2) and t.opening
    assert not push(t,db,hud,3) and not t.opening and t.departed
    assert not push(t,db,{'fields':[]},4) and t.departed

def test_partial_hud_does_not_flicker_out_of_briefing(db):
    t=SoloBriefing();push(t,db,sample(db))
    weak={'fields':[{'key':'phase','value':'整备','confidence':.99}]}
    for now in range(2,7):assert push(t,db,weak,now) and not t.departed

def test_multiplayer_stable_snapshot_is_locked_without_a_side_choice(db):
    t=SoloBriefing();a=sample(db);a['opening'].update(mode='coop',selected=None,groups={})
    a['fields'][0]['value']=json.dumps(a['opening'])
    assert push(t,db,a) and not t.locked
    push(t,db,a,2);assert t.locked and t.ready_field and t.opening['selected'] is None
    frozen=t.opening
    push(t,db,{'fields':[]},3);push(t,db,a,4)
    assert t.locked and t.opening is frozen


def test_locked_content_does_not_replace_detection_details_each_frame(db):
    t=SoloBriefing();a=sample(db);push(t,db,a);push(t,db,a,2);frozen=t.opening
    jitter=copy.deepcopy(a);jitter['opening']['core'][0]['similarity']=.95
    for n in range(3,8):push(t,db,jitter,n)
    assert t.locked and t.opening is frozen and 'similarity' not in t.opening['core'][0]

def test_low_confidence_cannot_auto_confirm(db):
    t=SoloBriefing();a=sample(db);a['fields'][0]['confidence']=.4
    for now in range(1,5):push(t,db,a,now);assert not t.ready_field

def test_new_capture_source_forgets_old_frames(db):
    t=SoloBriefing();push(t,db,sample(db));t.reset()
    assert not t.opening and not t.departed
    push(t,db,sample(db,'right'),2);assert not t.ready_field and t.opening['selected']=='right'

def test_repeated_side_switch_with_candidate_agreeing_dropout_can_confirm(db):
    t=SoloBriefing();a=sample(db);push(t,db,a,1);push(t,db,a,2);t.seed(a['opening'])
    now=3
    for side in ['right','left']*6:
        changed=sample(db,side);partial=copy.deepcopy(changed)
        partial['opening']['additional'].pop();partial['fields'][0]['value']=None
        push(t,db,changed,now);assert not t.ready_field
        push(t,db,partial,now+1);assert t.conflict and not t.ready_field
        push(t,db,changed,now+2)
        assert t.ready_field and t.opening['selected']==side and not t.conflict
        t.seed(t.opening);now+=3

def test_old_side_dropout_resets_new_candidate_but_does_not_lock_it(db):
    t=SoloBriefing();a=sample(db);b=sample(db,'right');push(t,db,a,1);push(t,db,a,2)
    push(t,db,b,3);partial=copy.deepcopy(a);partial['opening']['additional'].pop();partial['fields'][0]['value']=None
    push(t,db,partial,4);push(t,db,b,5);assert not t.ready_field
    push(t,db,b,6);assert t.ready_field and t.opening['selected']=='right'
