"""Independent frame settings through real widgets and saved-frame callbacks, offscreen only."""
import copy,json,os,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;OUT=HERE/'build/stability-settings';OUT.mkdir(exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-stability-settings-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
import cv2,numpy as np
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtGui import QFontDatabase
import garrison.ui as ui
from garrison import __version__
from garrison.core import new_state,fingerprint,unit
from garrison.storage import Storage
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
ui.enum_windows=lambda:[]
ui.capture_window=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Live capture forbidden'))
store=Storage();store.settings['ai_profiles']=[{'id':'retained','name':'保留配置','url':'https://example.invalid/v1','model':'test'}];store.save_settings()
w=ui.MainWindow(store);w.timer.stop();w.hotkeys.clear();w.settings.update(reduce_motion=True,ai_enabled=False,ai_auto=False,auto_apply=True)
checks=[]
def check(name,ok):checks.append({'test':name,'passed':bool(ok)});assert ok,name
def configure(opening,shop,other=4):
    w.opening_stability_spin.setValue(opening);w.shop_stability_spin.setValue(shop);w.stability_spin.setValue(other)
    next(b for b in w.recognition_runtime_page.findChildren(QPushButton) if b.text()=='保存识别参数').click()
def feed(result):
    result=copy.deepcopy(result);result['time']=time.time()
    w.receive_recognition(result,fingerprint(w.store.state))
def reset():
    w.store.state=new_state();w.gate.reset();w.battle_gate.reset();w.solo_briefing.reset();w.clear_shop_tracking();w.live=True;w.refresh_all()
try:
    check('both controls accept one through six',all(s.minimum()==1 and s.maximum()==6 for s in (w.opening_stability_spin,w.shop_stability_spin)))
    configure(1,3)
    saved=Storage().settings
    check('independent values persist',(saved['opening_stable_frames'],saved['shop_stable_frames'],saved['stable_frames'])==(1,3,4))
    check('API profile preserved',saved['ai_profiles']==store.settings['ai_profiles'])
    check('one frame explicitly labelled disabled','关闭' in w.opening_stability_spin.text())
    solo=json.loads((HERE/'build/opening-recognition/solo-result.json').read_text('utf8'))
    coop=json.loads((HERE/'build/opening-recognition/coop-result.json').read_text('utf8'))
    for name,result in [('solo',solo),('coop',coop)]:
        reset();feed(result)
        check(name+' confirms and visually locks on one frame',w.store.state['opening'] is not None and w.solo_briefing.locked and '已锁定' in w.overlay.opening_status.text())
    reset();w.settings['opening_auto_confirm']=False;feed(solo)
    check('one frame does not enable disabled automatic confirmation',w.store.state['opening'] is None and w.solo_briefing.locked)
    w.settings['opening_auto_confirm']=True
    reset();w.live=False;feed(solo)
    check('single screenshot still requires manual confirmation',w.store.state['opening'] is None)
    reset();configure(3,1);feed(solo)
    check('opening waits while shop is single frame',w.store.state['opening'] is None)
    feed(solo);check('opening still waits at two',w.store.state['opening'] is None)
    feed(solo);check('opening confirms at three',w.store.state['opening'] is not None)
    confirmed=copy.deepcopy(w.store.state['opening']);w.store.state['units']=[unit('OP001')]
    retained=copy.deepcopy(w.store.state['units']);generation=w.capture_generation
    configure(4,1)
    check('saving invalidates in-flight captures',w.capture_generation==generation+1)
    check('saving preserves confirmed bans and roster',w.store.state['opening']==confirmed and w.store.state['units']==retained)
    check('saving resets opening evidence but retains visual lock',w.solo_briefing.count==0 and w.solo_briefing.ready_field is None and w.solo_briefing.locked)
    check('other roster timing remains independent',w.battle_gate.repeats==4)
    frame=cv2.imdecode(np.fromfile(HERE/'build/battle-recognition/pc-round14-b.png',np.uint8),cv2.IMREAD_COLOR)
    shop=json.loads((HERE/'build/shop-recovery/partial-result.json').read_text('utf8'))
    for frames in (1,3):
        reset();configure(4,frames);w.set_frame(frame)
        for n in range(1,frames+1):
            feed(shop)
            check(f'shop snapshot at {n} of {frames}',bool(w.store.state['shop'])==(n>=frames))
            check(f'shop markers at {n} of {frames}',bool(w.shop_watch.stable)==(n>=frames))
        check(f'partial slots remain pending at {frames}',w.store.state['field_meta']['shop_snapshot']['pending_slots']==[3,5])
    generation=w.capture_generation;counts=copy.deepcopy(w.gate.counts);matches=copy.deepcopy(w.shop_watch.stable)
    w.timeout_spin.setValue(w.timeout_spin.value()+1);w.save_runtime()
    check('API-only edits preserve recognition evidence',w.capture_generation==generation and w.gate.counts==counts and w.shop_watch.stable==matches)
    configure(1,1);check('timing edit clears obsolete marker evidence',not w.shop_watch.stable and not w.gate.counts)
    w.live=False;w.navigate('recognition');w.resize(1320,900);w.show()
    for _ in range(6):app.processEvents()
    check('both controls visible in recognition settings',w.opening_stability_spin.isVisible() and w.shop_stability_spin.isVisible())
    w.grab().save(str(OUT/'settings.png'))
finally:
    report={'version':__version__,'passed':bool(checks) and all(c['passed'] for c in checks),'checks':checks,'scope':'Isolated offscreen UI and saved screenshots; no desktop control, live capture or real API.'}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    w.live=False;w.quitting=True;w.overlay.close();w.floating.close();w.shop_highlight.close();w.close();app.processEvents();profile.cleanup()
print(json.dumps(report,ensure_ascii=False))
