"""Offline replay of supplied opening screens; no desktop input or network."""
import copy,json,time
from pathlib import Path
import cv2,numpy as np
from garrison import __version__
from garrison.core import Database
from garrison.recognition import Recognizer
from garrison.opening import availability,recommendation
HERE=Path(__file__).parent;OUT=HERE/'build/opening-recognition';db=Database();r=Recognizer(db)
expected={
 'solo':{'mode':'solo','selected':'left','core':{'乌萨斯','叙拉古','炎','阿戈尔','谢拉格'},'additional':{'迅捷','灵巧','奇迹','聚合','奥术'}},
 'coop':{'mode':'coop','selected':None,'core':{'炎','萨尔贡','维多利亚','卡西米尔','乌萨斯'},'additional':{'迅捷','坚守','突袭','聚合','奥术'}}}
checks=[];timings=[]
def check(name,value):
    checks.append({'test':name,'passed':bool(value)})
    if not value:print('FAILED',name)
for name,expect in expected.items():
    frame=cv2.imdecode(np.fromfile(OUT/(name+'.png'),np.uint8),cv2.IMREAD_COLOR)
    for width in (2560,1920,1280):
        sample=cv2.resize(frame,(width,width*9//16),interpolation=cv2.INTER_AREA)
        result=r.recognize(sample);op=result.get('opening') or {};timings.append(result['elapsed_ms'])
        check(f'{name}/{width} mode',op.get('mode')==expect['mode'])
        check(f'{name}/{width} selection',op.get('selected')==expect['selected'])
        for kind in ('core','additional'):
            check(f'{name}/{width} {kind} exact bans',{e['name'] for e in op.get(kind,[]) if e['state']=='grey'}==expect[kind])
        check(f'{name}/{width} complete',result['complete'])
        check(f'{name}/{width} no OCR',r.engine is None and result.get('words')==[])
        check(f'{name}/{width} choice only solo',(recommendation(db,op) is not None)==(name=='solo'))
        if width==2560:(OUT/(name+'-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    # Cover every label and title. Icon recognition must be unchanged.
    masked=frame.copy();words=json.loads((OUT/(name+'-words.json')).read_text('utf8'))
    for word in words:
        if word['text'] not in {c['name'] for c in db.covenants}|{'核心盟约','附加盟约','本局禁用干员'} and word['y']>.15:continue
        x,y,w,h=word['rect'];cv2.rectangle(masked,(int(x*2560),int(y*1440)),(int((x+w)*2560),int((y+h)*1440)),(35,35,35),-1)
    masked_result=r.opening.recognize(masked)
    check(name+' text masked unchanged',masked_result is not None and masked_result['opening']==json.loads((OUT/(name+'-result.json')).read_text('utf8'))['opening'])
    # A hidden icon must not be substituted by the other five or by old state.
    hidden=frame.copy();cv2.rectangle(hidden,(960,1000),(1080,1150),(20,20,20),-1) if name=='coop' else cv2.rectangle(hidden,(950,1270),(1080,1420),(20,20,20),-1)
    result=r.opening.recognize(hidden)
    check(name+' hidden icon blocks apply',result is not None and result['fields'][0]['value'] is None and not result['complete'])
    (OUT/(name+'-masked-result.json')).write_text(json.dumps(masked_result,ensure_ascii=False,indent=2),'utf8')
for name in ('pc-round3','pc-level5','pc-level6'):
    frame=cv2.imdecode(np.fromfile(HERE/'build/recognition-real'/(name+'.png'),np.uint8),cv2.IMREAD_COLOR)
    check(name+' is not opening',r.opening.recognize(frame) is None)
frame=cv2.imdecode(np.fromfile(OUT/'solo.png',np.uint8),cv2.IMREAD_COLOR)
swapped=frame.copy();swapped[385:853,168:930]=frame[385:853,948:1710];swapped[385:853,948:1710]=frame[385:853,168:930]
result=r.opening.recognize(swapped)
check('right selection follows moved underline',result is not None and result['opening']['selected']=='right' and result['complete'])
check('selected group identities follow icons',result is not None and set(result['opening']['groups']['right'])=={'卡西米尔','莱塔尼亚','维多利亚','萨尔贡','伊比利亚'})
hidden=frame.copy();hidden[820:855,155:1720]=20
result=r.opening.recognize(hidden)
check('missing underline abstains',result is not None and result['opening']['selected'] is None and not result['complete'])
report={'version':__version__,'checks':checks,'passed':all(c['passed'] for c in checks),'timings_ms':timings,
        'method':'PRTS original alpha icon templates from local database; screenshots supply only layout anchors and test scenes; all text masked negative control; no OCR/portrait path.',
        'limits':'Two supplied reference frames, resized derivatives and synthetic occlusion; not independent live-game accuracy measurement.'}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({'passed':report['passed'],'checks':len(checks),'timings_ms':timings},ensure_ascii=False))
raise SystemExit(0 if report['passed'] else 1)
