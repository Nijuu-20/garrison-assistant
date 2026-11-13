"""Offline, deterministic rules. No game input and no network access."""
from __future__ import annotations
import ast
import copy
import hashlib
import json
import operator
import re
import sqlite3
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from pypinyin import lazy_pinyin, Style


def resource_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'resources'
    return Path(__file__).resolve().parents[2] / 'outputs'


class Database:
    def __init__(self, path=None):
        root = resource_root()
        self.path = Path(path) if path else next(root.rglob('卫戍协议_规程数据库.json'))
        self.raw = json.loads(self.path.read_text(encoding='utf-8'))
        self.validate(self.raw)
        self.ops = {x['operator_id']: x for x in self.raw['operators']}
        self.by_name = {x['name']: x for x in self.ops.values()}
        self.covenants = self.raw['covenants']
        self.equipment = {x['name']: x for x in self.raw['equipment']}
        self.commands = {x['name']: x for x in self.raw['commands']}
        self.skills = {x['skill_id']: x for x in self.raw['skills']}
        self.sources = {x['source_id']: x for x in self.raw['sources']}
        self.search_index = {}
        for op in self.ops.values():
            self.search_index[op['operator_id']] = ' '.join([
                json.dumps(op, ensure_ascii=False), ''.join(lazy_pinyin(op['name'])),
                ''.join(lazy_pinyin(op['name'], style=Style.FIRST_LETTER))]).lower()
        self.image_paths = {}
        for kind, name in [('avatar', '头像'), ('portrait', '精一立绘')]:
            self.image_paths[kind] = next(root.rglob(f'卫戍协议_规程_{name}数据库.sqlite'), None)

    @staticmethod
    def validate(data):
        for key in ('metadata', 'operators', 'covenants', 'skills', 'equipment', 'commands', 'equipment_recipes', 'sources', 'mechanics'):
            if key not in data:
                raise ValueError(f'数据库缺少 {key}')
        ids, names = set(), set()
        for op in data['operators']:
            if not all(k in op for k in ('operator_id', 'name', 'tier', 'covenants', 'recruit_cost')):
                raise ValueError('干员字段不完整')
            if op['operator_id'] in ids or op['name'] in names:
                raise ValueError('干员编号或名称重复')
            ids.add(op['operator_id']); names.add(op['name'])
            if not isinstance(op['recruit_cost'], int) or op['recruit_cost'] < 0:
                raise ValueError('招募费用格式无效')
        cv = {x['name'] for x in data['covenants']}
        if any(set(x['covenants']) - cv for x in data['operators']):
            raise ValueError('存在未定义的盟约')
        if any(x['operator_id'] not in ids for x in data['skills']):
            raise ValueError('技能引用了未知干员')

    def image_bytes(self, op_id, kind='avatar'):
        path = self.image_paths.get(kind)
        if not path:
            return None
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
            row = conn.execute('SELECT image_png FROM images WHERE operator_id=?', (op_id,)).fetchone()
        return row[0] if row else None

    def search(self, text='', tier=0, category='', covenant=''):
        terms = text.lower().split()
        return [o for o in self.ops.values() if
                all(t in self.search_index[o['operator_id']] for t in terms) and
                (not tier or o['tier'] == tier) and
                (not category or category in o['categories']) and
                (not covenant or covenant in o['covenants'])]


def new_state():
    return {'schema': 1, 'session_id': str(uuid.uuid4()), 'name': '未命名阵容',
            'round': None, 'phase': '未知', 'gold': None, 'level': None,
            'upgrade_cost': None, 'refresh_cost': None, 'target': '', 'units': [],
            'shop': [], 'inventory': [], 'stacks': {}, 'ursas_fixed': 0,
            'ursas_temporary': 0, 'strategies': [], 'command_uses': {},
            'command_cooldowns': {}, 'carry_gold': False, 'notes': '',
            'opening': None, 'field_meta': {}, 'recognized_inventory': {}, 'recognized_offers': {}, 'events': [], 'revision': 0, 'updated_at': None}


def unit(op_id, zone='field', elite=False):
    return {'uid': str(uuid.uuid4()), 'op_id': op_id, 'zone': zone,
            'elite': elite, 'skill': '', 'equipment': [], 'capacity': 2}


