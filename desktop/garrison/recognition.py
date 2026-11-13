from __future__ import annotations
import copy
import json
import re
import time
import cv2
import numpy as np
from .core import unit
from . import hud

LABELS = {'gold': '资金', 'round': '回合', 'level': '调度中心等级', 'upgrade_cost': '升级费用',
          'refresh_cost': '刷新费用', 'phase': '阶段', 'ursas_fixed': '乌萨斯固定层', 'ursas_temporary': '乌萨斯临时层'}


def field_label(key):
    if key in LABELS:return LABELS[key]
    if key=='shop_snapshot':return '商店整体核验'
    if key=='opening_snapshot':return '开局盟约与禁用推算'
    if key.startswith('sprite:'):return '战场小人比对'
    if key=='battle_roster':return '阵容完整性核对'
    if key=='battle_field':return '战场比对范围（脚底）'
    if key=='battle_bench':return '整备比对范围（脚底）'
    kinds={'shop':'商店干员','offer':'商店装备 / 未知商品','cost':'商品价格','field':'战场干员','bench':'整备干员','equipment':'库存装备'}
    prefix,_,index=key.partition(':')
    return f'{kinds[prefix]} {int(index)+1}' if prefix in kinds and index.isdigit() else key


def clean(text):
    return re.sub(r'[\s·“”"\[\]【】()（）:：,，。]', '', text)


def exact_entity(text, choices):
    value = clean(text)
    # A one-character operator such as 山 must not match arbitrary sentences.
    matches = [name for name in choices if clean(name) == value]
    if len(matches) == 1: return matches[0]
    matches = [name for name in choices if len(clean(name)) >= 2 and clean(name) in value]
    longest = sorted(matches, key=len, reverse=True)
    return longest[0] if longest and all(clean(n) in clean(longest[0]) for n in longest[1:]) else None


