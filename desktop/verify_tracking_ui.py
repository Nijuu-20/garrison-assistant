"""Offscreen interaction + real screenshot replay; all live-window calls mocked."""
import copy,json,os,time
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/tracking-ui';OUT.mkdir(parents=True,exist_ok=True)
os.environ['GARRISON_DATA_DIR']=str(HERE/'build/tracking-ui-profile');os.environ['QT_QPA_PLATFORM']='offscreen'
import cv2,numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QFontDatabase,QImage,QPainter
from PySide6.QtWidgets import QApplication,QScrollArea
import garrison.ui as ui
from garrison.core import new_state,fingerprint
from garrison.coach import normalize_result
from garrison.hud import locate,price_badges
from garrison.storage import Storage
from garrison.tracking import item_key
from garrison.strategy import local_plan
from garrison.tracking_view import paint_matches
from garrison import __version__
app=QApplication([])
for f in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
w=ui.MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.tracked=[];w.store.state=new_state();w.show();checks=[]
def check(name,ok):checks.append({'test':name,'passed':bool(ok)});assert ok,name
def events():
    for _ in range(6):app.processEvents()
try:
    w.store.state.update(gold=6,phase='整备',round=9,level=6)
    entries=[{'kind':'operator','op_id':w.db.by_name[n]['operator_id'],'reason':'补充阵容控制与输出'} for n in ('夜莺','霍尔海雅','塞雷娅')]
    entries+=[{'kind':'equipment','name':'炎国短刀','reason':'候选装备说明只在选项提示中显示'}, {'kind':'equipment','name':'维式重锤','reason':'补充攻击力'}]
    w.ai_result=normalize_result({'goal':'先补齐缺口，再决定升级或保留资金。','actions':[],
        'assessment':'围绕当前目标逐步补强；下方候选可按需要追踪。','recommendation_list':entries},w.db,w.store.state)
    w.ai_result['fingerprint']=fingerprint(w.store.state);w.ai_toggle.setChecked(True);w.refresh_all();w.show_overlay();w.navigate('analysis',False);events()
    check('recommendation list separate from prose',len(w.ai_choices.buttons)==5 and '炎国短刀' not in w.ai_output.toPlainText() and '炎国短刀' not in w.overlay.content.text())
    check('short wrapped list has all rows visible',w.overlay.tracking_choices.area.verticalScrollBar().maximum()==0)
    check('choices below analysis and before targets',w.overlay.advice_layout.indexOf(w.overlay.analysis_box)<w.overlay.advice_layout.indexOf(w.overlay.tracking_choices)<w.overlay.advice_layout.indexOf(w.overlay.goal))
    before=fingerprint(w.store.state)
    opkey=item_key(entries[0]);gearkey=item_key(entries[3])
    w.overlay.tracking_choices.buttons[opkey].click();w.ai_choices.buttons[gearkey].click();events()
    check('click tracks both kinds in both windows',set(w.ai_pins.buttons)=={opkey,gearkey}==set(w.overlay.tracking_pins.buttons))
    check('tracking does not invalidate advice',before==fingerprint(w.store.state))
    check('stored immediately',len(Storage().tracking)==2)
    pin_y=w.overlay.tracking_pins.y()
    advice_scroll=next(a for a in w.overlay.findChildren(QScrollArea) if a.widget().layout()==w.overlay.advice_layout)
    advice_scroll.verticalScrollBar().setValue(advice_scroll.verticalScrollBar().maximum());events()
    check('tracked list stays above scrolling advice',w.overlay.tracking_pins.y()==pin_y and w.overlay.tracking_pins.parentWidget()==w.overlay)
    advice_scroll.verticalScrollBar().setValue(0)
    w.ai_pins.buttons[opkey].click();check('click pinned cancels in both windows',opkey not in w.overlay.tracking_pins.buttons and not w.ai_choices.buttons[opkey].isChecked())
    w.overlay.tracking_choices.buttons[opkey].click();w.open_tracking();events()
    dialog=w.tracking_dialog;dialog.search.setText('霍尔海雅');events()
    manual=next(i for i in dialog.rows if i.data(Qt.ItemDataRole.UserRole).get('op_id')==entries[1]['op_id'])
    check('manual search filters',not manual.isHidden() and sum(not i.isHidden() for i in dialog.rows)==1)
    manual.setCheckState(Qt.CheckState.Checked);events()
    check('manual selection synchronized',item_key(entries[1]) in w.overlay.tracking_pins.buttons)
    dialog.search.clear();dialog.grab().save(str(OUT/'manual-selection.png'));dialog.accept();events()
    w.grab().save(str(OUT/'main-tracking.png'));w.overlay.grab().save(str(OUT/'overlay-tracking.png'))
    # Many pins stay bounded and scroll independently; narrow panel still fits.
    original=copy.deepcopy(w.tracked)
    w.tracked=[{'kind':'equipment','name':name} for name in w.db.equipment]
    w.refresh_tracking();w.overlay.resize(340,720);events()
    pins=w.overlay.tracking_pins
    check('long list stays bounded and scrollable',pins.area.height()<=102 and pins.area.verticalScrollBar().maximum()>0)
    check('narrow panel chips stay inside viewport',all(b.width()<=pins.area.viewport().width() for b in pins.buttons.values()))
    old_buttons=dict(pins.buttons);w.refresh_tracking();events()
    check('unchanged refresh reuses controls',all(pins.buttons[k] is b for k,b in old_buttons.items()))
    w.tracked=original;w.overlay.resize(410,720);w.refresh_tracking();events()
    saved=copy.deepcopy(w.tracked);w.store.state['gold']=3;w.refresh_all()
    local_keys={item_key(i) for i in local_plan(w.db,w.store.state)['recommendation_list']}
    check('stale AI switches to current local lineup and preserves pins',bool(local_keys) and set(w.ai_choices.buttons)==local_keys and w.overlay.activity.text()=='本地攻略' and w.tracked==saved)
    w.ai_toggle.setChecked(False);check('AI off keeps manual tracking',len(w.overlay.tracking_pins.buttons)==3)
    # Rebuild current geometry from cached OCR words + actual price badges.
    root=HERE/'build/recognition-real';game=cv2.cvtColor(np.array(Image.open(root/'pc-level6.png').convert('RGB')),cv2.COLOR_RGB2BGR)
    result=json.loads((root/'pc-level6-result-2048.json').read_text('utf8'))
    layout=locate(result['words'],price_badges(game),w.db,game.shape[1]/game.shape[0]);result['shop_slots']=layout['slots'];result['regions']=layout['regions']
    w.set_frame(game);w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state));check('single frame not highlighted',not w.canvas.tracking_regions)
    w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state));events()
    check('stable real shop matches both kinds',len(w.canvas.tracking_regions)==3 and {m['slot'] for m in w.canvas.tracking_regions}=={0,2,3})
    check('offline preview never opens game overlay',not w.shop_highlight.isVisible())
    # Pure render of real fixture; does not touch the desktop.
    rgb=cv2.cvtColor(game,cv2.COLOR_BGR2RGB);h,ww=rgb.shape[:2];im=QImage(rgb.data,ww,h,rgb.strides[0],QImage.Format.Format_RGB888).copy()
    painter=QPainter(im);paint_matches(painter,QRectF(0,0,ww,h),w.canvas.tracking_regions);painter.end();im.save(str(OUT/'shop-tracking.png'))
    w.navigate('recognition',False);w.recognition_tabs.setCurrentIndex(0);events();w.grab().save(str(OUT/'preview-tracking.png'))
    w.toggle_tracking(entries[3]);check('cancel immediately removes equipment box',all(m['kind']=='operator' for m in w.canvas.tracking_regions));w.toggle_tracking(entries[3])
    # Exercise native-window guards against a fake target; no OS manipulation.
    target={'hwnd':12345,'pid':6789};w.window_combo.blockSignals(True);w.window_combo.addItem('测试窗口',target);w.window_combo.setCurrentIndex(w.window_combo.count()-1);w.window_combo.blockSignals(False)
    source={**target,'size':[ww,h],'captured':time.monotonic()};w.watch_source=source;w.live=True;w.settings['auto_apply']=False
    geometry=[-2048,30,ww,h];latest=[game];placements=[]
    ui.client_geometry=lambda *args:tuple(geometry) if geometry else None
    ui.peek_capture=lambda *args:latest[0]
    ui.place_highlight=lambda handle,rect:placements.append(rect)
    ui.set_capture_excluded=lambda *args:None
    w.update_shop_highlight();events()
    check('transparent input and focus flags',w.shop_highlight.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) and w.shop_highlight.windowFlags()&Qt.WindowType.WindowDoesNotAcceptFocus)
    check('physical negative monitor geometry forwarded',placements[-1]==tuple(geometry))
    geometry.clear();w.update_shop_highlight();check('other foreground hides boxes',not w.shop_highlight.isVisible())
    geometry[:]=[-1900,30,ww,h];w.update_shop_highlight();check('window movement realigns boxes',placements[-1][0]==-1900)
    w.minimize_overlay();w.update_shop_highlight();check('minimized floating icon retains highlight',w.shop_highlight.isVisible())
    w.close_overlay();check('terminal toggle also closes highlight',not w.shop_highlight.isVisible())
    w.show_overlay();latest[0]=game.copy();latest[0][int(h*.92):]=0;w.update_shop_highlight()
    check('refresh pixels remove old boxes before next OCR',not w.shop_highlight.isVisible() and not w.canvas.tracking_regions)
    latest[0]=game;w.live=False;w.set_frame(game);w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state));w.receive_recognition(copy.deepcopy(result),fingerprint(w.store.state))
    w.live=True;w.watch_source=source;geometry[2]-=100;w.update_shop_highlight();check('resize clears stale rectangles',not w.canvas.tracking_regions)
    w.live=False;w.new_session();check('new session keeps explicit pins but clears matches',{item_key(i) for i in w.tracked}=={item_key(i) for i in saved} and not w.canvas.tracking_regions and not w.ai_choices.buttons)
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'scope':'Offscreen controls, saved game frames and mocked native geometry/pixel polling; no live desktop or API used'},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.hotkeys.clear();w.timer.stop();w.shop_highlight.hide();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps(checks,ensure_ascii=False))
