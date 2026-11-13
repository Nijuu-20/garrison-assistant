"""Replay a locally captured PC frame. Derived sizes are NOT independent games."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from garrison.core import Database,new_state
from garrison.recognition import Recognizer,StabilityGate,apply_fields,applicable_fields

root=Path(__file__).resolve().parent/'build'/'recognition-real'
db=Database();r=Recognizer(db)
fixtures=[('pc-round3',{'round':3,'gold':6,'level':1,'phase':'整备','upgrade_cost':3,'refresh_cost':1,
          'offer:0':'维式重锤','shop:1':db.by_name['幽灵鲨']['operator_id'],
          'shop:2':db.by_name['艾丝黛尔']['operator_id'],'shop:3':db.by_name['陨星']['operator_id'],
          'cost:0':1,'cost:1':2,'cost:2':2,'cost:3':2}),
          ('pc-level5',{'round':9,'gold':18,'level':5,'phase':'整备','upgrade_cost':12,'refresh_cost':1,
          'offer:0':'炎国短刀',**{f'shop:{i}':db.by_name[n]['operator_id'] for i,n in enumerate(['深靛','夜莺','霍尔海雅','塞雷娅','忍冬'],1)},
          **{f'cost:{i}':c for i,c in enumerate([2,2,3,3,4,3])}}),
          ('pc-level6',{'round':9,'gold':6,'level':6,'phase':'整备','refresh_cost':1,
          'offer:0':'炎国短刀',**{f'shop:{i}':db.by_name[n]['operator_id'] for i,n in enumerate(['深靛','夜莺','霍尔海雅','塞雷娅','忍冬'],1)},
          **{f'cost:{i}':c for i,c in enumerate([2,2,3,3,4,3])}})]
reports=[]
for fixture,expected in fixtures:
  frame=cv2.cvtColor(np.array(Image.open(root/(fixture+'.png')).convert('RGB')),cv2.COLOR_RGB2BGR)
  for width in (2048,1920,1280):
    im=cv2.resize(frame,(width,round(width*frame.shape[0]/frame.shape[1])),interpolation=cv2.INTER_AREA)
    first=r.recognize(im);result=r.recognize(im);fields={f['key']:f for f in result['fields']}
    checks=[{'key':k,'expected':v,'actual':fields.get(k,{}).get('value'),
             'confidence':fields.get(k,{}).get('confidence',0),'passed':fields.get(k,{}).get('value')==v and fields[k]['confidence']>=.92} for k,v in expected.items()]
    gate=StabilityGate(2);assert not gate.accept(first['fields'],.92)
    stable=gate.accept(result['fields'],.92);s=new_state();apply_fields(s,applicable_fields(result,stable))
    count=sum(k.startswith('shop:') for k in expected)
    report={'fixture':fixture,'width':width,'source':'real PC frame' if width==2048 else 'resize of the same frame',
            'first_ms':first['elapsed_ms'],'warm_ms':result['elapsed_ms'],'checks':checks,'shop_applied':len(s['shop'])==count and len(s['recognized_offers'])==1}
    reports.append(report)
    (root/f'{fixture}-result-{width}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    if fixture=='pc-round3':(root/f'result-{width}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'}|{'passed':sum(c['passed'] for c in checks),'total':len(checks),'failures':[c for c in checks if not c['passed']]},ensure_ascii=False),flush=True)
hidden=frame.copy();hidden[int(len(hidden)*.59):]=0
refusal=r.recognize(hidden)
negative={'source':'same frame with shop occluded','passed':not refusal['layout_valid'] and all(f['value'] is None for f in refusal['fields'])}
report={'independent_game_frames':len(fixtures),'theme':'可露希尔','tests':reports,'negative':negative,
        'limitations':['Only the listed real frames and resized copies were tested; other themes and combat animations remain unverified.','Battlefield sprites have a separate partial-recognition report; equipment icons remain manual.']}
(root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(c['passed'] for rep in reports for c in rep['checks']) and all(rep['shop_applied'] for rep in reports)
assert negative['passed']
