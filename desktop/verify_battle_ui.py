"""Native UI integration for sprite updates, with a separate profile."""
import copy,json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'build/battle-recognition'
os.environ['GARRISON_DATA_DIR']=str(ROOT/'build/battle-ui-profile')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import cv2,numpy as np
from garrison.ui import MainWindow
from garrison.core import fingerprint,new_state,covenant_status
from garrison.coach import make_context
from garrison.advice import target_candidates,overlay_advice
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
    w.set_frame(frame);w.navigate('recognition',False);w.live=True;w.settings['auto_apply']=True;w.gate.reset()
    w.receive_recognition(result,fingerprint(w.store.state));check('first frame waits',not w.store.state['units'])
    w.receive_recognition(result,fingerprint(w.store.state));w.live=False
    count=sum(bool(f['key'].startswith('sprite:') and f['value'] and f['confidence']>=.92) for f in result['fields'])
    check('stable sprites applied',len(w.store.state['units'])==count>=7)
    check('same name field and bench distinct',sum(w.db.ops[u['op_id']]['name']=='维伊' for u in w.store.state['units'])==2)
    check('partial roster blocks auto coach',w.store.state['field_meta']['battle_roster']['uncertain'])
    check('name boxes in preview',any(r.get('label','').startswith('维伊') for r in w.canvas.detected_regions))
    app.processEvents();w.grab().save(str(OUT/'assistant-battle-preview.png'))
    w.navigate('roster',False);w.select_unit(w.store.state['units'][0]['uid']);w.confirm_unit_elite()
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
    before_units=copy.deepcopy(w.store.state['units'])
    before_counts={c['name']:c['effective'] for c in covenant_status(w.db,w.store.state)}
    before_targets=[(c['name'],c['score']) for c in target_candidates(w.db,w.store.state,10)]
    missing=copy.deepcopy(result);missing['fields']=[f for f in missing['fields'] if not f['key'].startswith('sprite:')]
    missing['battlefield']={'active':False,'detections':[]};w.live=True
    for _ in range(3):w.receive_recognition(missing,fingerprint(w.store.state))
    w.live=False;w.refresh_all()
    check('occlusion retains records as pending',len(w.store.state['units'])==count and all(u['sprite_missing'] for u in w.store.state['units']))
    check('occlusion preserves positions and equipment',all(all(a.get(k)==b.get(k) for k in ('uid','op_id','zone','elite','equipment')) for a,b in zip(before_units,w.store.state['units'])))
    check('occlusion retains covenant progress',before_counts=={c['name']:c['effective'] for c in covenant_status(w.db,w.store.state)})
    check('occlusion retains target rankings',before_targets==[(c['name'],c['score']) for c in target_candidates(w.db,w.store.state,10)])
    check('board shows pending and retained contribution',all('待核对' in item.text() and '不计入建议' not in item.text() for group in (w.field_list,w.bench_list) for item in (group.item(i) for i in range(group.count()))))
    check('main roster count retained',f'战场 {sum(u["zone"]=="field" for u in before_units)} 人' in w.home_status.text() and '沿用上次阵容' in w.home_status.text())
    check('covenant strip marks provisional progress',any(c['effective'] and c['needs_review'] for c in w.home_links.entries))
    check('overlay explains last confirmed roster','最后确认' in w.overlay.content.text() and '待核对' in w.overlay.content.text())
    context=make_context(w.db,w.store.state)
    check('AI includes all pending instances',len(context['state']['units'])==count and all(u['observation_status']=='needs_review' for u in context['state']['units']))
    check('AI includes pending covenant evidence',any(c['effective'] and c['needs_review'] for c in context['covenants']))
    check('pending roster still requires review',w.store.state['field_meta']['battle_roster']['uncertain'])
    w.navigate(0,False);app.processEvents();w.grab().save(str(OUT/'assistant-roster-pending.png'))
    w.overlay.resize(490,790);w.overlay.update_content();app.processEvents();w.overlay.grab().save(str(OUT/'overlay-roster-pending.png'))
    w.live=True
    w.receive_recognition(result,fingerprint(w.store.state))
    check('first returning frame still waits',all(u['sprite_missing'] for u in w.store.state['units']))
    w.receive_recognition(result,fingerprint(w.store.state));w.live=False;w.refresh_all()
    check('stable return clears pending without duplicates',len(w.store.state['units'])==count and not any(u['sprite_missing'] for u in w.store.state['units']))
    check('stable return preserves instance IDs',[u['uid'] for u in w.store.state['units']]==[u['uid'] for u in before_units])
    check('stable return removes pending UI','沿用上次阵容' not in w.home_status.text() and not any(c['needs_review'] for c in w.home_links.entries))
    check('stable return retains covenant progress',before_counts=={c['name']:c['effective'] for c in covenant_status(w.db,w.store.state)})
    w.new_session();check('new session clears old team',not w.store.state['units'] and not make_context(w.db,w.store.state)['state']['units'])
finally:
    (OUT/'ui-report.json').write_text(json.dumps({'version':__version__,'checks':checks,'passed':all(c['passed'] for c in checks)},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps(checks,ensure_ascii=False))
