"""Real-frame sprite replay; reports omissions instead of treating them as empty."""
from pathlib import Path
import json
import time
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from garrison.battle import BattleRecognizer
from garrison import __version__
from garrison.core import Database
from garrison.recognition import Recognizer

ROOT=Path(__file__).resolve().parent/'build';OUT=ROOT/'battle-recognition';OUT.mkdir(exist_ok=True)
detector=BattleRecognizer();reports=[]
for filename in ('recognition-real/pc-level6.png','battle-recognition/pc-round14.png','battle-recognition/pc-round14-b.png'):
    frame=cv2.imdecode(np.fromfile(ROOT/filename,np.uint8),cv2.IMREAD_COLOR)
    result=detector.detect(frame,{'field':[.12,.20,.56,.43],'bench':[.10,.63,.80,.115]})
    print(Path(filename).stem,result['elapsed_ms'],[(d['name'],d['zone'],d['matches'],d['correlation'],d['reliable']) for d in result['detections']],flush=True)
    report={'fixture':filename,**result};reports.append(report)
    image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
    for d in result['detections']:
        x,y,w,h=d['rect'];x*=image.width;w*=image.width;y*=image.height;h*=image.height
        color='#14dfbb' if d['reliable'] else '#ffbf55';draw.rectangle((x,y,x+w,y+h),outline=color,width=3)
        text=d['name']+(' / 待确认' if not d['reliable'] else '');box=draw.textbbox((x,y-25),text,font=font)
        draw.rectangle(box,fill='#102121');draw.text((x,y-25),text,font=font,fill=color)
    image.save(OUT/(Path(filename).stem+'-annotated.png'))
# Position-labelled current lineup, checked visually against the model previews.
# This covers one lineup, not population accuracy. Mechanic remains a known miss.
truth=[('乌啾','field',.400,.245),('摆渡人','field',.454,.241),('冻河','field',.396,.318),
       ('机械师','field',.452,.324),('塔露拉','field',.393,.398),('折桠','field',.446,.399),
       ('烈夏','field',.387,.489),('维伊','field',.440,.480),('维伊','bench',.757,.648)]
def expected(d):
    x,y,w,h=d['rect'];cx=x+w/2;cy=y+h*.7
    return any(d['name']==name and d['zone']==zone and abs(cx-tx)<.035 and abs(cy-ty)<.05 for name,zone,tx,ty in truth)
checks=[]
for rep in reports[1:]:
    good=[d for d in rep['detections'] if d['reliable']]
    checks.append({'test':rep['fixture']+' confident identities and positions','passed':len(good)>=7 and all(expected(d) for d in good),'matched':len(good),'visible_operators':9})
for width in (1280,1920):
    resized=cv2.resize(frame,(width,round(width*frame.shape[0]/frame.shape[1])),interpolation=cv2.INTER_AREA)
    result=detector.detect(resized,{'field':[.12,.20,.56,.43],'bench':[.10,.63,.80,.115]})
    good=[d for d in result['detections'] if d['reliable']]
    checks.append({'test':f'same frame resized to {width}','passed':len(good)>=5 and all(expected(d) for d in good),'matched':len(good),'elapsed_ms':result['elapsed_ms']})
negative=frame.copy();hh,ww=negative.shape[:2]
negative[int(.17*hh):int(.62*hh),int(.32*ww):int(.49*ww)]=0
negative[int(.54*hh):int(.73*hh),int(.70*ww):int(.80*ww)]=0
result=detector.detect(negative,{'field':[.12,.20,.56,.43],'bench':[.10,.63,.80,.115]})
checks.append({'test':'operators occluded; summons, boss, terrain and shop retained','passed':not any(d['reliable'] for d in result['detections'])})
recognizer=Recognizer(Database());recognizer.battle=detector
result=recognizer.recognize(frame);values={f['key']:f['value'] for f in result['fields']}
checks.append({'test':'full OCR + sprites pipeline round14','passed':all(values.get(k)==v for k,v in [('round',14),('level',6),('gold',2),('phase','整备')]) and result['battlefield']['active'],'elapsed_ms':result['elapsed_ms']})
snapshot=next(f for f in result['fields'] if f['key']=='shop_snapshot')
accepted=json.loads(snapshot['value'])
checks.append({'test':'silver prices retained; verified cards publish while unmapped Stormeye abstains','passed':len(result['shop_slots'])==6 and all(values.get(f'cost:{i}')==v for i,v in enumerate([3,2,3,3,4,3])) and snapshot['partial'] and snapshot['pending_slots']==[3,5] and len(accepted)==8 and not any(f['key'].endswith((':3',':5')) for f in accepted) and values['offer:3'] is None and values['offer:5'] is None})
(OUT/'pc-round14-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
report={'version':__version__,'frames':reports,'checks':checks,'passed':all(c['passed'] for c in checks),
        'limitations':['Three screenshots from two preparation states; two are different idle instants of the same round14 lineup.','Default skins, Closure layout only. Results are partial, not a population accuracy measurement.','Elite status, equipment and missing units require review; mechanic is missed in the round14 fixture.','Stormeye occurs as a prototype of several records, not a unique operator in the 143-operator database; those shop entries remain unknown.','Labels checked visually against model previews, not extracted through game memory or in-game name panel.']}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(checks,ensure_ascii=False),flush=True)
assert report['passed']
