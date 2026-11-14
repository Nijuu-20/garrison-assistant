"""Temporal regression with saved shop frames and isolated offscreen controls."""
import copy,json,os,tempfile,time
from pathlib import Path
import cv2,numpy as np
HERE=Path(__file__).parent;OUT=HERE/'build/stability-locks';OUT.mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-stability-locks-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
import garrison.ui as ui
from garrison.core import new_state,fingerprint,unit,validate_state
from garrison.opening import recompute,snapshot_key
from garrison.strategy import route_matches,local_plan
from garrison.storage import Storage
from garrison.hud import locate,price_badges
from garrison import __version__
app=QApplication([])
for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
w=ui.MainWindow();w.timer.stop();w.hotkeys.clear();w.settings.update(reduce_motion=True,auto_apply=False);w.show();w.show_overlay();checks=[]
def check(name,ok):
    checks.append({'test':name,'passed':bool(ok)});assert ok,name
def events():
    for _ in range(4):app.processEvents()
def deliver(result):w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state));events()
def blank():return {'fields':[],'mode':'auto','regions':[],'notes':[],'time':time.time(),'elapsed_ms':0,'shop_slots':[]}
try:
    game=cv2.imdecode(np.fromfile(HERE/'build/recognition-real/pc-level6.png',np.uint8),cv2.IMREAD_COLOR)
    result=json.loads((HERE/'build/recognition-real/pc-level6-result-2048.json').read_text('utf8'))
    layout=locate(result['words'],price_badges(game),w.db,game.shape[1]/game.shape[0]);result.update(shop_slots=layout['slots'],regions=layout['regions'])
    w.store.state=new_state();w.tracked=[{'kind':'operator','op_id':w.db.by_name[n]['operator_id'],'name':n} for n in ('夜莺','霍尔海雅')]
    w.tracked.append({'kind':'equipment','name':'炎国短刀'})
    w.set_frame(game);deliver(result);deliver(result);check('three saved shop matches',len(w.canvas.tracking_regions)==3)
    target={'hwnd':12345,'pid':6789};source={**target,'size':[game.shape[1],game.shape[0]],'captured':time.monotonic()}
    w.window_combo.blockSignals(True);w.window_combo.addItem('离线测试窗口',target);w.window_combo.setCurrentIndex(w.window_combo.count()-1);w.window_combo.blockSignals(False)
    ui.client_geometry=lambda *_:(0,0,game.shape[1],game.shape[0]);latest=[game]
    ui.peek_capture=lambda *_:latest[0];ui.place_highlight=lambda *_:None;ui.set_capture_excluded=lambda *_:None
    w.live=True;w.watch_source=source;w.update_shop_highlight();events()
    check('stable overlay visible',w.shop_highlight.isVisible())
    source['captured']=time.monotonic()-20;w.update_shop_highlight()
    check('slow recognition cannot expire a visually verified current shop',w.shop_highlight.isVisible() and len(w.canvas.tracking_regions)==3)
    w.set_frame(game,preserve_tracking=True);check('new capture never hides established surface',w.shop_highlight.isVisible() and len(w.canvas.tracking_regions)==3)
    result['capture_source']=source;before=fingerprint(w.store.state);w.store.state['gold']=11
    w.receive_recognition(copy.deepcopy(result),before)
    check('manual state edit does not discard current visual tracking',len(w.canvas.tracking_regions)==3 and w.shop_highlight.isVisible() and w.store.state['gold']==11)
    missing=copy.deepcopy(result)
    for f in missing['fields']:
        if f['key'].startswith(('shop:','offer:')):f['value']=None
    deliver(missing);check('isolated OCR miss retains verified cards',len(w.canvas.tracking_regions)==3)
    latest[0]=None;w.update_shop_highlight();check('brief capture contention does not flash surface',w.shop_highlight.isVisible())
    latest[0]=game.copy();first=w.canvas.tracking_regions[0];x,y,rw,rh=first['sample_rect'];h,ww=game.shape[:2]
    latest[0][int(y*h):int((y+rh)*h)+1,int(x*ww):int((x+rw)*ww)+1]=0
    w.update_shop_highlight();check('one sold card leaves other two highlighted',len(w.canvas.tracking_regions)==2 and w.shop_highlight.isVisible())
    w.clear_shop_tracking();w.live=False

    s=new_state();s.update(target='卡西米尔',phase='整备',round=5,level=3,gold=8,units=[unit(w.db.by_name['砾']['operator_id'])])
    s['opening']=recompute(w.db,{'mode':'coop','selected':None,'groups':{},'core':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']=='核心盟约'],'additional':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']!='核心盟约']})
    w.store.state=s;w.last_recognition=None;w.solo_briefing.reset();w.refresh_all();events()
    w.overlay.route_lock.toggle.click();events()
    check('overlay can lock offered route in all three controls',w.store.state['route_lock']=='R02' and all(c.toggle.text()=='解锁路线' for c in (w.home_route_lock,w.ai_route_lock,w.overlay.route_lock)))
    saved=json.loads((w.storage.root/'session.json').read_text('utf8'));check('lock persists in saved session',validate_state(saved,w.db)['route_lock']=='R02')
    w.store.state.update(target='乌萨斯',level=6,units=[unit(w.db.by_name['塔露拉']['operator_id'])]);w.refresh_all();events()
    check('new board and level update steps within locked route',route_matches(w.db,w.store.state)[0]['id']=='R02' and '已锁定路线' in w.overlay.content.text())
    w.navigate('analysis',False);w.grab().save(str(OUT/'route-lock-main.png'));w.overlay.grab().save(str(OUT/'route-lock-overlay.png'))
    for e in w.store.state['opening']['core']:
        if e['name']=='卡西米尔':e['state']='grey'
    recompute(w.db,w.store.state['opening']);w.refresh_all();events()
    check('ban conflict keeps lock with explicit explanation',w.store.state['route_lock']=='R02' and '不会自动换线' in w.overlay.content.text() and not w.overlay.tracking_choices.buttons)
    w.home_route_lock.toggle.click();check('main window unlock restores route selection',not w.store.state['route_lock'] and route_matches(w.db,w.store.state)[0]['id']=='R04')

    w.new_session();w.live=True
    frame=cv2.imdecode(np.fromfile(HERE/'build/opening-recognition/solo.png',np.uint8),cv2.IMREAD_COLOR)
    opening=w.recognizer.opening.recognize(frame);deliver(opening);deliver(opening)
    frozen=copy.deepcopy(w.store.state['opening']);status=w.overlay.opening_status.text();content=w.overlay.content.text()
    cells=[w.opening_table.item(i,0) for i in range(26)];bans=w.overlay.opening_bans.text();rev=w.store.state['revision']
    w.opening_summary.verticalScrollBar().setValue(w.opening_summary.verticalScrollBar().maximum());position=w.opening_summary.verticalScrollBar().value()
    for _ in range(4):deliver(blank())
    deliver(opening);deliver(opening)
    check('locked content and status do not flicker across lost frames',w.overlay.opening_status.text()==status and w.overlay.opening_bans.text()==bans and w.overlay.content.text()==content)
    check('locked table keeps cells instead of rebuilding them',all(w.opening_table.item(i,0) is cell for i,cell in enumerate(cells)))
    check('locked summary keeps scroll position',w.opening_summary.verticalScrollBar().value()==position and w.store.state['revision']==rev)
    check('visual lock marks all rows',all(w.opening_table.item(i,2).text()=='已锁定' for i in range(26)))
    changed=copy.deepcopy(opening);o=changed['opening'];o['selected']='right'
    for e in o['core']:e['state']='lit' if e['name'] in o['groups']['right'] else 'grey'
    recompute(w.db,o);changed['fields'][0]['value']=json.dumps(o)
    deliver(changed);check('new group never immediately overwrites lock',snapshot_key(w.store.state['opening'])==snapshot_key(frozen) and '核对中' in w.overlay.opening_status.text())
    deliver(changed);check('stable changed group replaces lock exactly once',w.store.state['opening']['selected']=='right' and w.store.state['revision']==rev+1)
    check('confirmed advice no longer recommends the opposite group','已锁定右组' in w.overlay.content.text() and '优先选择左组' not in w.overlay.content.text() and '当前锁定：右组' in w.opening_summary.toPlainText())
    w.navigate('bans',False);events();w.grab().save(str(OUT/'opening-lock-main.png'));w.overlay.grab().save(str(OUT/'opening-lock-overlay.png'))
    w.capture_once=lambda *a,**k:None;w.begin_opening_review();check('review explicitly unlocks detection',w.review_opening and not w.solo_briefing.locked and '等待' in w.overlay.opening_confirm.text())
    w.end_opening_review();w.new_session();check('new session clears both locks',not w.store.state.get('route_lock') and not w.solo_briefing.locked)
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'scope':'Saved PC screenshots, scripted recognition sequences and offscreen UI; all game-window calls mocked. No live game or external API used.'},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.live=False;w.hotkeys.clear();w.timer.stop();w.shop_highlight.hide();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'checks':len(checks),'passed':all(c['passed'] for c in checks)}))
