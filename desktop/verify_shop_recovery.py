"""Saved-image replay only. No live capture, game input or provider requests."""
import json,statistics,time
from pathlib import Path
import cv2,numpy as np
from garrison import __version__
from garrison.core import Database
from garrison.recognition import Recognizer

HERE=Path(__file__).parent;OUT=HERE/'build/shop-recovery';OUT.mkdir(exist_ok=True)
db=Database();r=Recognizer(db);checks=[];timings=[]
def check(name,ok):
    checks.append({'test':name,'passed':bool(ok)})
    assert ok,name
def load(path):return cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
fixtures=json.loads((HERE/'build/level-transition/fixtures.json').read_text('utf8'))
fixture=next(f for f in fixtures if f['expected']['level']==4)
source=load(HERE/fixture['file']);scan=r.scan;names=set(db.by_name)|set(db.equipment)
def lost_global_names(frame,box=(0,0,1,1)):
    words=scan(frame,box)
    return [a for a in words if a['text'].strip() not in names] if box[2]==1 else words
for width in (source.shape[1],1280):
    frame=source if width==source.shape[1] else cv2.resize(source,(width,round(width*source.shape[0]/source.shape[1])),interpolation=cv2.INTER_AREA)
    r.scan=lost_global_names
    try:result=r.recognize(frame,{'battle_enabled':False})
    finally:r.scan=scan
    fields={f['key']:f for f in result['fields']}
    for key,value in fixture['expected'].items():
        if key.startswith('shop:'):value=db.by_name[value]['operator_id']
        check(f'{width} missing-global-names {key}',fields.get(key,{}).get('value')==value and fields[key]['confidence']>=.92)
    check(f'{width} all six cards recovered',result['shop_valid'] and not fields['shop_snapshot']['partial'])
    (OUT/f'recovery-{width}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')

frame=load(HERE/'build/battle-recognition/pc-round14-b.png')
result=r.recognize(frame,{'battle_enabled':False})
snapshot=next(f for f in result['fields'] if f['key']=='shop_snapshot')
known=json.loads(snapshot['value'])
check('real unresolved cards do not block four verified cards',snapshot['partial'] and snapshot['pending_slots']==[3,5] and len(known)==8)
check('unknown slots are not guessed',not any(f['key'].endswith((':3',':5')) for f in known))
(OUT/'partial-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
# Warm both model paths first. Compare the same saved frame and process, with
# and without waiting for battlefield matching; this is not end-to-end live latency.
r.recognize(frame,{'battle_enabled':True})
for repeat in range(3):
    for full in ((False,True) if repeat%2==0 else (True,False)):
        start=time.perf_counter();result=r.recognize(frame,{'battle_enabled':full})
        timings.append({'stage':'shop_and_battle' if full else 'shop_first','ms':round((time.perf_counter()-start)*1000)})
medians={kind:round(statistics.median(t['ms'] for t in timings if t['stage']==kind)) for kind in ('shop_and_battle','shop_first')}
report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'timings':timings,'median_ms':medians,
    'scope':'Real saved level4 and round14 images. Initial global name omissions are simulated; local recovery uses actual pixels. Timings are warmed saved-frame work, not live response latency or population accuracy. No desktop control or capture performed.'}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({'passed':report['passed'],'checks':len(checks),'median_ms':medians}),flush=True)
