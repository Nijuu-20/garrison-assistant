"""Saved-frame and offscreen temporal replay, never captures the live desktop."""
import copy,json,os,tempfile,time
from pathlib import Path
import cv2,numpy as np
HERE=Path(__file__).parent;OUT=HERE/'build/opening-stability';OUT.mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-solo-stability-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from garrison.ui import MainWindow
from garrison.opening import recompute,snapshot_key
from garrison.core import fingerprint
from garrison import __version__
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.settings['auto_apply']=False;w.live=True
w.show_overlay();app.processEvents();checks=[];frames=[]
def check(name,value):checks.append({'test':name,'passed':bool(value)});assert value,name
def deliver(result):
    w.receive_recognition(result,fingerprint(w.store.state));app.processEvents()
def blank():return {'fields':[],'mode':'auto','regions':[],'notes':[],'time':time.time(),'elapsed_ms':0,'shop_slots':[]}
try:
    frame=cv2.imdecode(np.fromfile(HERE/'build/opening-recognition/solo.png',np.uint8),cv2.IMREAD_COLOR)
    base=w.recognizer.opening.recognize(frame);check('base solo fully recognized',base['complete'] and base['opening']['mode']=='solo')
    deliver(base);deliver(base);old=copy.deepcopy(w.store.state['opening']);revision=w.store.state['revision'];bans=w.overlay.opening_bans.text()
    check('baseline auto confirmed',old is not None and not w.overlay.opening_confirm.isEnabled())
    # Remove one actual icon, then lose the whole frame: display must stay put.
    hidden=frame.copy();hidden[1270:1420,950:1080]=20
    partial=w.recognizer.opening.recognize(hidden);check('occlusion produces incomplete observation',partial and not partial['complete'])
    deliver(partial);deliver(blank())
    check('dropouts preserve displayed bans and all 26 rows',w.overlay.opening_bans.text()==bans and w.opening_table.rowCount()==26 and not w.overlay.opening_box.isHidden())
    check('locked results cannot be redundantly confirmed',not w.overlay.opening_confirm.isEnabled() and '已锁定' in w.overlay.opening_status.text())
    check('dropouts never write new bans',w.store.state['opening']==old and w.store.state['revision']==revision)
    w.overlay.grab().save(str(OUT/'held-briefing.png'))
    deliver(blank());check('sustained visibility loss preserves explicitly locked briefing',w.overlay.activity.text()=='开局攻略' and '已锁定' in w.overlay.opening_status.text() and w.overlay.opening_bans.text()==bans)
    deliver(base);deliver(base)
    check('recovery does not reconfirm unchanged pool',w.store.state['revision']==revision and '已锁定' in w.overlay.opening_status.text())
    # Pixel perturbations are synthetic derivatives, not independent game samples.
    for name,img in [('dimmer',cv2.convertScaleAbs(frame,alpha=.85)),('brighter',cv2.convertScaleAbs(frame,alpha=1.10)),
                     ('shift',cv2.warpAffine(frame,np.float32([[1,0,2],[0,1,-2]]),(frame.shape[1],frame.shape[0]))),
                     ('resize',cv2.resize(frame,(1920,1080),interpolation=cv2.INTER_AREA))]:
        result=w.recognizer.opening.recognize(img);deliver(result or blank())
        frames.append({'sample':name,'complete':bool(result and result['complete']),'display_key_unchanged':snapshot_key(w.visible_opening())==snapshot_key(old)})
        check(name+' recognizes all icons without relying on held preview',bool(result and result['complete']) and snapshot_key(result['opening'])==snapshot_key(old))
        check(name+' does not replace known configuration',w.store.state['opening']==old and frames[-1]['display_key_unchanged'])
    deliver(base);deliver(base)
    changed=copy.deepcopy(base);opening=changed['opening'];opening['selected']='right'
    for e in opening['core']:e['state']='lit' if e['name'] in opening['groups']['right'] else 'grey'
    recompute(w.db,opening);changed['fields'][0]['value']=json.dumps(opening)
    deliver(changed)
    check('single changed frame retains lock and labels pending new choice',w.overlay.opening_bans.text()==bans and not w.store.state['field_meta']['opening_snapshot'].get('uncertain') and '新选组核对中' in w.overlay.opening_status.text())
    deliver(changed)
    check('real repeated change replaces pool once',w.store.state['opening']['selected']=='right' and w.store.state['revision']==revision+1 and w.overlay.opening_bans.text()!=bans)
    revision=w.store.state['revision']
    reordered=copy.deepcopy(changed)
    for k in ('core','additional'):reordered['opening'][k].reverse()
    for names in reordered['opening']['groups'].values():names.reverse()
    reordered['fields'][0]['value']=json.dumps(reordered['opening'])
    for _ in range(3):deliver(reordered)
    check('detection ordering does not create tactical changes',w.store.state['revision']==revision)
    # A series of intermediate non-HUD screens must not silently discard bans.
    for _ in range(4):deliver(blank())
    hud=blank();hud['fields']=[{'key':k,'value':v,'confidence':.99,'label':str(v),'method':'saved test','raw':str(v)} for k,v in [('phase','整备'),('round',1),('level',1),('gold',6)]]
    deliver(hud);check('first HUD observation keeps briefing',w.visible_opening() is not None)
    deliver(hud);check('stable HUD leaves briefing without losing confirmed bans',w.visible_opening() is None and w.overlay.opening_box.isHidden() and w.store.state['opening']['selected']=='right' and not w.store.state['field_meta']['opening_snapshot'].get('uncertain'))
    w.new_session();check('new session forgets all held previews',w.solo_briefing.opening is None and w.visible_opening() is None)
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'synthetic_frames':frames,
        'limits':'User-provided historical solo screenshot plus synthetic occlusion/brightness/translation, scripted result sequences and offscreen UI. No new live solo/co-op test.'},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'checks':len(checks),'frames':frames,'passed':all(c['passed'] for c in checks)},ensure_ascii=False))
