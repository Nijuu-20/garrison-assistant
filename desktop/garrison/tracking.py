"""Explicit watch lists and conservative, per-frame shop matches. No game input."""
from __future__ import annotations
import math,time
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
    """Confirm identities, retain visually unchanged misses, expire each slot separately."""
    def __init__(self):self.reset()
    def reset(self):self.previous={};self.stable=[];self.reference=None;self.last_seen={};self.pixel_failures={}
    @staticmethod
    def key(item):return (item['slot'],item_key(item))
    def discard(self,items):
        keys={self.key(i) for i in items}
        self.stable=[i for i in self.stable if self.key(i) not in keys]
        for key in keys:
            self.previous.pop(key,None);self.last_seen.pop(key,None);self.pixel_failures.pop(key,None)
    def accept(self,db,result,threshold=.92,frames=2,frame=None,now=None):
        now=time.monotonic() if now is None else now
        current={};stable=[]
        for item in shop_observations(db,result,threshold):
            key=(item['slot'],item_key(item));old=self.previous.get(key)
            same=old and max(abs(a-b) for a,b in zip(old['rect'],item['rect']))<.006
            count=old['count']+1 if same else 1
            current[key]={'rect':item['rect'],'count':count}
            if count>=max(1,frames):
                prior=next((m for m in self.stable if self.key(m)==key),None)
                if same and prior:item={**item,'rect':prior['rect']}
                stable.append(item);self.last_seen[key]=now
        slots={s['slot']:s for s in result.get('shop_slots',[])}
        if frame is not None and result.get('layout_valid') and not result.get('opening'):
            for item in self.stable:
                key=self.key(item);slot=slots.get(item['slot'],{})
                if key in current or any(k[0]==item['slot'] for k in current):continue
                if (slot.get('kind')==item['kind'] and valid_rect(slot.get('rect'))
                    and max(abs(a-b) for a,b in zip(slot['rect'],item['rect']))<.006
                    and now-self.last_seen.get(key,0)<=6
                    and same_shop_pixels(frame,self.reference,[item])):
                    stable.append(item);current[key]=self.previous[key]
        self.previous=current;self.stable=stable
        self.last_seen={self.key(i):self.last_seen[self.key(i)] for i in stable}
        self.reference=frame.copy() if frame is not None else None
        return stable
    def matches(self,tracked):
        keys={item_key(i) for i in tracked}
        return [i for i in self.stable if item_key(i) in keys]
    def visible_matches(self,frame,reference,matches,now=None):
        """Two quick polls reject a marginal mismatch; a blank/changed card clears immediately."""
        now=time.monotonic() if now is None else now;expired=[]
        for item in matches:
            key=self.key(item);status=shop_pixel_status(frame,reference,item)
            if status=='same':self.pixel_failures.pop(key,None);continue
            since=self.pixel_failures.setdefault(key,now)
            if status=='changed' or now-since>=.35:expired.append(item)
        self.discard(expired)
        gone={self.key(i) for i in expired}
        return [i for i in matches if self.key(i) not in gone]


def sample_patch(frame,rect):
    if frame is None or not valid_rect(rect):return None
    h,w=frame.shape[:2];x,y,rw,rh=rect
    crop=frame[int(y*h):min(h,int((y+rh)*h)+1),int(x*w):min(w,int((x+rw)*w)+1)]
    if not crop.size:return None
    return cv2.resize(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(96,28),interpolation=cv2.INTER_AREA)


def same_shop_pixels(frame,reference,matches):
    """Fast guard on static name plates, avoiding animated portraits and effects."""
    return bool(matches) and all(shop_pixel_status(frame,reference,m)=='same' for m in matches)


def shop_pixel_status(frame,reference,item):
    if frame is None or reference is None or frame.shape!=reference.shape:return 'changed'
    a=sample_patch(frame,item['sample_rect']);b=sample_patch(reference,item['sample_rect'])
    if a is None or b is None or min(float(a.std()),float(b.std()))<8:return 'changed'
    # Ignore uniform hover brightness and up to two reduced-pixel translations.
    template=b[2:-2,2:-2]
    score=cv2.matchTemplate(a,template,cv2.TM_CCOEFF_NORMED)
    _,corr,_,(x,y)=cv2.minMaxLoc(score)
    aligned=a[y:y+template.shape[0],x:x+template.shape[1]].astype(np.float32)
    base=template.astype(np.float32)
    error=float(np.mean(np.abs((aligned-aligned.mean())-(base-base.mean()))))
    if corr>=.94 and error<=14:return 'same'
    return 'changed' if corr<.65 or error>45 else 'uncertain'
