"""Real HUD replay plus explicitly synthetic resize/occlusion/transition checks."""
import copy,json,os,time
from pathlib import Path
import cv2,numpy as np
from garrison import __version__
from garrison.core import Database,new_state
from garrison.recognition import Recognizer,StabilityGate,apply_fields,applicable_fields,mark_uncertain
from garrison.tracking import ShopWatch,shop_observations

HERE=Path(__file__).parent;ROOT=HERE/'build/level-transition'
db=Database();recognizer=Recognizer(db);checks=[];base=[];timings=[]
fixtures=json.loads((ROOT/'fixtures.json').read_text('utf8'))
def check(name,ok):
    checks.append({'test':name,'passed':bool(ok)})
    assert ok,name
def read(frame):return recognizer.recognize(frame,{'battle_enabled':False})
def verify(name,result,expected,count):
    fields={f['key']:f for f in result['fields']}
    check(name+' layout',result['layout_valid'] and result['shop_valid'])
    check(name+' card count',len(result['shop_slots'])==count)
    for key,value in expected.items():
        if key.startswith('shop:'):value=db.by_name[value]['operator_id']
        f=fields.get(key,{})
        check(name+' '+key+' '+json.dumps(f,ensure_ascii=False),f.get('value')==value and f.get('confidence',0)>=.92)
    check(name+' snapshot complete',fields['shop_snapshot']['value'] is not None)
    if expected['level']==6:check(name+' maximum has no upgrade price','upgrade_cost' not in fields)
    timings.append({'case':name,'elapsed_ms':result['elapsed_ms']})
for fixture in fixtures:
    path=HERE/fixture['file'];frame=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
    for width in (frame.shape[1],1280,1920):
        if width==frame.shape[1] and any(t['case']==fixture['name']+' native' for t in timings):continue
        sample=frame if width==frame.shape[1] else cv2.resize(frame,(width,round(width*frame.shape[0]/frame.shape[1])),interpolation=cv2.INTER_AREA)
        name=fixture['name']+(' native' if width==frame.shape[1] else f' resized {width}')
        result=read(sample);verify(name,result,fixture['expected'],fixture['count'])
        if width==frame.shape[1]:
            base.append((frame,result,fixture));(ROOT/(fixture['name']+'-fixed.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps({'case':name,'passed':True,'ms':result['elapsed_ms']}),flush=True)

# Feed real frames in upgrade order through the same temporal gates. These
# repetitions are a deterministic replay, not separate live camera samples.
gate=StabilityGate(2);watch=ShopWatch();state=new_state();clock=0
for frame,result,fixture in base:
    clock+=1;first=gate.accept(result['fields'],.92)
    check(fixture['name']+' changed level awaits confirmation',not any(f['key']=='level' for f in first))
    before=copy.deepcopy(watch.stable);now=watch.accept(db,result,frame=frame,now=clock)
    observed=shop_observations(db,result)
    check(fixture['name']+' no old card geometry retained',all(any(i['slot']==j['slot'] and i.get('op_id',i.get('name'))==j.get('op_id',j.get('name')) and max(abs(a-b) for a,b in zip(i['rect'],j['rect']))<.006 for j in observed) for i in now))
    second=gate.accept(result['fields'],.92);apply_fields(state,applicable_fields(result,second))
    check(fixture['name']+' committed new level',state['level']==fixture['expected']['level'])
    current=watch.accept(db,result,frame=frame,now=clock+.3)
    check(fixture['name']+' markers follow all new slots',len(current)==fixture['count'])
    expected_shop=[(int(k.split(':')[1]),db.by_name[v]['operator_id']) for k,v in fixture['expected'].items() if k.startswith('shop:')]
    check(fixture['name']+' atomic shop replacement',sorted((i['slot'],i['op_id']) for i in state['shop'])==sorted(expected_shop))

frame,result,fixture=base[0];h,w=frame.shape[:2]
for part in ('label','digit','badge','shop'):
    sample=frame.copy()
    if part=='label':box=next(a['rect'] for a in result['words'] if a['text']=='LEVEL')
    elif part=='digit':box=next(a['rect'] for a in result['regions'] if a['key']=='level')
    elif part=='badge':
        cx=next(a['x'] for a in result['words'] if a['text']=='LEVEL');box=[cx-.032,.73,.064,.065]
    else:box=[0,.59,1,.41]
    x,y,bw,bh=box;sample[max(0,int(y*h)-2):min(h,int((y+bh)*h)+2),max(0,int(x*w)-2):min(w,int((x+bw)*w)+2)]=150 if part!='shop' else 0
    failed=read(sample);fields={f['key']:f for f in failed['fields']}
    key='upgrade_cost' if part=='badge' else 'level'
    check('occluded '+part+' abstains',fields.get(key,{}).get('value') is None)
    if part=='shop':check('hidden shop invalid',not failed['layout_valid'])
    if part in ('label','digit'):
        state['level']=1;mark_uncertain(state,failed['fields'],.92)
        check('occluded '+part+' marks prior level uncertain',state['field_meta']['level'].get('uncertain'))
dimmed=[]
for frame,result,fixture in base[:3]:
    dim=cv2.convertScaleAbs(frame,alpha=.72)
    result=read(dim);fields={f['key']:f for f in result['fields']};unknown=[]
    for key,value in fixture['expected'].items():
        if key.startswith('shop:'):value=db.by_name[value]['operator_id']
        observed=fields.get(key,{})
        if observed.get('value') is None or observed.get('confidence',0)<.92:unknown.append(key);continue
        check(fixture['name']+' dimmed '+key+' never fabricates',observed['value']==value)
    if not result.get('shop_valid'):
        snap=fields.get('shop_snapshot',{});accepted=json.loads(snap['value']) if snap.get('value') else []
        check(fixture['name']+' dimmed unresolved cards never committed',all(f['key'] not in unknown and int(f['key'].split(':')[1]) not in snap.get('pending_slots',[]) for f in accepted))
    dimmed.append({'case':fixture['name'],'abstained_fields':unknown})
report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'fixtures':fixtures,'timings':timings,'dimmed_abstentions':dimmed,
        'scope':'New user-authorized PC captures plus historical level 5/6; resizes, dimming, occlusions and temporal repetitions are synthetic replay, not live input latency.'}
(ROOT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({'passed':report['passed'],'checks':len(checks),'native_frames':len(base)},ensure_ascii=False))