def validate_state(state, db):
    if not isinstance(state, dict) or state.get('schema') != 1:
        raise ValueError('不支持的阵容文件版本')
    if not isinstance(state.get('units'), list) or len(state['units']) > 100:
        raise ValueError('阵容数据无效或数量过多')
    result = new_state()
    for k in result:
        if k in state:
            result[k] = copy.deepcopy(state[k])
    from .opening import validate as validate_opening
    validate_opening(result['opening'],db)
    seen = set()
    for u in result['units']:
        if u.get('op_id') not in db.ops or u.get('zone') not in ('field', 'bench'):
            raise ValueError('阵容包含未知干员或区域')
        if not u.get('uid') or u['uid'] in seen:
            u['uid'] = str(uuid.uuid4())
        seen.add(u['uid'])
        u.setdefault('elite', False); u.setdefault('skill', '')
        u.setdefault('equipment', []); u.setdefault('capacity', 2)
        if u['capacity'] not in (2, 4) or (u['capacity'] == 4 and db.ops[u['op_id']]['name'] != '“暴躁铁皮”'):
            raise ValueError('装备容量不符合规则')
        if len(u['equipment']) > u['capacity'] or any(e.removesuffix(' · 进阶') not in db.equipment for e in u['equipment']):
            raise ValueError('装备未知或超过容量')
        if u['skill'] and (u['skill'] not in db.skills or db.skills[u['skill']]['operator_id'] != u['op_id']):
            raise ValueError('干员技能不匹配')
    for k in ('gold', 'round', 'level', 'upgrade_cost', 'refresh_cost'):
        if result[k] is not None and (type(result[k]) is not int or not 0 <= result[k] <= 9999):
            raise ValueError(f'{k} 必须为非负整数或未知')
    if not isinstance(result['shop'], list) or len(result['shop']) > 20:
        raise ValueError('商店数据无效')
    if not isinstance(result['recognized_offers'],dict) or len(result['recognized_offers'])>20:
        raise ValueError('商店装备记录无效')
    for slot,x in result['recognized_offers'].items():
        if not str(slot).isdigit() or not isinstance(x,dict) or x.get('name') not in db.equipment or (x.get('cost') is not None and (type(x['cost']) is not int or not 0<=x['cost']<=9999)):
            raise ValueError('商店装备或价格无效')
    for x in result['shop']:
        if x.get('op_id') not in db.ops or (x.get('cost') is not None and (type(x['cost']) is not int or not 0 <= x['cost'] <= 9999)):
            raise ValueError('商店干员或价格无效')
    if any(e.removesuffix(' · 进阶') not in db.equipment for e in result['inventory']):
        raise ValueError('库存包含未知装备')
    if not isinstance(result['stacks'], dict) or any(type(v) is not int or not 0 <= v <= 999999 for v in result['stacks'].values()):
        raise ValueError('层数无效')
    if any(x not in db.commands for x in result['strategies']):
        raise ValueError('策略未知')
    return result


def fingerprint(state):
    keys = ('session_id', 'round', 'phase', 'gold', 'level', 'upgrade_cost', 'refresh_cost',
            'target', 'units', 'shop', 'inventory', 'stacks', 'ursas_fixed', 'ursas_temporary',
            'strategies', 'command_uses', 'command_cooldowns', 'carry_gold', 'recognized_offers', 'opening')
    payload={k:state.get(k) for k in keys}
    # Idle motion and tracker IDs do not change tactical state.
    payload['units']=[{k:v for k,v in u.items() if k not in ('sprite_rect','recognition_key')} for u in state.get('units',[])]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def covenant_status(db, state):
    from .opening import availability
    allowed={oid for oid,v in availability(db,state['opening']).items() if v['status']=='available'} if state.get('opening') else set(db.ops)
    units=[u for u in state['units'] if not u.get('sprite_missing')]
    field = [u for u in units if u['zone'] == 'field']
    harmony = any('调和' in db.ops[u['op_id']]['covenants'] for u in field)
    result = []
    for c in db.covenants:
        source = units if c['bench_counts'] else field
        members = {u['op_id'] for u in source if c['name'] in db.ops[u['op_id']]['covenants']}
        # 绝技 counts elite units; other covenants count distinct operators.
        count = sum(bool(u['elite']) for u in field) if c['name'] == '绝技' else len(members)
        bonus = int(harmony and c['type'] == '核心盟约' and count > 0)
        effective = count + bonus
        thresholds = sorted(set([c['activation_count']] + [int(n) for n in re.findall(r'在场(\d+)名', c['effect'])]))
        active = effective >= c['activation_count']
        if c['name'] == '独行':
            count = sum('独行' in db.ops[u['op_id']]['covenants'] for u in field)
            effective = count; active = count == 1
        next_t = next((t for t in thresholds if effective < t), None)
        result.append({**c, 'count': count, 'effective': effective, 'bonus': bonus, 'active': active,
                       'next': next_t, 'members_present': sorted(members),
                       'candidates': [o['operator_id'] for o in db.ops.values() if c['name'] in o['covenants'] and o['operator_id'] not in members and o['operator_id'] in allowed]})
    return sorted(result, key=lambda c: (-c['active'], -c['effective'], c['covenant_id']))


