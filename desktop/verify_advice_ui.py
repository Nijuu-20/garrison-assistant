"""Offscreen advice and toggle tests; mock AI content, no desktop interaction."""
import copy,json,os
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/advice-ui';OUT.mkdir(parents=True,exist_ok=True)
os.environ['GARRISON_DATA_DIR']=str(HERE/'build/advice-ui-profile');os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtGui import QFontDatabase
from garrison.ui import MainWindow
from garrison.core import new_state,unit,fingerprint
from garrison.coach import normalize_result,make_context
from garrison import __version__
app=QApplication([])
for f in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.store.state=new_state();w.show();app.processEvents();checks=[]
def check(name,value):checks.append({'test':name,'passed':bool(value)});assert value,name
try:
    w.overlay_toggle_button.click();app.processEvents();check('main toggle opens panel',w.overlay.isVisible() and w.overlay_toggle_button.isChecked())
    w.overlay_toggle_button.click();app.processEvents();check('main toggle closes panel',not w.overlay.isVisible() and not w.floating.isVisible() and not w.overlay_toggle_button.isChecked())
    w.show_overlay();w.minimize_overlay();check('minimize remains enabled',w.floating.isVisible() and w.overlay_toggle_button.isChecked())
    w.overlay_toggle_button.click();check('toggle closes minimized icon',not w.floating.isVisible() and not w.overlay_toggle_button.isChecked())
    w.hotkey(2);check('shortcut opens and syncs toggle',w.overlay.isVisible() and w.overlay_toggle_button.isChecked())
    w.hotkey(2);check('shortcut minimizes with icon',w.floating.isVisible() and w.overlay_toggle_button.isChecked())
    check('no close button in overlay',not any(b.text()=='×' or '关闭' in b.accessibleName() for b in w.overlay.findChildren(QPushButton)))
    check('analysis is before target section',w.overlay.advice_layout.indexOf(w.overlay.analysis_box)<w.overlay.advice_layout.indexOf(w.overlay.goal))
    opening=json.loads((HERE/'build/opening-recognition/solo-result.json').read_text('utf8'))['opening']
    s=w.store.state;s.update(phase='整备',round=3,gold=8,level=2,target='卡西米尔',opening=opening,
      units=[unit(w.db.by_name['砾']['operator_id'])],shop=[{'op_id':w.db.by_name['野鬃']['operator_id'],'cost':2,'slot':0}])
    w.ai_result=normalize_result({'goal':'先买野鬃推进卡西米尔，再留资金补齐第三名成员。',
      'assessment':'当前已确认砾，商店有野鬃；这次购买可以推进主力盟约，但还不会直接激活三人档。',
      'actions':[{'type':'buy','slot':0,'reason':'符合已选目标，2资金即可增加一名不同成员。','expected_gain':'卡西米尔成员从1名增至2名，还需第三名不同干员。','condition':'确认当前商店仍为野鬃。'}],
      'economy':'购买后剩余6资金。先留作补齐成员；未确认升级与刷新实际价格前不预设支出。',
      'target_recommendation':{'name':'卡西米尔','reason':'已有砾和当前商店的野鬃，且该盟约未被本局禁选。','transition':'补第三名不同成员后再考虑其他路线；不要为了副盟约立即打散主力。'},
      'formation':['野鬃购买后先留在整备区；核对部署位后再上场。当前没有准确格位，不指定坐标。'],
      'alternative':'如果商品已变化，先保留资金并重新查看商店，不预设刷新后会出现哪名干员。',
      'next_round':'优先留意第三名不同的卡西米尔成员，再结合实际升级费用决定节奏。',
      'warnings':['当前只记录了已确认成员，晋升前还要核对精锐与完整阵容。'],
      'explanation':'这条路线利用已有成员和已知商品，减少为未成型路线反复刷新。'},w.db,s)
    w.ai_result['fingerprint']=fingerprint(s);w.ai_result['elapsed_ms']=999;w.ai_toggle.setChecked(True)
    w.recognition_status='DEBUG_SENTINEL 1234 ms confidence 99% 区域 原文';w.refresh_all();w.show_overlay();app.processEvents()
    check('AI actions shown before targets','购买 野鬃' in w.overlay.content.text() and w.overlay.activity.text()=='AI 分析')
    check('no recognition logs in overlay','DEBUG_SENTINEL' not in '\n'.join(l.text() for l in (w.overlay.content,w.overlay.activity,w.overlay.links)))
    check('AI detail rendered in main',all(t in w.ai_output.toPlainText() for t in ('理由：','预期：','条件：','资金安排','站位与装备','后续目标','备选方案','目标盟约')))
    check('forbidden targets not recommended',all(title.text().split(' / ')[-1] not in {'乌萨斯','叙拉古','炎','阿戈尔','谢拉格'} for box,title,_ in w.overlay.suggestions if not box.isHidden()))
    w.navigate(8,False);w.ai_status.setText('界面预览 · 模拟 AI 响应');app.processEvents();w.grab().save(str(OUT/'main-detailed-analysis.png'));w.overlay.grab().save(str(OUT/'overlay-analysis.png'))
    w.settings['overlay_scale']=150;w.overlay.update_content();app.processEvents()
    check('large font scroll content stays within window',w.overlay.width()==410 and w.overlay.content.wordWrap())
    w.overlay.grab().save(str(OUT/'overlay-analysis-150.png'));w.settings['overlay_scale']=100
    s['gold']=1;w.refresh_all();check('old AI commands disappear after state change','AI 分析'!=w.overlay.activity.text() and '花费 2' not in w.overlay.content.text())
    w.ai_result=None;w.last_recognition=json.loads((HERE/'build/opening-recognition/solo-result.json').read_text('utf8'));w.overlay.update_content()
    check('opening advice replaces ban dump','起步推荐' in w.overlay.content.text() and '推算禁用' not in w.overlay.content.text() and '禁核心' not in w.overlay.content.text())
    app.processEvents();w.overlay.grab().save(str(OUT/'overlay-opening.png'))
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'provider':'mock response; no live API used'},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.hotkeys.clear();w.timer.stop();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps(checks,ensure_ascii=False))
