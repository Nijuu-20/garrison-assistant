import copy
import json

import pytest

from garrison.briefing import SoloBriefing
from garrison.core import Database
from garrison.recognition import StabilityGate
from garrison.storage import Storage, atomic_json
from garrison.tracking import ShopWatch
from test_briefing import sample
from test_tracking import observation


@pytest.fixture(scope='module')
def db(): return Database()


@pytest.mark.parametrize('saved,expected', [
    ({}, (2, 2)), ({'stable_frames': 4}, (4, 4)),
    ({'stable_frames': 5, 'opening_stable_frames': 1}, (1, 5)),
    ({'stable_frames': 3, 'shop_stable_frames': 1}, (3, 1)),
    ({'stable_frames': 6, 'opening_stable_frames': 1, 'shop_stable_frames': 3}, (1, 3)),
    ({'opening_stable_frames': None, 'shop_stable_frames': 'bad'}, (2, 2)),
    ({'opening_stable_frames': 0, 'shop_stable_frames': 99}, (1, 6)),
])
def test_migration_and_restart_preserve_independent_values(tmp_path, monkeypatch, saved, expected):
    monkeypatch.setenv('GARRISON_DATA_DIR', str(tmp_path))
    saved.update(ai_profiles=[{'id': 'retained', 'model': 'test'}], ai_profile='retained')
    atomic_json(tmp_path/'settings.json', saved)
    store = Storage()
    keys = ('opening_stable_frames', 'shop_stable_frames')
    assert tuple(store.settings[k] for k in keys) == expected
    store.save_settings()
    restored = Storage()
    assert tuple(restored.settings[k] for k in keys) == expected
    assert restored.settings['ai_profiles'] == saved['ai_profiles']
    assert restored.settings['ai_profile'] == 'retained'


@pytest.mark.parametrize('opening,shop', [(1, 3), (4, 1), (1, 1), (6, 6)])
def test_gate_independent_limits_cover_auto_and_manual_fields(db, opening, shop):
    gate = StabilityGate.from_settings({'stable_frames': 5, 'opening_stable_frames': opening, 'shop_stable_frames': shop})
    fields = sample(db)['fields'] + [
        {'key': key, 'value': value, 'confidence': .99} for key, value in (
            ('shop_snapshot', '[]'), ('shop:0', 'OP001'), ('offer:1', 'gear'), ('cost:0', 2),
            ('gold', 12), ('level', 3), ('field:0', 'OP002'), ('sprite:abc', 'OP003'))]
    expected = {f['key']: opening if f['key']=='opening_snapshot' else shop if f['key'].startswith(('shop', 'offer:', 'cost:')) else 5 for f in fields}
    for n in range(1, 7):
        assert {f['key'] for f in gate.accept(fields, .92)} == {k for k, limit in expected.items() if n >= limit}
    gate.reset()
    assert {f['key'] for f in gate.accept(fields, .92)} == {k for k, limit in expected.items() if limit == 1}


def test_one_frame_does_not_bypass_confidence_missing_or_bad_snapshot():
    gate = StabilityGate(4, opening_repeats=1, shop_repeats=1)
    for fields in ([{'key': 'shop:0', 'value': 'OP001', 'confidence': .91}],
                   [{'key': 'shop_snapshot', 'value': None, 'confidence': 1}],
                   [{'key': 'opening_snapshot', 'value': 'bad json', 'confidence': 1}]):
        assert not gate.accept(fields, .92)


@pytest.mark.parametrize('frames', [1, 3, 6])
def test_opening_confirm_and_side_change_use_configured_frames(db, frames):
    briefing = SoloBriefing()
    for side in ('left', 'right', 'left'):
        for n in range(frames):
            result = sample(db, side)
            assert briefing.observe(db, result, .92, frames, now=10+n)
            assert bool(briefing.ready_field) == (n+1 >= frames)
        assert briefing.locked and briefing.opening['selected'] == side


@pytest.mark.parametrize('damage', ['missing_icon', 'confidence', 'mismatch'])
def test_one_frame_opening_still_requires_complete_consistent_icons(db, damage):
    result = sample(db)
    if damage == 'missing_icon':
        result['opening']['additional'].pop()
        result['fields'][0]['value'] = json.dumps(result['opening'])
    elif damage == 'confidence': result['fields'][0]['confidence'] = .91
    else: result['fields'][0]['value'] = sample(db, 'right')['fields'][0]['value']
    briefing = SoloBriefing()
    briefing.observe(db, result, .92, 1)
    assert not briefing.ready_field and not briefing.locked


@pytest.mark.parametrize('kind', ['operator', 'equipment'])
@pytest.mark.parametrize('frames', [1, 3, 6])
def test_tracking_obeys_shop_frames_and_retains_geometry_guards(db, kind, frames):
    watch = ShopWatch(); result = observation(db, kind=kind)
    for n in range(frames):
        assert bool(watch.accept(db, result, frames=frames, now=n+1)) == (n+1 >= frames)
    low = copy.deepcopy(result); low['fields'][0]['confidence'] = .91
    assert not watch.accept(db, low, frames=frames)
    assert not watch.accept(db, {**result, 'layout_valid': False}, frames=1)
    assert not watch.accept(db, {**result, 'opening': {'mode': 'solo'}}, frames=1)


def test_restarted_opening_keeps_confirmed_content_but_not_old_evidence(db):
    briefing = SoloBriefing(); result = sample(db)
    briefing.observe(db, result, .92, 1, now=1)
    briefing.exit_count = 2
    briefing.restart_evidence()
    assert briefing.locked and briefing.opening == result['opening']
    assert not briefing.ready_field and briefing.count == briefing.exit_count == 0
    for n in range(3):
        briefing.observe(db, result, .92, 3, now=2+n)
        assert bool(briefing.ready_field) == (n == 2)
