"""Native UI integration for sprite updates, with a separate profile."""
import copy,json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'build/battle-recognition'
os.environ['GARRISON_DATA_DIR']=str(ROOT/'build/battle-ui-profile')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import cv2,numpy as np
from garrison.ui import MainWindow
from garrison.core import fingerprint,new_state
from garrison import __version__
app=QApplication([])
for f in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.store.state=new_state();w.show();app.processEvents()
checks=[]
def check(name,value):
    checks.append({'test':name,'passed':bool(value)});assert value,name
try:
    frame=cv2.imdecode(np.fromfile(OUT/'pc-round14-b.png',np.uint8),cv2.IMREAD_COLOR)
    result=json.loads((OUT/'pc-round14-result.json').read_text('utf8'))
    w.set_frame(frame);w.navigate(7,False);w.live=True;w.settings['auto_apply']=True;w.gate.reset()
    w.receive_recognition(result,fingerprint(w.store.state));check('first frame waits',not w.store.state['units'])
    w.receive_recognition(result,fingerprint(w.store.state));w.live=False
    count=sum(bool(f['key'].startswith('sprite:') and f['value'] and f['confidence']>=.92) for f in result['fields'])
    check('stable sprites applied',len(w.store.state['units'])==count>=7)
    check('same name field and bench distinct',sum(w.db.ops[u['op_id']]['name']=='维伊' for u in w.store.state['units'])==2)
    check('partial roster blocks auto coach',w.store.state['field_meta']['battle_roster']['uncertain'])
    check('name boxes in preview',any(r.get('label','').startswith('维伊') for r in w.canvas.detected_regions))
    app.processEvents();w.grab().save(str(OUT/'assistant-battle-preview.png'))
    w.navigate(1,False);w.select_unit(w.store.state['units'][0]['uid']);w.confirm_unit_elite()
    check('explicit initial state confirmation',not w.store.state['units'][0]['sprite_elite_unknown'])
    w.confirm_battle_roster();check('roster confirmation recorded',not w.store.state['field_meta']['battle_roster']['uncertain'])
    calls=[];original=w.analyze;w.analyze=lambda **kwargs:calls.append(kwargs)
    w.settings.update(ai_enabled=True,ai_auto=True);w.auto_keys.clear();w.ai_busy=False
    w.last_recognition={'fields':[{'key':k} for k in ('phase','round','gold','level','shop:1','sprite:rejected')]}
    # Supply a separately confirmed shop for this gate test; the real Stormeye
    # fixture correctly refuses its complete shop snapshot.
    for key in ('phase','round','gold','level','shop:1'):
        w.store.state['field_meta'][key]={'time':time.time(),'source':'自动识别','confidence':.99}
    w.maybe_auto_analyze();check('reviewed roster allows auto coach despite rejected extra candidate',len(calls)==1)
    w.settings['ai_enabled']=False;w.analyze=original;w.last_recognition=result
    w.store.state['round']=15;w.refresh_all();check('round change invalidates roster confirmation',w.store.state['field_meta']['battle_roster']['uncertain'])
    app.processEvents();w.grab().save(str(OUT/'assistant-battle-roster.png'))
    missing=copy.deepcopy(result);missing['fields']=[f for f in missing['fields'] if not f['key'].startswith('sprite:')]
    missing['battlefield']={'active':False,'detections':[]};w.live=True
    w.receive_recognition(missing,fingerprint(w.store.state));w.live=False
    check('occlusion retains records but excludes them',len(w.store.state['units'])==count and all(u['sprite_missing'] for u in w.store.state['units']))
finally:
    (OUT/'ui-report.json').write_text(json.dumps({'version':__version__,'checks':checks,'passed':all(c['passed'] for c in checks)},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps(checks,ensure_ascii=False))
