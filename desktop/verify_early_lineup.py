"""Offscreen round-two-to-three integration. No capture or real AI request."""
import copy,json,os,tempfile,time
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/early-lineup';OUT.mkdir(exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-early-lineup-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from garrison import __version__
from garrison.ui import MainWindow
from garrison.core import new_state,unit,fingerprint
from garrison.opening import recompute
from garrison.recognition import interpret
from garrison.strategy import route_matches,local_plan
from garrison.tracking import item_key
from garrison.advice import overlay_advice
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings.update(reduce_motion=True,ai_enabled=False,ai_auto=False,auto_apply=True);w.show();w.navigate('analysis',False)
checks=[]
def check(name,ok):checks.append({'test':name,'passed':bool(ok)});assert ok,name
def events():
    for _ in range(5):app.processEvents()
try:
    s=new_state();s.update(round=2,phase='整备',units=[unit(w.db.by_name['幽灵鲨']['operator_id'])])
    s['opening']=recompute(w.db,{'mode':'coop','selected':None,'groups':{},
        'core':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']=='核心盟约'],
        'additional':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']!='核心盟约']})
    w.store.state=s;w.tracked=[{'kind':'equipment','name':'维式重锤'}];w.refresh_all()
    check('round two unrelated start waits',not w.ai_choices.buttons and not w.overlay.tracking_choices.buttons)
    check('empty bulk disabled',not w.ai_choices.bulk_button.isEnabled())
    result={'mode':'manual','fields':[interpret('round',[('3',.99)],w.db),interpret('phase',[('整备',.99)],w.db)],
        'regions':[],'notes':[],'time':time.time(),'elapsed_ms':0,'layout_valid':True}
    w.live=True;w.gate.reset();w.receive_recognition(copy.deepcopy(result),fingerprint(s))
    check('first round-three frame still waits',s['round']==2 and not w.ai_choices.buttons)
    w.receive_recognition(copy.deepcopy(result),fingerprint(s));w.live=False;events()
    check('confirmed round three shows both lists',s['round']==3 and w.ai_choices.buttons and w.overlay.tracking_choices.buttons)
    check('local list available without shop or level',not s['shop'] and s['level'] is None and not w.coach.calls)
    check('main and overlay agree',set(w.ai_choices.buttons)==set(w.overlay.tracking_choices.buttons))
    check('bulk control enabled',w.ai_choices.bulk_button.isEnabled() and w.overlay.tracking_choices.bulk_button.isEnabled())
    check('route header offers immediate tracking',w.overlay.route_lock.track.isEnabled() and w.ai_route_lock.track.isEnabled())
    w.overlay.resize(410,860);w.overlay.update_content();events();w.overlay.grab().save(str(OUT/'overlay-round3-untracked.png'))
    view=overlay_advice(w.db,s,None,None,False);operators=[i for i in view['recommendation_list'] if i['kind']=='operator']
    expected={item_key(i) for i in operators}|{'equipment:维式重锤'}
    w.overlay.route_lock.track.click();events()
    check('bulk adds lineup and preserves manual tracking',{item_key(i) for i in w.tracked}==expected)
    check('pins synchronized',set(w.ai_pins.buttons)==set(w.overlay.tracking_pins.buttons)==expected)
    check('bulk does not auto-lock route',not s['route_lock'])
    check('already tracked bulk disabled',not w.ai_choices.bulk_button.isEnabled() and not w.overlay.tracking_choices.bulk_button.isEnabled())
    check('route header tracks same state',not w.overlay.route_lock.track.isEnabled() and w.overlay.route_lock.track.text()=='阵容已追踪')
    w.track_recommended_formation();check('repeat never duplicates',len(w.tracked)==len(expected))
    key=item_key(operators[0]);w.overlay.tracking_pins.buttons[key].click();events()
    check('pinned click cancels one',key not in {item_key(i) for i in w.tracked} and w.ai_choices.bulk_button.isEnabled())
    w.ai_choices.bulk_button.click();events();check('main bulk restores only missing',{item_key(i) for i in w.tracked}==expected)
    w.overlay.route_lock.toggle.click();locked=s['route_lock'];check('early route can be locked',bool(locked))
    s.update(round=7,level=4,units=[unit(w.db.by_name['空弦']['operator_id'])]);w.refresh_all();events()
    check('later board keeps chosen route',[r['id'] for r in route_matches(w.db,s,20)]==[locked])
    check('route updates keep chosen tracking',{item_key(i) for i in w.tracked}==expected)
    s['round']=3;w.settings['ai_enabled']=True;w.ai_busy=True;w.ai_result=None;w.refresh_all();events()
    check('AI pending does not hide targets',bool(w.ai_choices.buttons) and not w.coach.calls)
    w.ai_busy=False;w.ai_result={'fingerprint':fingerprint(s),'goal':'先按路线准备核心','actions':[],
        'guide_profile_id':locked,'recommendation_list':[]};w.refresh_all();events()
    check('AI empty list retains chosen lineup',bool(w.ai_choices.buttons) and '先按路线准备核心' in w.overlay.content.text())
    w.settings['ai_enabled']=False;w.overlay.resize(410,860);w.overlay.update_content();events()
    w.overlay.grab().save(str(OUT/'overlay-round3.png'))
    w.ai_choices.resize(540,220);events();w.ai_choices.grab().save(str(OUT/'tracking-controls.png'))
finally:
    report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,
        'scope':'Simulated stable round transition and offscreen controls; no game capture, desktop control or real provider call.'}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'passed':report['passed'],'checks':len(checks)}))
