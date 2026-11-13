"""Explicit watch lists and conservative, per-frame shop matches. No game input."""
from __future__ import annotations
import math
import cv2
import numpy as np
from .core import fingerprint


def item_key(item):
    return ('operator:' + item['op_id']) if item['kind']=='operator' else ('equipment:' + item['name'])


def normalize_items(db, values, state=None, limit=220):
    if not isinstance(values,list):return []
    allowed=None
    if state is not None and state.get('opening'):
        from .advice import ban_context
        c=ban_context(db,state);allowed=set(c['available_operator_ids'])
    result=[];seen=set()
    for raw in values[:500]:
        if not isinstance(raw,dict):continue
        kind=raw.get('kind');oid=raw.get('op_id');name=raw.get('name')
        if kind=='operator' and isinstance(oid,str) and oid in db.ops:
            if allowed is not None and oid not in allowed:continue
            item={'kind':kind,'op_id':oid,'name':db.ops[oid]['name']}
        elif kind=='equipment' and isinstance(name,str) and name.removesuffix(' · 进阶') in db.equipment:
            item={'kind':kind,'name':name.removesuffix(' · 进阶')}
        else:continue
        key=item_key(item)
        if key in seen:continue
        seen.add(key)
        if isinstance(raw.get('reason'),str):item['reason']=raw['reason'].strip()[:220]
        result.append(item)
        if len(result)>=limit:break
    return result


def current_candidates(db,state,result,enabled=True):
    if not enabled or not result or result.get('fingerprint')!=fingerprint(state):return []
    if state.get('opening') and state['field_meta'].get('opening_snapshot',{}).get('uncertain'):return []
    return normalize_items(db,result.get('recommendation_list'),state,12)


def catalog(db,state):
    operators=normalize_items(db,[{'kind':'operator','op_id':oid} for oid in db.ops],state)
    return {
        'operators':[{**i,'tier':db.ops[i['op_id']]['tier'],'covenants':db.ops[i['op_id']]['covenants'],
                      'roles':db.ops[i['op_id']]['categories']} for i in operators],
        'equipment':[{k:e[k] for k in ('name','tier','effect','combination','consumable')} for e in db.equipment.values()],
    }


def valid_rect(r):
    return (isinstance(r,(list,tuple)) and len(r)==4
            and all(type(v) in (int,float) and math.isfinite(v) for v in r)
            and min(r[:2])>=0 and min(r[2:])>0 and r[0]+r[2]<=1.001 and r[1]+r[3]<=1.001)


def shop_observations(db,result,threshold=.92):
    if result.get('opening') or not result.get('layout_valid'):return []
    fields={f['key']:f for f in result.get('fields',[])}
    regions={r['key']:r['rect'] for r in result.get('regions',[]) if valid_rect(r.get('rect'))}
    slots=result.get('shop_slots',[])
    if result.get('mode')=='manual':
        slots=[{'slot':int(k.split(':')[1]),'key':k,'kind':'operator','rect':regions.get(k)}
               for k in fields if k.startswith('shop:') and k.split(':')[1].isdigit()]
    rows=[]
    for slot in slots:
        if slot.get('kind') not in ('operator','equipment'):continue
        key=slot['key'];f=fields.get(key,{})
        if f.get('value') is None or f.get('confidence',0)<threshold:continue
        raw={'kind':'operator','op_id':f['value']} if slot['kind']=='operator' else {'kind':'equipment','name':f['value']}
        items=normalize_items(db,[raw]);r=slot.get('rect');sample=regions.get(key)
        if not items or not valid_rect(r) or not valid_rect(sample):continue
        rows.append({**items[0],'slot':slot['slot'],'rect':list(r),'sample_rect':sample})
    return rows


class ShopWatch:
    """Require consecutive identity AND position agreement; never reuse old slots."""
    def __init__(self):self.reset()
    def reset(self):self.previous={};self.stable=[]
    def accept(self,db,result,threshold=.92,frames=2):
        current={};stable=[]
        for item in shop_observations(db,result,threshold):
            key=(item['slot'],item_key(item));old=self.previous.get(key)
            same=old and max(abs(a-b) for a,b in zip(old['rect'],item['rect']))<.006
            count=old['count']+1 if same else 1
            current[key]={'rect':item['rect'],'count':count}
            if count>=max(2,frames):stable.append(item)
        self.previous=current;self.stable=stable
        return stable
    def matches(self,tracked):
        keys={item_key(i) for i in tracked}
        return [i for i in self.stable if item_key(i) in keys]


def sample_patch(frame,rect):
    if frame is None or not valid_rect(rect):return None
    h,w=frame.shape[:2];x,y,rw,rh=rect
    crop=frame[int(y*h):min(h,int((y+rh)*h)+1),int(x*w):min(w,int((x+rw)*w)+1)]
    if not crop.size:return None
    return cv2.resize(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(96,28),interpolation=cv2.INTER_AREA)


def same_shop_pixels(frame,reference,matches):
    """Fast guard on static name plates, avoiding animated portraits and effects."""
    if frame is None or reference is None or frame.shape!=reference.shape:return False
    for m in matches:
        a=sample_patch(frame,m['sample_rect']);b=sample_patch(reference,m['sample_rect'])
        if a is None or b is None:return False
        if np.mean(cv2.absdiff(a,b))>9:return False
        if float(b.std())<8 or float(cv2.matchTemplate(a,b,cv2.TM_CCOEFF_NORMED)[0,0])<.94:return False
    return bool(matches)
