"""Offline sprite geometry + appearance verification; never emits game input.

Scores are evidence gates, not measured probabilities. The roster is partial:
absence from a screenshot is never proof that an operator has left the board.
"""
from __future__ import annotations
from pathlib import Path
import json
import hashlib
import math
import sys
import time
import uuid
import cv2
import numpy as np
from .core import unit


def index_path():
    base=Path(sys._MEIPASS)/'assets' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'assets'
    return base/'battle-index.npz'


def inside(point,rect):
    x,y,w,h=rect
    return x<=point[0]<=x+w and y<=point[1]<=y+h


def center(rect):
    x,y,w,h=rect
    return x+w/2,y+h*.7


def overlap(a,b):
    x,y,w,h=a;xx,yy,ww,hh=b
    area=max(0,min(x+w,xx+ww)-max(x,xx))*max(0,min(y+h,yy+hh)-max(y,yy))
    return area/max(1e-9,min(w*h,ww*hh))


def default_zones(regions):
    prices=[r['rect'][1] for r in regions if r['key'].startswith('cost:')]
    if not prices:return None
    # Follow the current shop row. The band is for feet, not sprite heads.
    row=float(np.median(prices));split=row-.13
    return {'field':[.12,.20,.56,max(.01,split-.20)],'bench':[.10,split,.80,.115]}