def interpret(key, texts, db):
    joined = ' '.join(t[0] for t in texts)
    confidence = min((float(t[1]) for t in texts), default=0.0)
    name = None; value = None
    if key.startswith(('shop:', 'field:', 'bench:')):
        names = [exact_entity(t[0], db.by_name) for t in texts]
        names = set(n for n in names if n)
        if len(names) == 1:
            name = names.pop(); value = db.by_name[name]['operator_id']
            confidence = max(t[1] for t in texts if exact_entity(t[0], db.by_name) == name)
    elif key.startswith(('equipment:', 'gear:', 'offer:')):
        name = exact_entity(joined, db.equipment); value = name
    elif key.startswith('strategy:'):
        name = exact_entity(joined, db.commands); value = name
    elif key.startswith('elite:'):
        if '精锐' in joined: value = True
        elif '初始' in joined: value = False
    elif key == 'phase':
        candidates = [p for p, words in [('整备', ('休整', '整备', '招募干员', '休息')), ('作战', ('作战阶段', '战斗进行', '战斗中')), ('结束', ('模拟结束', '作战失败', '行动结束'))] if any(w in joined for w in words)]
        if len(candidates) == 1: value = candidates[0]
    else:
        nums = re.findall(r'(?<!\d)\d+(?!\d)', joined)
        if len(nums) == 1:
            value = int(nums[0])
            if (key == 'level' and not 1 <= value <= 6) or value > 99999: value = None
        elif key == 'level':
            roman=clean(joined).upper().replace('Ⅰ','I').replace('Ⅱ','II').replace('Ⅲ','III').replace('Ⅳ','IV').replace('Ⅴ','V').replace('Ⅵ','VI')
            value={'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6}.get(roman)
            if roman=='已满级':value=6
    return {'key': key, 'value': value, 'label': name or str(value) if value is not None else '待确认',
            'confidence': round(float(confidence), 4), 'raw': joined, 'method': '文字识别', 'time': time.time()}


class Recognizer:
    def __init__(self, db):
        self.db = db; self.engine = None; self.templates = {}; self.battle = None
        from .opening import OpeningRecognizer
        self.opening=OpeningRecognizer(db)

    def load(self):
        if self.engine is None:
            from rapidocr import RapidOCR
            self.engine = RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                                          'EngineConfig.onnxruntime.inter_op_num_threads': 1,
                                          'Global.log_level': 'error', 'Global.max_side_len': 2000,
                                          'Det.limit_type': 'max', 'Det.limit_side_len': 1536})

    def scan(self, frame, box=None):
        h,w=frame.shape[:2];x,y,bw,bh=box or (0,0,1,1)
        x1,y1,x2,y2=int(x*w),int(y*h),int((x+bw)*w),int((y+bh)*h)
        crop=frame[y1:y2,x1:x2]
        if not crop.size:return []
        out=self.engine(crop,use_det=True,use_cls=False,use_rec=True)
        words=[]
        if out.txts is not None:
            for poly,txt,score in zip(out.boxes,out.txts,out.scores):
                p=np.asarray(poly);lo=p.min(axis=0);hi=p.max(axis=0)
                rx,ry,rw,rh=(float(lo[0]+x1)/w,float(lo[1]+y1)/h,float(hi[0]-lo[0])/w,float(hi[1]-lo[1])/h)
                words.append({'text':txt,'confidence':float(score),'x':rx+rw/2,'y':ry+rh/2,'rect':[rx,ry,rw,rh]})
        return words

    @staticmethod
    def crop(frame, region):
        h,w=frame.shape[:2];x,y,rw,rh=region['rect']
        return frame[max(0,int(y*h)):min(h,int((y+rh)*h)),max(0,int(x*w)):min(w,int((x+rw)*w))]

    def read_regions(self, frame, regions, words):
        crops=[];owners=[];observations=[[] for _ in regions]
        for i,region in enumerate(regions):
            if region.get('unavailable'):continue
            crop=self.crop(frame,region)
            if not crop.size:continue
            key=region['key'];seed=region.get('seed')
            if seed:observations[i].append((seed['text'],seed['confidence']))
            # A calibrated rectangle can contain multiple separate lines. Use
            # detected words as a whole observation, never pick one digit out
            # of an ambiguous "18 / 20" region.
            x,y,rw,rh=region['rect']
            selected=[a for a in words if x<=a['x']<=x+rw and y<=a['y']<=y+rh]
            if selected and not seed:
                observations[i].append((' '.join(a['text'] for a in selected),min(a['confidence'] for a in selected)))
            if region.get('avatar'):continue
            for gray in (False,True):
                c=cv2.resize(crop,None,fx=2,fy=2,interpolation=cv2.INTER_CUBIC)
                if gray:c=cv2.cvtColor(cv2.cvtColor(c,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
                c=cv2.copyMakeBorder(c,6,6,10,10,cv2.BORDER_REPLICATE)
                crops.append(c);owners.append(i)
        if crops:
            out=self.engine.recognize_txt(crops)
            for i,txt,score in zip(owners,out.txts,out.scores):observations[i].append((txt,float(score)))
        fields=[]
        for region,seen in zip(regions,observations):
            key=region['key'];field=vote(key,seen,self.db)
            crop=self.crop(frame,region)
            if region.get('roman'):
                shape=hud.roman_bars(crop)
                if shape is not None and all(f['value'] in (None,shape) for f in [interpret(key,[o],self.db) for o in seen] if f['confidence']>=.65):
                    field.update(value=shape,label=str(shape),confidence=.97,method='LEVEL 锚点 + 罗马数字形状核验')
            if region.get('avatar') and crop.size and key.startswith(('field:','bench:','shop:')):
                oid,score=self.avatar(crop)
                if field['value'] and oid and field['value']!=oid:field.update(value=None,label='文字与头像不一致',confidence=0)
                elif oid and field['value'] is None:field.update(value=oid,label=self.db.ops[oid]['name'],confidence=score,method='头像相似度（需校准）')
            field['rect']=region['rect']
            fields.append(field)
        return fields

    def avatar(self, crop):
        if not self.templates:
            for oid in self.db.ops:
                blob = self.db.image_bytes(oid)
                if blob:
                    image = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
                    self.templates[oid] = cv2.resize(image, (64, 64)).astype(np.float32)
        sample = cv2.resize(crop, (64, 64)).astype(np.float32)
        scores = sorted([(float(cv2.matchTemplate(sample, t, cv2.TM_CCOEFF_NORMED)[0, 0]), oid)
                         for oid, t in self.templates.items()], reverse=True)
        if len(scores) >= 2 and scores[0][0] >= .94 and scores[0][0] - scores[1][0] >= .08:
            return scores[0][1], scores[0][0]
        return None, scores[0][0] if scores else 0

    def recognize(self, frame, profile=None):
        start = time.perf_counter(); h, w = frame.shape[:2]
        profile = profile or {'regions': []}
        review=profile.get('opening_review',False)
        opening=self.opening.recognize(frame,review=review,in_match=profile.get('in_match',False))
        if opening:return opening
        if review:
            return {'fields':[],'words':[],'candidates':[],'regions':[],'mode':'opening-review','notes':['请在游戏中打开本局信息，展示完整盟约图标后重新识别'],
                    'shop_slots':[],'battlefield':None,'layout_valid':False,'complete':False,'size':[w,h],
                    'elapsed_ms':round((time.perf_counter()-start)*1000),'time':time.time()}
        self.load()
        profile = profile or {'regions': []}
        ref = profile.get('aspect')
        if ref and abs(w / h - ref) / ref > .035:
            raise ValueError('游戏宽高比与校准不一致，请切换或重新校准识别布局')
        ocr_regions=[r for r in profile.get('regions',[]) if r['key'] not in ('battle_field','battle_bench')]
        automatic=not ocr_regions
        if automatic:
            # Local detection preserves tiny HUD text and avoids scanning the
            # name-less battlefield sprites as if they were shop portraits.
            words=self.scan(frame,(0,0,1,.21))+self.scan(frame,(0,.59,1,.41))
            layout=hud.locate(words,hud.price_badges(frame),self.db,w/h)
            regions=layout['regions']
            hud.refine_refresh(frame,regions)
        else:
            words=self.scan(frame);regions=ocr_regions
            layout={'valid':True,'notes':[],'slots':[]}
        fields=self.read_regions(frame,regions,words)
        if automatic:
            offers=[f for f in fields if f['key'].startswith(('shop:','offer:','cost:'))]
            usable=layout.get('shop_valid') and offers and all(f['value'] is not None and f['confidence']>=.92 for f in offers)
            payload=[{k:f[k] for k in ('key','value')} for f in offers]
            fields.append({'key':'shop_snapshot','value':json.dumps(payload,ensure_ascii=False,sort_keys=True) if usable else None,
                           'label':f'{len(layout["slots"])} 件商品已对应' if usable else '商店待确认',
                           'confidence':min((f['confidence'] for f in offers),default=0) if usable else 0,
                           'method':'逐帧定位 · 整组稳定后更新','raw':'','time':time.time()})
        if automatic and not layout['valid']:
            fields=[interpret(k,[],self.db) for k in ('phase','round','gold','level','shop_snapshot')]
        battle_result=None
        if profile.get('battle_enabled',True):
            from .battle import BattleRecognizer,default_zones,observation_fields
            zones=default_zones(regions)
            custom={r['key'].removeprefix('battle_'):r['rect'] for r in profile.get('regions',[]) if r['key'] in ('battle_field','battle_bench')}
            if zones:zones.update(custom)
            elif len(custom)==2:zones=custom
            phase=next((f for f in fields if f['key']=='phase'),{})
            if zones and layout['valid'] and phase.get('value')=='整备' and phase.get('confidence',0)>=.92:
                try:
                    if self.battle is None:self.battle=BattleRecognizer()
                    battle_result={**self.battle.detect(frame,zones),'active':True,'zones':zones}
                    sprites=observation_fields(battle_result);fields+=sprites
                    regions=regions+[{'key':f['key'],'rect':f['rect'],'label':f['detection']['name']+(' · 待确认' if f['value'] is None else ''),'pending':f['value'] is None} for f in sprites]
                    count=sum(d['reliable'] for d in battle_result['detections'])
                    layout['notes'].append(f'小人比对 {count} 个可用结果；完整阵容、精锐和装备待核对')
                except (OSError,ValueError,cv2.error) as e:
                    battle_result={'active':False,'detections':[],'error':str(e)}
                    layout['notes'].append('小人索引不可用，文字识别继续；请检查安装资源')
            else:
                battle_result={'active':False,'detections':[]}
                layout['notes'].append('小人比对等待整备阶段和展开的商店')
        candidates = []
        for a in words:
            name = exact_entity(a['text'], self.db.by_name)
            if name: candidates.append({'name': name, 'confidence': a['confidence']})
        return {'fields': fields, 'words': words, 'candidates': candidates,'regions':regions,
                'mode':'auto' if automatic else 'manual','layout_valid':layout['valid'],'notes':layout['notes'],
                'shop_slots':layout['slots'],'shop_valid':layout.get('shop_valid',False),
                'battlefield':battle_result,
                'elapsed_ms': round((time.perf_counter() - start)*1000), 'time': time.time(), 'size': [w, h],
                'complete': bool(fields) and layout['valid'] and all(f['value'] is not None and f['confidence']>=.92 for f in fields)}


def vote(key, observations, db):
    """Independent crop views must agree; high-score contradictions abstain."""
    choices=[interpret(key,[o],db) for o in observations]
    good=[f for f in choices if f['value'] is not None and f['confidence']>=.90]
    values={f['value'] for f in good}
    if len(values)==1 and len(good)>=2:
        result=max(good,key=lambda f:f['confidence']).copy()
    else:
        result=interpret(key,[],db)
        if len(values)>1:result['label']='多视图结果冲突'
    if key in ('gold','round','level','upgrade_cost','refresh_cost') or key.startswith('cost:'):
        if any(score>=.9 and len(re.findall(r'\d+',text))>1 for text,score in observations):
            result.update(value=None,label='区域包含多个数字',confidence=0)
    result.update(raw=' / '.join(dict.fromkeys(o[0] for o in observations)),method='区域放大 + 多视图核验')
    return result


def applicable_fields(result, accepted):
    if result.get('mode')!='auto':return accepted
    # Auto shop data is applied only through the complete snapshot, even when
    # some individual fields stabilise earlier than their neighbouring cards.
    return [f for f in accepted if not f['key'].startswith(('shop:','offer:','cost:'))]


class StabilityGate:
    def __init__(self, repeats=2): self.repeats = repeats; self.previous = {}; self.counts = {}
    def reset(self): self.previous.clear(); self.counts.clear()
    def accept(self, fields, threshold):
        result = []
        present = {f['key'] for f in fields}
        for key in set(self.previous) - present:
            self.previous.pop(key, None); self.counts.pop(key, None)
        for f in fields:
            key, value = f['key'], f['value']
            if key=='opening_snapshot' and value is not None:
                from .opening import snapshot_key
                try:value=snapshot_key(json.loads(value))
                except (ValueError,TypeError,KeyError):value=None
            if value is None or f['confidence'] < threshold:
                self.previous.pop(key, None); self.counts[key] = 0; continue
            self.counts[key] = self.counts.get(key, 0) + 1 if self.previous.get(key) == value else 1
            self.previous[key] = value
            if self.counts[key] >= self.repeats: result.append(f)
        return result


def apply_fields(state, fields, manual=False):
    """Patch only known, visible fields. Unseen equipment/elite data is preserved."""
    now = time.time()
    opening=next((f for f in fields if f['key']=='opening_snapshot' and f['value'] is not None),None)
    if opening:
        from .opening import apply_snapshot
        apply_snapshot(state,json.loads(opening['value']))
        state['field_meta']['opening_snapshot']={'time':now,'source':'手动确认' if manual else '自动识别','confidence':opening['confidence']}
        return
    from .battle import apply_observations
    apply_observations(state,fields,manual)
    fields=[f for f in fields if not f['key'].startswith('sprite:')]
    snapshot=next((f for f in fields if f['key']=='shop_snapshot'),None)
    if snapshot:
        # One transaction for the whole shop: a shifted equipment card must
        # never leave an operator from the previous level in its old slot.
        fields=[f for f in fields if not f['key'].startswith(('shop:','cost:','offer:')) and f['key']!='shop_snapshot']
        if snapshot['value'] is not None:
            observed=[{**f,'confidence':snapshot['confidence']} for f in json.loads(snapshot['value'])]
            locked=any(m.get('locked') for k,m in state['field_meta'].items() if k.startswith(('shop:','cost:','offer:')))
            if manual or not locked:
                state['shop']=[];state['recognized_offers']={}
                state['field_meta']={k:v for k,v in state['field_meta'].items() if not k.startswith(('shop:','cost:','offer:'))}
                fields+=observed
                state['field_meta']['shop_snapshot']={'time':now,'source':'手动确认' if manual else '自动识别','confidence':snapshot['confidence']}
            else:state['field_meta']['shop_snapshot']={'uncertain':True}
    ordered = sorted(fields, key=lambda f: (f['key'].startswith(('cost:', 'elite:', 'gear:')), f['key']))
    for f in ordered:
        key, value = f['key'], f['value']
        if value is None: continue
        prior = state['field_meta'].get(key, {})
        if prior.get('locked') and not manual: continue
        if key in LABELS:
            if key=='upgrade_cost' and state.get('level')==6:continue
            state[key] = value
            if key=='level' and value==6:
                state['upgrade_cost']=None
                state['field_meta'].pop('upgrade_cost',None)
        elif key.startswith('stack:'):
            state['stacks'][key.split(':', 1)[1]] = value
        elif key.startswith('shop:'):
            idx = int(key.split(':')[1])
            slots = {x.get('slot', i): x for i, x in enumerate(state['shop'])}
            old = slots.get(idx, {})
            slots[idx] = {**old, 'op_id': value, 'slot': idx,
                          'cost': old.get('cost') if old.get('op_id') == value else None}
            state['shop'] = [slots[i] for i in sorted(slots)]
        elif key.startswith('cost:'):
            idx = int(key.split(':')[1])
            for i, item in enumerate(state['shop']):
                if item.get('slot', i) == idx: item['cost'] = value
            if str(idx) in state.get('recognized_offers',{}):state['recognized_offers'][str(idx)]['cost']=value
        elif key.startswith('offer:'):
            state.setdefault('recognized_offers',{})[key.split(':')[1]]={'name':value,'cost':None}
        elif key.startswith(('field:', 'bench:')):
            zone, slot = key.split(':')
            old = next((u for u in state['units'] if u.get('recognition_key') == key), None)
            if old is None:
                old = unit(value, zone); old['recognition_key'] = key; state['units'].append(old)
            elif old['op_id'] != value:
                # Changed identity cannot inherit equipment or elite status from the previous occupant.
                new = unit(value, zone); new['recognition_key'] = key
                state['units'][state['units'].index(old)] = new
        elif key.startswith('elite:'):
            target = key.removeprefix('elite:')
            for u in state['units']:
                if u.get('recognition_key') == target: u['elite'] = bool(value)
        elif key.startswith('equipment:'):
            inventory_slots = state.setdefault('recognized_inventory', {})
            inventory_slots[key] = value
            # Inventory observations are shown separately until the user merges them, avoiding duplicates.
        elif key.startswith('strategy:'):
            if value not in state['strategies']: state['strategies'].append(value)
        state['field_meta'][key] = {'time': now, 'source': '手动确认' if manual else '自动识别',
                                     'confidence': f['confidence'], 'locked': prior.get('locked', False)}


def mark_uncertain(state, fields, threshold):
    for f in fields:
        if f['value'] is None or f['confidence'] < threshold:
            old = state['field_meta'].get(f['key'], {})
            if not old.get('locked'):
                state['field_meta'][f['key']] = {**old, 'uncertain': True}
            if f['key']=='shop_snapshot':
                for k,m in state['field_meta'].items():
                    if k.startswith(('shop:','cost:','offer:')):m['uncertain']=True


def ready_for_auto(state, required, freshness=10):
    now = time.time(); missing = []
    for key in required:
        meta = state['field_meta'].get(key, {})
        transient = key in ('gold', 'round', 'phase', 'upgrade_cost', 'refresh_cost') or key.startswith(('shop:', 'cost:'))
        if meta.get('locked') and not transient: continue
        if meta.get('uncertain') or now - meta.get('time', 0) > freshness: missing.append(key)
    return missing
