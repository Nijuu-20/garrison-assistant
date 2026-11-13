"""Compile the user's sprite DB plus optional rendered idle phases, read-only."""
from pathlib import Path
import hashlib
import json
import sqlite3
import time
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=ROOT/'outputs/regulation_battle_models_2026-11-13/卫戍协议_规程_战场小人数据库.sqlite'
OUT=HERE/'assets/battle-index.npz'

def build():
    start=time.perf_counter();sift=cv2.SIFT_create(contrastThreshold=.018,edgeThreshold=16)
    with sqlite3.connect(SOURCE.as_uri()+'?mode=ro',uri=True) as c:
        names=dict(c.execute('SELECT operator_id,name FROM operators'))
        rows=[(m,o,d,'database-preview',p) for m,o,d,p in c.execute('SELECT m.model_id,m.operator_id,m.direction,p.png FROM models m JOIN previews p USING(model_id)')]
    extra=HERE/'build/battle-templates/manifest.json'
    if extra.exists():
        for r in json.loads(extra.read_text('utf8')):
            rows.append((r['model_id'],r['operator_id'],r['model_id'].split('-')[1],f'{r["animation"]}@{r["time"]:.3f}',(extra.parent/r['file']).read_bytes()))
    refs=[];descs=[];points=[];owners=[];pngs=[];offsets=[0]
    for mid,oid,direction,animation,png in rows:
        raw=cv2.imdecode(np.frombuffer(png,np.uint8),cv2.IMREAD_UNCHANGED)
        ys,xs=np.where(raw[:,:,3]>80)
        if not len(xs):continue
        raw=raw[ys.min():ys.max()+1,xs.min():xs.max()+1]
        for flip in (False,True):
            im=cv2.resize(raw,(round(raw.shape[1]*140/raw.shape[0]),140),interpolation=cv2.INTER_AREA)
            if flip:im=cv2.flip(im,1)
            mask=cv2.erode((im[:,:,3]>180).astype(np.uint8)*255,np.ones((3,3),np.uint8))
            kp,d=sift.detectAndCompute(cv2.cvtColor(im[:,:,:3],cv2.COLOR_BGR2GRAY),mask)
            if d is None:continue
            rid=len(refs);encoded=cv2.imencode('.png',im)[1];pngs.append(encoded);offsets.append(offsets[-1]+len(encoded))
            refs.append(dict(model_id=mid,op_id=oid,name=names[oid],direction=direction,flip=flip,animation=animation,size=[im.shape[1],im.shape[0]]))
            descs.append(d);points.extend(k.pt for k in kp);owners.extend([rid]*len(d))
    descs=np.vstack(descs);owners=np.asarray(owners,np.int32);points=np.asarray(points,np.float32)
    # Similar descriptors recur in neighbouring animation phases. Share the
    # query while retaining every original template coordinate for geometry.
    cluster=np.full(len(descs),-1,np.int32);centers=[]
    op_numbers=np.asarray([int(r['op_id'][2:]) for r in refs])[owners]
    for oid in np.unique(op_numbers):
        indices=np.flatnonzero(op_numbers==oid);ds=descs[indices]
        matcher=cv2.FlannBasedMatcher(dict(algorithm=1,trees=2),dict(checks=24))
        neighbors=matcher.knnMatch(ds,ds,k=min(16,len(ds)))
        for i,pair in enumerate(neighbors):
            if cluster[indices[i]]>=0:continue
            cid=len(centers);centers.append(ds[i]);cluster[indices[i]]=cid
            for m in pair:
                j=indices[m.trainIdx]
                if m.distance<=55 and cluster[j]<0:cluster[j]=cid
    meta=dict(schema=1,operators=len(names),models=len({r['model_id'] for r in refs}),templates=len(refs),
              descriptors=len(descs),queries=len(centers),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              source_name=SOURCE.name,phase='整备待机',default_skins_only=True,independent_summons=False,refs=refs)
    np.savez_compressed(OUT,meta=np.asarray(json.dumps(meta,ensure_ascii=False)),descriptors=np.asarray(centers,np.uint8),
                        points=points,owners=owners,cluster=cluster,png=np.concatenate(pngs),offsets=np.asarray(offsets,np.int64))
    (HERE/'assets/battle-index.json').write_text(json.dumps({k:v for k,v in meta.items() if k!='refs'}|{'bytes':OUT.stat().st_size},ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:v for k,v in meta.items() if k!='refs'}|{'ms':round((time.perf_counter()-start)*1000)},ensure_ascii=False))

if __name__=='__main__':build()