class BattleRecognizer:
    def __init__(self,path=None):
        self.path=Path(path) if path else index_path();self.loaded=False;self.tracks={};self.images={}

    def reset(self):self.tracks.clear()

    def load(self):
        if self.loaded:return
        with np.load(self.path,allow_pickle=False) as f:
            self.meta=json.loads(str(f['meta']));self.refs=self.meta['refs']
            self.desc=f['descriptors'].astype(np.float32);self.points=f['points'];self.owners=f['owners']
            clusters=f['cluster'];self.png=f['png'];self.offsets=f['offsets']
        order=np.argsort(clusters,kind='stable');bounds=np.searchsorted(clusters[order],np.arange(len(self.desc)+1))
        self.members=[order[bounds[i]:bounds[i+1]] for i in range(len(self.desc))]
        self.opids=[self.refs[int(self.owners[m[0]])]['op_id'] for m in self.members]
        self.sift=cv2.SIFT_create(contrastThreshold=.018,edgeThreshold=16)
        self.matcher=cv2.FlannBasedMatcher(dict(algorithm=1,trees=4),dict(checks=48))
        self.matcher.add([self.desc]);self.matcher.train();self.loaded=True

    def template(self,rid):
        if rid not in self.images:
            self.images[rid]=cv2.imdecode(self.png[self.offsets[rid]:self.offsets[rid+1]],cv2.IMREAD_UNCHANGED)
        return self.images[rid]

    def detect(self,frame,zones):
        start=time.perf_counter();self.load()
        # A common working scale prevents viewport size from changing the gates.
        h0,w0=frame.shape[:2];w=2048;h=round(h0*w/w0)
        im=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA if w0>=w else cv2.INTER_CUBIC)
        mask=np.zeros((h,w),np.uint8)
        for x,y,rw,rh in zones.values():
            mask[max(0,int((y-.18)*h)):min(h,int((y+rh)*h)),max(0,int(x*w)):min(w,int((x+rw)*w))]=255
        mask[:int(h*.165)]=0
        kp,d=self.sift.detectAndCompute(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),mask)
        if d is None:return {'detections':[],'elapsed_ms':round((time.perf_counter()-start)*1000),'templates':len(self.refs)}
        groups={}
        def add(cid,scene):
            for source in self.members[cid]:
                rid=int(self.owners[source]);groups.setdefault(rid,{})[(int(source),scene)]=(self.points[source],kp[scene].pt)
        reverse=cv2.FlannBasedMatcher(dict(algorithm=1,trees=3),dict(checks=32))
        for pair in reverse.knnMatch(self.desc,d,k=2):
            if len(pair)!=2:continue
            a,b=pair
            if a.distance<300 and a.distance<.80*b.distance:add(a.queryIdx,a.trainIdx)
        # Scene-to-model pass retains two identical copies which would tie in
        # the reverse ratio test. Compare different identities, not idle phases.
        for pair in self.matcher.knnMatch(d,k=12):
            a=pair[0];oid=self.opids[a.trainIdx]
            rival=next((b.distance for b in pair[1:] if self.opids[b.trainIdx]!=oid),280)
            if a.distance<min(260,.80*rival):add(a.trainIdx,a.queryIdx)
        found=[]
        for rid,matches in groups.items():
            if len(matches)<5:continue
            pairs=list(matches.values());src=np.asarray([a[0] for a in pairs],np.float32);dst=np.asarray([a[1] for a in pairs],np.float32)
            ref=self.refs[rid]
            # Remove one spatial instance's inliers, then look for another.
            for _ in range(4):
                if len(src)<5:break
                M,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=800)
                if M is None:break
                good=inliers.ravel().astype(bool);a=src[good];b=dst[good];src=src[~good];dst=dst[~good]
                unique=len(np.unique(np.round(b/2),axis=0));scale=float(np.hypot(M[0,0],M[0,1]));angle=float(np.degrees(np.arctan2(M[1,0],M[0,0])))
                if unique<5 or abs(angle)>9 or not .40<scale<1.85:continue
                spread=np.ptp(a,axis=0)/ref['size']
                if spread[0]<.10 or spread[1]<.16:continue
                rw,rh=ref['size'];corners=cv2.transform(np.asarray([[[0,0],[rw,0],[rw,rh],[0,rh]]],np.float32),M)[0]
                low=corners.min(0);high=corners.max(0);box=[float(low[0]/w),float(low[1]/h),float((high[0]-low[0])/w),float((high[1]-low[1])/h)]
                feet=((box[0]+box[2]/2),box[1]+box[3])
                zone=next((k for k,r in zones.items() if inside(feet,r)),None)
                if not zone or box[0]<0 or box[1]<.15 or box[0]+box[2]>1 or box[1]+box[3]>.82:continue
                template=self.template(rid);aligned=cv2.warpAffine(im,cv2.invertAffineTransform(M),(rw,rh))
                solid=template[:,:,3]>220;aa=aligned[solid].astype(float);bb=template[:,:,:3][solid].astype(float)
                error=float(np.abs(aa-bb).mean());corr=float(np.corrcoef(aa.mean(1),bb.mean(1))[0,1])
                if not math.isfinite(corr) or corr<.36 or error>58:continue
                # Strong geometry AND independently matching foreground pixels.
                reliable=unique>=6 and corr>=.46 and error<=50
                score=min(.985,.93+max(0,unique-6)*.002) if reliable else .80
                found.append(dict(op_id=ref['op_id'],name=ref['name'],zone=zone,rect=[round(v,6) for v in box],
                                  direction=ref['direction'],flip=ref['flip'],matches=unique,correlation=round(corr,3),
                                  pixel_error=round(error,2),confidence=score,reliable=reliable))
        found.sort(key=lambda a:(a['reliable'],a['matches'],a['correlation']),reverse=True)
        kept=[]
        for candidate in found:
            prior=next((p for p in kept if overlap(p['rect'],candidate['rect'])>.55),None)
            if prior:
                if prior['op_id']!=candidate['op_id'] and candidate['reliable']:
                    prior.update(reliable=False,confidence=.70,conflict=True)
                continue
            kept.append(candidate)
        self.track(kept)
        return {'detections':kept,'elapsed_ms':round((time.perf_counter()-start)*1000),'templates':len(self.refs)}

    def track(self,detections):
        now=time.monotonic();unused={k:v for k,v in self.tracks.items() if now-v['seen']<30}
        for d in detections:
            options=sorted([(math.dist(center(d['rect']),center(v['rect'])),k) for k,v in unused.items() if v['op_id']==d['op_id']])
            if options and options[0][0]<.12:
                tid=options[0][1];unused.pop(tid)
            else:tid=uuid.uuid4().hex[:12]
            d['track_id']=tid;self.tracks[tid]={**d,'seen':now}
        self.tracks={k:v for k,v in self.tracks.items() if now-v['seen']<30}