def safe_formula(expr, layers):
    """Only numeric arithmetic; never execute expressions from an imported database."""
    expr = expr.replace('×', '*').replace('层数', str(layers))
    if len(expr) > 120: raise ValueError('公式过长')
    tree = ast.parse(expr, mode='eval')
    ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float): return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops: return ops[type(n.op)](visit(n.left), visit(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub): return -visit(n.operand)
        raise ValueError('仅支持明确的数值公式')
    return round(visit(tree.body), 4)


def evaluated_effect(effect, layers):
    def sub(m):
        try: return f'【{safe_formula(m.group(1), layers):g}】'
        except (ValueError, SyntaxError, ZeroDivisionError): return m.group(0)
    return re.sub(r'\(([^()\n]*层数[^()\n]*)\)', sub, effect)


def promotion_need(db, op_id):
    return 2 if db.ops[op_id]['name'] == '星极' else 3


def cost_for(db, state, op_id, visible_cost=None):
    if visible_cost is not None: return visible_cost
    o = db.ops[op_id]
    cost = o['recruit_cost']
    if '远见' in o['covenants']:
        layers = state['stacks'].get('远见', 0)
        cost -= int(layers >= 80) + int(layers >= 150)
    return max(0, cost)


def recommend(db, state, shop_only=False):
    if state.get('opening') and state['field_meta'].get('opening_snapshot',{}).get('uncertain'):return []
    from .opening import availability
    allowed={oid for oid,v in availability(db,state['opening']).items() if v['status']=='available'} if state.get('opening') else set(db.ops)
    before = {x['name']: x for x in covenant_status(db, state)}
    copies = Counter(u['op_id'] for u in state['units'] if not u['elite'] and not u.get('sprite_missing') and not u.get('sprite_elite_unknown'))
    candidates = state['shop'] if shop_only else [{'op_id': x} for x in db.ops]
    ranked = []
    from .strategy import guide_boosts
    guide_weights,guide=guide_boosts(db,state)
    for index, item in enumerate(candidates):
        if item['op_id'] not in allowed:continue
        if shop_only and any(state['field_meta'].get(k,{}).get('uncertain') for k in ('shop_snapshot',f'shop:{item.get("slot",index)}',f'cost:{item.get("slot",index)}')):
            continue
        oid = item['op_id']; op = db.ops[oid]
        score = 0; reasons = []; changes = []
        simulated = copy.deepcopy(state); simulated['units'].append(unit(oid))
        after = {x['name']: x for x in covenant_status(db, simulated)}
        for name, c in after.items():
            prev = before[name]
            if not prev['active'] and c['active']:
                score += 35; reasons.append('激活' + name); changes.append(f'{name} {prev["effective"]}→{c["effective"]}')
            elif prev['active'] and not c['active']:
                score -= 40; reasons.append(name + '失效'); changes.append(name + '失效')
            elif c['effective'] > prev['effective']:
                score += 5
                if prev['next'] and c['effective'] >= prev['next']:
                    score += 22; reasons.append(f'{name}达到{prev["next"]}人档')
                changes.append(f'{name} {prev["effective"]}→{c["effective"]}')
        need = promotion_need(db, oid)
        if copies[oid] + 1 >= need:
            score += 45; reasons.append(f'已有{copies[oid]}名初始，购买可满足精锐晋升')
        elif copies[oid]:
            score += 8; reasons.append(f'同名进度 {copies[oid] + 1}/{need}')
        if state['target'] in op['covenants']:
            score += 25; reasons.append('符合目标盟约')
        if '叠层' in op['categories']:
            score += 5; reasons.append('提供叠层能力')
        if oid in guide_weights:
            score+=guide_weights[oid];reasons.insert(0,'攻略「'+guide['title']+'」'+('核心' if guide_weights[oid]>=80 else '过渡 / 可选补位'))
        cost = cost_for(db, state, oid, item.get('cost'))
        affordable = state['gold'] is not None and state['gold'] >= cost
        if not reasons: reasons = ['补充战斗能力，需结合当前生存与输出需求']
        ranked.append({'op_id': oid, 'name': op['name'], 'score': score, 'cost': cost,
                       'cost_confirmed': item.get('cost') is not None,
                       'affordable': affordable, 'reasons': reasons, 'changes': changes, 'slot': index})
    return sorted(ranked, key=lambda x: (-x['score'], x['cost'], x['name']))


def replacement_options(db, state, incoming):
    before = {x['name'] for x in covenant_status(db, state) if x['active']}
    results = []
    for old in [u for u in state['units'] if u['zone'] == 'field']:
        s = copy.deepcopy(state)
        s['units'] = [u for u in s['units'] if u['uid'] != old['uid']] + [unit(incoming)]
        after = {x['name'] for x in covenant_status(db, s) if x['active']}
        results.append({'uid': old['uid'], 'name': db.ops[old['op_id']]['name'],
                        'gain': sorted(after - before), 'loss': sorted(before - after)})
    return sorted(results, key=lambda x: (len(x['loss']), -len(x['gain'])))


def craft_options(db, inventory):
    owned = Counter(inventory); result = []
    for r in db.raw['equipment_recipes']:
        req = Counter([r['component_a'], r['component_b']])
        missing = list((req - owned).elements())
        result.append({**r, 'missing': missing, 'ready': not missing})
    for name, count in owned.items():
        if not name.endswith(' · 进阶'):
            result.append({'result': name + ' · 进阶', 'component_a': name, 'component_b': name,
                           'missing': [name] * max(0, 2 - count), 'ready': count >= 2})
    return result


def equip_item(db, state, uid, equipment):
    u = next((u for u in state['units'] if u['uid'] == uid), None)
    if not u: raise ValueError('干员已不在阵容中')
    if equipment not in state['inventory']: raise ValueError('库存中没有该装备')
    base = equipment.removesuffix(' · 进阶')
    if base not in db.equipment or db.equipment[base].get('consumable'):
        raise ValueError('消耗品不能作为常驻装备分配，请在游戏内使用后更新库存')
    if equipment in u['equipment'] and not equipment.endswith(' · 进阶'):
        u['equipment'][u['equipment'].index(equipment)] = equipment + ' · 进阶'
    else:
        if len(u['equipment']) >= u['capacity']: raise ValueError('装备栏已满')
        u['equipment'].append(equipment)
    state['inventory'].remove(equipment)


def validate_actions(db, state, actions):
    """Sequential feasibility simulation. Unknown facts are rejected, not guessed."""
    s = copy.deepcopy(state); output = []
    for action in actions[:12]:
        a = dict(action); reason = ''; t = a.get('type'); backup = copy.deepcopy(s)
        try:
            if t in ('buy', 'upgrade', 'refresh'):
                meta = s.get('field_meta', {}).get('gold', {})
                if meta.get('uncertain') or (meta.get('source') == '自动识别' and time.time() - meta.get('time', 0) > 15):
                    raise ValueError('资金识别已过期或不确定，请重新确认')
            if t == 'buy':
                if s.get('opening') and s['field_meta'].get('opening_snapshot',{}).get('uncertain'):raise ValueError('开局禁选已变化，需重新核对')
                slot = a.get('slot')
                if type(slot) is not int or not 0 <= slot < len(s['shop']): raise ValueError('商店槽位无效')
                item = s['shop'][slot]
                from .opening import unavailable_reason
                exclusion=unavailable_reason(db,s,item['op_id'])
                if exclusion:raise ValueError(exclusion)
                physical = item.get('slot', slot)
                for field_key in (f'shop:{physical}', f'cost:{physical}'):
                    meta = s.get('field_meta', {}).get(field_key, {})
                    if meta.get('uncertain') or (meta.get('source') == '自动识别' and time.time() - meta.get('time', 0) > 15):
                        raise ValueError('商店识别已过期或不确定，请重新确认')
                if item.get('bought'): raise ValueError('同一商店商品已被前序操作购买')
                if a.get('op_id', item['op_id']) != item['op_id']: raise ValueError('商店商品已变化')
                if item.get('cost') is None: raise ValueError('请先确认商店实际价格（含局内折扣）')
                cost = item['cost']
                if s['gold'] is None: raise ValueError('资金未知')
                if s['gold'] < cost: raise ValueError('按前序操作结算后资金不足')
                s['gold'] -= cost; item['bought'] = True; s['units'].append(unit(item['op_id'], 'bench'))
            elif t in ('upgrade', 'refresh'):
                cost = s[t + '_cost']
                if cost is None or s['gold'] is None: raise ValueError('实际费用或资金未知')
                if s['gold'] < cost: raise ValueError('资金不足')
                if t == 'upgrade' and s['level'] is None: raise ValueError('调度中心等级未知')
                if t == 'upgrade' and s['level'] >= 6: raise ValueError('已达最高调度中心等级')
                s['gold'] -= cost
                if t == 'upgrade': s['level'] += 1; s['upgrade_cost'] = None
                else: s['shop'] = []; s['refresh_cost'] = None
            elif t == 'promote':
                oid = a.get('op_id')
                if oid not in db.ops: raise ValueError('未知干员')
                matches = [u for u in s['units'] if u['op_id'] == oid and not u['elite'] and not u.get('sprite_missing') and not u.get('sprite_elite_unknown')]
                need = promotion_need(db, oid)
                if len(matches) < need: raise ValueError('同名初始干员数量不足')
                for u in matches[:need]: s['inventory'].extend(u['equipment']); s['units'].remove(u)
                s['units'].append(unit(oid, matches[0]['zone'], True))
            elif t == 'equip':
                if any(u['uid']==a.get('uid') and u.get('sprite_missing') for u in s['units']):raise ValueError('干员当前不可见，请先核对')
                equip_item(db, s, a.get('uid'), a.get('equipment'))
            elif t == 'move':
                u = next((u for u in s['units'] if u['uid'] == a.get('uid')), None)
                if not u or a.get('zone') not in ('field', 'bench'): raise ValueError('干员或区域无效')
                if u.get('sprite_missing'):raise ValueError('干员当前不可见，请先核对')
                u['zone'] = a['zone']
            else:
                raise ValueError('此建议需要人工核对，不属于已实现的自动校验操作')
        except (ValueError, TypeError, KeyError) as e:
            reason = str(e); s = backup
        output.append({**a, 'valid': not reason, 'validation': reason or '已按顺序核对当前已知条件', 'balance_after': s['gold']})
    return output


class StateStore:
    def __init__(self, state=None):
        self.state = state or new_state(); self.undo_stack = []; self.redo_stack = []

    def change(self, fn, reason='更新局面'):
        old = copy.deepcopy(self.state)
        try: fn(self.state)
        except Exception:
            self.state = old
            raise
        if self.state == old: return False
        self.undo_stack.append(old); self.undo_stack = self.undo_stack[-60:]; self.redo_stack.clear()
        self.state['revision'] += 1; self.state['updated_at'] = time.time()
        self.state['events'] = (self.state['events'] + [{'time': time.time(), 'text': reason}])[-30:]
        return True

    def undo(self):
        if not self.undo_stack: return False
        self.redo_stack.append(copy.deepcopy(self.state)); self.state = self.undo_stack.pop(); return True

    def redo(self):
        if not self.redo_stack: return False
        self.undo_stack.append(copy.deepcopy(self.state)); self.state = self.redo_stack.pop(); return True
