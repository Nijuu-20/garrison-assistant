"""Synthetic OCR benchmark. This deliberately is NOT a live-game accuracy test."""
import sys
import json
import time
from pathlib import Path
import numpy as np
import cv2
from PIL import Image,ImageDraw,ImageFont
from garrison.core import Database,new_state,recommend
from garrison.recognition import Recognizer,StabilityGate,apply_fields

root=Path(__file__).resolve().parent;out=root/'build'/'recognition-validation';out.mkdir(parents=True,exist_ok=True)
im=Image.new('RGB',(1280,720),(26,32,35));draw=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',38)
records=[('gold','资金 18',(40,30,290,100)),('round','回合 3',(390,30,620,100)),('level','等级 2',(740,30,1000,100)),
         ('phase','整备期',(40,160,300,230)),('shop:0','折桠',(40,330,290,430)),('shop:1','角峰',(390,330,640,430)),('shop:2','艾丝黛尔',(740,330,1100,430)),
         ('upgrade_cost','升级 6',(40,530,290,620)),('cost:0','2',(390,530,500,620))]
regions=[]
for key,text,(x,y,x2,y2) in records:
    draw.text((x,y),text,font=font,fill=(244,248,224));regions.append({'key':key,'rect':[x/1280,y/720,(x2-x)/1280,(y2-y)/720]})
im.save(out/'synthetic-layout.png');frame=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2BGR)
db=Database();engine=Recognizer(db);profile={'regions':regions,'aspect':1280/720};start=time.perf_counter();first=engine.recognize(frame,profile);cold=round((time.perf_counter()-start)*1000)
second=engine.recognize(frame,profile);expected={'gold':18,'round':3,'level':2,'phase':'整备','shop:0':db.by_name['折桠']['operator_id'],'shop:1':db.by_name['角峰']['operator_id'],'shop:2':db.by_name['艾丝黛尔']['operator_id'],'upgrade_cost':6,'cost:0':2}
checks=[{'field':f['key'],'expected':expected[f['key']],'actual':f['value'],'confidence':f['confidence'],'pass':expected[f['key']]==f['value']} for f in second['fields']]
gate=StabilityGate(2);assert not gate.accept(first['fields'],.92);accepted=gate.accept(second['fields'],.92);state=new_state();apply_fields(state,accepted)
times=[]
for _ in range(30):
    t=time.perf_counter();recommend(db,state,True);times.append((time.perf_counter()-t)*1000)
report={'fixture':'synthetic Chinese text, not gameplay','cold_total_ms':cold,'warm_ocr_ms':second['elapsed_ms'],
        'local_recommendation_mean_ms':round(sum(times)/len(times),2),'accepted_fields':len(accepted),'checks':checks,'live_game_verified':False}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
assert all(c['pass'] for c in checks)