def observation_fields(battle):
    fields=[];now=time.time()
    for d in battle['detections']:
        fields.append(dict(key='sprite:'+d['track_id'],value=f'{d["op_id"]}|{d["zone"]}' if d['reliable'] else None,
                           label=d['name']+(' · 战场' if d['zone']=='field' else ' · 整备')+('' if d['reliable'] else ' · 待确认'),
                           confidence=d['confidence'],method='小人模型 · 正背面 / 动作核验',
                           raw=f'{d["matches"]} 个特征点 · 外观相关 {d["correlation"]:.2f}',time=now,rect=d['rect'],detection=d))
    return fields


def apply_observations(state,fields,manual=False):
    """Match instances one-to-one. Preserve gear, elite and hand-maintained units."""
    used=set();now=time.time()
    for f in fields:
        if not f['key'].startswith('sprite:') or f['value'] is None:continue
        d=f['detection'];key=f['key'];prior=state['field_meta'].get(key,{})
        if prior.get('locked') and not manual:continue
        candidates=[u for u in state['units'] if u['uid'] not in used and u['op_id']==d['op_id']]
        old=next((u for u in candidates if u.get('recognition_key')==key),None)
        if old is None and manual:
            corrected=next((u for u in state['units'] if u.get('recognition_key')==key and u['uid'] not in used),None)
            if corrected is not None:
                uid=corrected['uid'];corrected.clear();corrected.update(unit(d['op_id'],d['zone']),uid=uid,sprite_managed=True,sprite_elite_unknown=True);old=corrected
        if old is None:
            positioned=sorted([(math.dist(center(u['sprite_rect']),center(d['rect'])),u['uid'],u) for u in candidates if u.get('sprite_rect')])
            if positioned and positioned[0][0]<.12:old=positioned[0][2]
            elif len(candidates)==1 and candidates[0].get('sprite_managed') and sum(x.get('detection',{}).get('op_id')==d['op_id'] for x in fields)==1:
                old=candidates[0] # one identity moved; equipment follows it
        if old is None:
            # An existing manual copy is ambiguous. Show the observation, but
            # do not silently claim it or add a possible duplicate.
            if any(not u.get('sprite_managed') for u in candidates):
                state['field_meta'][key]={'time':now,'uncertain':True,'source':'与手动阵容待核对'};continue
            old=unit(d['op_id'],d['zone']);old['sprite_managed']=True;old['sprite_elite_unknown']=True;state['units'].append(old)
        previous=old.get('recognition_key')
        if previous and previous!=key:state['field_meta'].pop(previous,None)
        old.update(recognition_key=key,sprite_rect=d['rect'],sprite_missing=False)
        if old.get('sprite_managed'):old['zone']=d['zone']
        used.add(old['uid']);state['field_meta'][key]={'time':now,'source':'手动确认' if manual else '自动识别','confidence':f['confidence'],'locked':prior.get('locked',False)}


def mark_missing(state,accepted_keys):
    for u in state['units']:
        key=u.get('recognition_key','')
        if u.get('sprite_managed') and key not in accepted_keys:
            meta=state['field_meta'].setdefault(key,{})
            if not meta.get('locked'):u['sprite_missing']=True;meta['uncertain']=True


def known_units(state):
    return [u for u in state['units'] if not u.get('sprite_missing')]


def roster_signature(state):
    fields=('uid','op_id','zone','elite','sprite_missing','sprite_elite_unknown')
    return hashlib.sha256(json.dumps([state.get('round'),[{k:u.get(k) for k in fields} for u in state['units']]],sort_keys=True).encode()).hexdigest()


def update_roster_status(state):
    prior=state['field_meta'].get('battle_roster',{})
    state['field_meta']['battle_roster']={**prior,'time':time.time(),'uncertain':prior.get('signature')!=roster_signature(state)}
