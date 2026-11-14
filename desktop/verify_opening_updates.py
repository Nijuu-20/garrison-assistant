"""Low-difficulty, in-match recheck and repeated side-switch offline regression."""
import copy,json,os,tempfile,time
from pathlib import Path
import cv2,numpy as np
HERE=Path(__file__).resolve().parent;OUT=HERE/'build/opening-updates';OUT.mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-opening-updates-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from garrison.ui import MainWindow
from garrison.core import fingerprint,unit
from garrison.opening import recompute,rules,confirmation_problem
from garrison.opening_icons import asset_root
from garrison.advice import ban_context
from garrison import __version__
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.show_overlay();checks=[]
def check(name,value):
    checks.append({'test':name,'passed':bool(value)})
    assert value,name
def deliver(result):w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state));app.processEvents()
def render_icon(canvas,name,x,y,lit,size=100):
    ref=refs[name];a=cv2.imdecode(np.fromfile(asset_root()/ref['file'],np.uint8),-1)[:,:,3]
    cv2.circle(canvas,(x,y),size//2+7,(150,220,5) if lit else (48,52,50),-1)
    a=cv2.resize(a,(size,size),interpolation=cv2.INTER_AREA)[:,:,None]/255
    region=canvas[y-size//2:y-size//2+size,x-size//2:x-size//2+size]
    region[:]=(region*(1-a)+(12 if lit else 190)*a).astype(np.uint8)
def low_frame(count,relocated=False):
    frame=np.full_like(coop,25) if relocated else coop.copy()
    banned=set(rules()['small'][:count]);positions={}
    for k,kind in enumerate(('core','additional')):
        entries=[e for e in base['icon_matches'] if e['kind']==kind]
        for i,e in enumerate(entries):
            x,y=(340+(i%10)*200,350+k*370+(i//10)*300) if relocated else (round(e['x']*2560),round(e['y']*1440))
            lit=kind=='core' or e['name'] not in banned
            # Clear old glyph, status corner and glow before composing a new
            # fixture from independent database alpha, not a screenshot glyph.
            frame[y-65:y+65,x-65:x+65]=25;render_icon(frame,e['name'],x,y,lit)
            positions[e['name']]=(x,y)
    return frame,positions
try:
    coop=cv2.imdecode(np.fromfile(HERE/'build/opening-recognition/coop.png',np.uint8),1)
    base=w.recognizer.opening.recognize(coop)
    refs={r['name']:r for r in json.loads((asset_root()/'index.json').read_text('utf8'))['references'] if r['kind']!='anchor'}
    for count in (0,1,2,5):
        frame,_=low_frame(count);result=w.recognizer.recognize(frame)
        check(f'core all enabled / {count} additional bans detected',result['complete'] and result['opening']['mode']=='fixed' and
              not any(e['state']=='grey' for e in result['opening']['core']) and sum(e['state']=='grey' for e in result['opening']['additional'])==count)
        check(f'no OCR or group choice required / {count}',w.recognizer.engine is None and result['words']==[] and result['opening']['selected'] is None and not confirmation_problem(w.db,result['opening']))
    w.live=True;deliver(result);deliver(result)
    check('low difficulty auto confirms in overlay',w.store.state['opening']['mode']=='fixed' and '无（全部启用）' in w.overlay.opening_bans.text() and not w.overlay.opening_confirm.isEnabled())
    frame,positions=low_frame(2,relocated=True)
    review=w.recognizer.recognize(frame,{'opening_review':True})
    (OUT/'review-result.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),'utf8')
    check('in-match review locates relocated icons without screenshot anchors',review['complete'] and review['opening']['context']=='in_match' and review['opening']['mode']=='fixed')
    cv2.imencode('.png',cv2.resize(frame,(1280,720)))[1].tofile(str(OUT/'synthetic-info.png'))
    missing=frame.copy();x,y=positions['炎'];missing[y-65:y+65,x-65:x+65]=25
    partial=w.recognizer.recognize(missing,{'opening_review':True})
    check('in-match missing icon cannot be interpreted as unrestricted',not partial['complete'] and not partial['fields'][0]['value'])
    blank=w.recognizer.recognize(np.zeros_like(frame),{'opening_review':True})
    check('failed recheck never falls back to HUD OCR',not blank['complete'] and blank['fields']==[] and w.recognizer.engine is None)
    # Begin a running match with all protected fields populated.
    w.new_session();w.live=False;u=unit('OP001');u['equipment']=[next(iter(w.db.equipment))]
    w.store.state.update(phase='整备',round=8,level=5,gold=18,units=[u],shop=[{'op_id':'OP002','cost':2,'slot':0}],inventory=[next(iter(w.db.equipment))],target='乌萨斯')
    w.refresh_all();protected=copy.deepcopy(w.store.state);calls=[]
    w.capture_once=lambda *a,**kw:calls.append(w.review_opening)
    check('overlay always exposes recheck entry',not w.overlay.opening_review_button.isHidden())
    w.overlay.opening_review_button.click();app.processEvents()
    check('overlay starts recheck without changing the match',calls==[True] and w.review_opening and w.store.state==protected and w.overlay.opening_box.isVisible() and not w.overlay.opening_confirm.isEnabled())
    deliver(blank);check('failed recheck keeps match and waits',w.store.state==protected and not w.overlay.opening_confirm.isEnabled())
    deliver(review);check('manual recheck can be confirmed from overlay',w.overlay.opening_confirm.isEnabled())
    w.overlay.opening_confirm.click();app.processEvents()
    check('confirmation preserves phase roster gear money and session',all(w.store.state[k]==v for k,v in protected.items() if k not in ('opening','field_meta','revision','updated_at','events')))
    check('recheck updates local and AI constraints',ban_context(w.db,w.store.state)['core_banned']==[] and len(ban_context(w.db,w.store.state)['additional_banned'])==2 and not w.review_opening)
    check('recheck does not archive the current session',not (w.storage.root/'sessions'/(protected['session_id']+'.json')).exists())
    w.overlay.grab().save(str(OUT/'overlay-reconfirmed.png'))
    w.opening_review_button.click();deliver(review)
    check('same bans can be explicitly reconfirmed again',w.overlay.opening_confirm.isEnabled())
    w.overlay.opening_confirm.click();check('same-ban recheck exits review mode',not w.review_opening)
    no_ban_frame,_=low_frame(0,relocated=True);no_ban=w.recognizer.recognize(no_ban_frame,{'opening_review':True})
    w.live=True;w.overlay.opening_review_button.click();deliver(no_ban)
    check('live in-match review waits for agreement',len(ban_context(w.db,w.store.state)['additional_banned'])==2 and w.review_opening)
    deliver(no_ban)
    check('live in-match review auto confirms zero bans and preserves match',not ban_context(w.db,w.store.state)['additional_banned'] and not w.review_opening and
          w.store.state['phase']=='整备' and w.store.state['round']==8 and w.store.state['gold']==18 and w.store.state['units']==protected['units'] and
          w.store.state['field_meta']['opening_snapshot']['source']=='自动识别')
    w.live=False
    w.overlay.opening_review_button.click();w.overlay.opening_review_cancel.click()
    check('return-to-match cancels a pending review',not w.review_opening and w.last_recognition is None and w.store.state['round']==8)
    # Normal scanning can recognize an in-match panel without its ready button.
    no_ready=coop.copy();no_ready[1250:,:]=20
    passive=w.recognizer.recognize(no_ready,{'in_match':True})
    check('normal scanning treats info without ready action as current match',passive['complete'] and passive['opening']['context']=='in_match')
    # Repeated actual recognition results with one agreeing incomplete frame.
    solo=cv2.imdecode(np.fromfile(HERE/'build/opening-recognition/solo.png',np.uint8),1)
    left=w.recognizer.recognize(solo,{'in_match':True})
    check('genuine new briefing still starts a new session',left['opening']['context']=='briefing')
    w.new_session();w.live=True;deliver(left);deliver(left);revision=w.store.state['revision']
    for index,side in enumerate(['right','left']*6):
        changed=copy.deepcopy(left);o=changed['opening'];o['selected']=side
        for e in o['core']:e['state']='lit' if e['name'] in o['groups'][side] else 'grey'
        recompute(w.db,o);changed['fields'][0]['value']=json.dumps(o)
        incomplete=copy.deepcopy(changed);incomplete['opening']['additional'].pop();incomplete['fields'][0]['value']=None;incomplete['complete']=False
        deliver(changed);deliver(incomplete);deliver(changed)
        check(f'repeated switch {index+1} updates after agreeing dropout',w.store.state['opening']['selected']==side and w.store.state['revision']==revision+index+1 and not w.store.state['field_meta']['opening_snapshot'].get('uncertain'))
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,
        'limits':'Saved opening screenshots, synthetic PRTS-icon layouts and scripted offscreen UI events; no actual low-difficulty/in-match game screen or live side-switch interaction was captured.'},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'checks':len(checks),'passed':all(c['passed'] for c in checks)},ensure_ascii=False))
