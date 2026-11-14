"""Partial-shop integration with saved pixels and an isolated offscreen UI."""
import copy,json,os,time
from pathlib import Path
import cv2,numpy as np
HERE=Path(__file__).parent;OUT=HERE/'build/shop-recovery'
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['GARRISON_DATA_DIR']=str(HERE/'build/shop-ui-profile')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from garrison.ui import MainWindow
from garrison import __version__
from garrison.core import new_state,fingerprint,recommend
from garrison.coach import make_context
from garrison.advice import overlay_advice
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
w=MainWindow();w.timer.stop();w.hotkeys.clear()
w.settings.update(reduce_motion=True,ai_enabled=False,ai_auto=False,auto_apply=True)
w.store.state=new_state();checks=[]
def check(name,ok):
    checks.append({'test':name,'passed':bool(ok)});assert ok,name
try:
    frame=cv2.imdecode(np.fromfile(HERE/'build/battle-recognition/pc-round14-b.png',np.uint8),cv2.IMREAD_COLOR)
    result=json.loads((OUT/'partial-result.json').read_text('utf8'));result['time']=time.time()
    w.set_frame(frame);w.live=True;w.gate.reset()
    w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state))
    check('first observation does not publish unconfirmed shop',not w.store.state['shop'])
    w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state))
    check('stable subset applied',len(w.store.state['shop'])==3 and len(w.store.state['recognized_offers'])==1)
    check('physical slots preserved',[i['slot'] for i in w.store.state['shop']]==[1,2,4])
    check('pending slots explicit',w.store.state['field_meta']['shop_snapshot']['pending_slots']==[3,5])
    check('confirmed operator rows displayed',w.shop_table.rowCount()==3)
    check('shop UI labels unknown cards','第 4、6 格待确认' in w.shop_equipment.text())
    check('local recommendations include confirmed operators',len(recommend(w.db,w.store.state,True))==3)
    check('overlay labels unknown cards','第 4、6 格待确认' in w.overlay.content.text())
    check('AI context retains pending slots',make_context(w.db,w.store.state)['shop_observation']['pending_slots']==[3,5])
    w.ai_result={'fingerprint':fingerprint(w.store.state),'goal':'已确认商品优先','actions':[]}
    w.settings['ai_enabled']=True;w.refresh_all()
    check('AI subset advice stays visible',overlay_advice(w.db,w.store.state,w.ai_result,None,True)['source']=='AI 分析')
    check('AI overlay includes pending caveat','已确认商品优先' in w.overlay.content.text() and '第 4、6 格待确认' in w.overlay.content.text())
    w.settings['ai_enabled']=False;w.live=False
    w.overlay.resize(490,790);w.overlay.update_content();app.processEvents()
    w.overlay.grab().save(str(OUT/'partial-overlay.png'))
finally:
    report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'scope':'Offscreen, saved frame, mocked AI text; no desktop control, live capture or API call.'}
    (OUT/'ui-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'passed':report['passed'],'checks':len(checks)}))
