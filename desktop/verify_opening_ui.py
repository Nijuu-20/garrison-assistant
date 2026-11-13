"""Offscreen integration only: does not interact with the user's desktop."""
import copy,json,os,tempfile
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/opening-recognition'
profile=tempfile.TemporaryDirectory(prefix='garrison-opening-')
os.environ['GARRISON_DATA_DIR']=profile.name
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from garrison.ui import MainWindow
from garrison.core import new_state,fingerprint,unit,recommend
from garrison.opening import recompute
from garrison import __version__
app=QApplication([])
for f in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.store.state=new_state();w.show();app.processEvents();checks=[]
def check(name,value):checks.append({'test':name,'passed':bool(value)});assert value,name
try:
    solo=json.loads((OUT/'solo-result.json').read_text('utf8'));coop=json.loads((OUT/'coop-result.json').read_text('utf8'))
    check('opening auto confirmation defaults on',w.settings['opening_auto_confirm'] and w.overlay.opening_auto_check.isChecked())
    w.navigate(7,False);w.live=True;w.settings['auto_apply']=False;w.gate.reset()
    w.receive_recognition(solo,fingerprint(w.store.state));check('waits for stable opening',w.store.state['opening'] is None)
    check('overlay offers manual confirmation before stable',w.overlay.opening_confirm.isEnabled() and '禁选核心' in w.overlay.opening_bans.text())
    check('switches to opening tab',w.recognition_tabs.currentIndex()==2)
    check('preview 26 icon rows',w.opening_table.rowCount()==26)
    pictures=[w.opening_table.item(i,0).icon().pixmap(32,32).toImage() for i in range(26)]
    check('PRTS icons retain transparent backgrounds',all(p.hasAlphaChannel() and p.pixelColor(0,0).alpha()==0 for p in pictures))
    check('PRTS icons have visible silhouettes',all(any(p.pixelColor(x,y).alpha()>200 for y in range(p.height()) for x in range(p.width())) for p in pictures))
    w.receive_recognition(solo,fingerprint(w.store.state));check('stable opening applies without tactical auto apply',w.store.state['opening']['selected']=='left' and w.store.state['field_meta']['opening_snapshot']['source']=='自动识别')
    check('overlay confirmed state','已自动确认' in w.overlay.opening_status.text() and not w.overlay.opening_confirm.isEnabled())
    revision=w.store.state['revision'];w.receive_recognition(solo,fingerprint(w.store.state))
    check('same frame does not repeat confirmation',w.store.state['revision']==revision)
    w.live=False;check('solo advice in main and overlay','起步推荐' in w.local_advice.toPlainText() and '起步推荐' in w.overlay.content.text())
    app.processEvents();w.grab().save(str(OUT/'assistant-solo.png'));w.overlay.show();app.processEvents();w.overlay.grab().save(str(OUT/'overlay-solo.png'));w.overlay.hide()
    changed=copy.deepcopy(solo);opening=changed['opening'];opening['selected']='right'
    for e in opening['core']:e['state']='lit' if e['name'] in opening['groups']['right'] else 'grey'
    recompute(w.db,opening);changed['fields'][0]['value']=json.dumps(opening,ensure_ascii=False,sort_keys=True)
    before=set(w.store.state['opening']['banned_ids']);w.last_recognition=changed;w.apply_opening()
    check('manual side confirmation replaces bans',set(w.store.state['opening']['banned_ids'])!=before and w.store.state['opening']['selected']=='right')
    w.live=True;w.gate.reset();w.receive_recognition(solo,fingerprint(w.store.state))
    check('changed group suspends old restrictions',w.store.state['field_meta']['opening_snapshot']['uncertain'] and w.store.state['opening']['selected']=='right')
    w.receive_recognition(solo,fingerprint(w.store.state))
    check('new stable group replaces old restrictions',w.store.state['opening']['selected']=='left' and not w.store.state['field_meta']['opening_snapshot'].get('uncertain'))
    w.new_session();w.live=True;w.settings['auto_apply']=True;w.overlay.opening_auto_check.click()
    check('overlay switch synchronizes and persists',not w.settings['opening_auto_confirm'] and not w.opening_auto_check.isChecked() and not json.loads((w.storage.root/'settings.json').read_text('utf8'))['opening_auto_confirm'])
    for _ in range(3):w.receive_recognition(coop,fingerprint(w.store.state))
    check('disabled confirmation is not bypassed by tactical auto apply',w.store.state['opening'] is None)
    w.overlay.show();app.processEvents();w.overlay.grab().save(str(OUT/'overlay-confirm-opening.png'))
    page=w.stack.currentIndex();w.overlay.opening_confirm.click()
    check('overlay confirms without changing main page',w.store.state['opening']['mode']=='coop' and w.stack.currentIndex()==page and w.store.state['field_meta']['opening_snapshot']['source']=='手动确认')
    w.opening_auto_check.click();check('main switch syncs overlay',w.overlay.opening_auto_check.isChecked())
    w.new_session();w.live=False
    for _ in range(3):w.receive_recognition(solo,fingerprint(w.store.state))
    check('single screenshot remains manual',w.store.state['opening'] is None and w.overlay.opening_confirm.isEnabled())
    for mutate in (lambda o:o['additional'].pop(),lambda o:o.update(selected=None),lambda o:o['core'][0].update(state='unknown'),lambda o:o['core'][0].update(name=o['core'][1]['name'])):
        bad=copy.deepcopy(solo);mutate(bad['opening']);bad['fields'][0]['value']=json.dumps(bad['opening'],ensure_ascii=False,sort_keys=True)
        w.live=True;w.gate.reset()
        for _ in range(2):w.receive_recognition(bad,fingerprint(w.store.state))
        check('invalid icons or choice never auto confirm '+str(len(checks)),w.store.state['opening'] is None and not w.overlay.opening_confirm.isEnabled())
    w.gate.reset();low=copy.deepcopy(solo);low['fields'][0]['confidence']=.4
    for _ in range(3):w.receive_recognition(low,fingerprint(w.store.state))
    check('low confidence does not auto confirm',w.store.state['opening'] is None)
    w.gate.reset();w.receive_recognition(solo,fingerprint(w.store.state));stale=fingerprint(w.store.state)
    w.store.state['target']='乌萨斯';w.receive_recognition(solo,stale)
    check('inflight capture cannot override manual change',w.store.state['opening'] is None)
    w.live=False
    w.receive_recognition(coop,fingerprint(w.store.state));w.apply_opening()
    check('coop has no group recommendation','起步推荐' not in w.opening_summary.toPlainText() and '固定配置' in w.overlay.content.text())
    check('coop ban pool applied',w.store.state['opening']['banned_ids']==recompute(w.db,copy.deepcopy(coop['opening']))['banned_ids'])
    app.processEvents();w.grab().save(str(OUT/'assistant-coop.png'))
    # Entering a briefing from an old match archives and resets tactical data.
    w.store.state.update(phase='整备',round=9,gold=99,shop=[{'op_id':'OP001','cost':2}],units=[unit('OP001')]);oldid=w.store.state['session_id']
    w.last_recognition=solo;w.apply_opening()
    check('new match clears old units money shop',not w.store.state['units'] and not w.store.state['shop'] and w.store.state['gold'] is None and w.store.state['round'] is None)
    check('new match archives old state',w.store.state['session_id']!=oldid and (w.storage.root/'sessions'/(oldid+'.json')).exists())
    w.new_session();check('new session clears bans and preview',w.store.state['opening'] is None and w.visible_opening() is None)
    check('overlay confirmation hidden outside opening',w.overlay.opening_box.isHidden())
    calls=[];w.run_job=lambda *a,**kw:calls.append(a);w.last_recognition=solo;w.analyze()
    check('opening recommendation makes no API request',not calls)
finally:
    (OUT/'ui-report.json').write_text(json.dumps({'version':__version__,'checks':checks,'passed':all(c['passed'] for c in checks)},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps(checks,ensure_ascii=False))
