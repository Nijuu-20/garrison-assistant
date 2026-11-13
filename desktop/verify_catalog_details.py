"""Offline catalog interactions and reference-data checks, with an isolated profile."""
import json,os,tempfile
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/catalog-details';OUT.mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-catalog-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QTextDocument
from PySide6.QtTest import QTest
from garrison.ui import MainWindow
from garrison.core import fingerprint
from garrison import __version__
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
w=MainWindow();w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.navigate(2,False);w.show();app.processEvents()
d=w.catalog_detail;checks=[]
def check(name,value):
    checks.append({'test':name,'passed':bool(value)});assert value,name
def plain(widget):
    doc=QTextDocument();doc.setHtml(widget.text());return doc.toPlainText()
try:
    baseline=fingerprint(w.store.state)
    w.catalog_search.setText('赫拉格');app.processEvents()
    check('four distinct detail pages',[d.tabs.tabText(i) for i in range(d.tabs.count())]==['概览','特质','技能','资料'])
    check('overview has portrait and covenant icons',not d.art.pixmap().isNull() and d.covenant_flow.count()==2)
    for page,name in enumerate(('overview','trait-normal','skill-normal','reference')):
        d.tabs.setCurrentIndex(page);app.processEvents();w.grab().save(str(OUT/(name+'.png')))
    d.tabs.setCurrentIndex(1)
    check('normal trait and cap','层数+4' in plain(d.trait_effect) and '12层' in d.cap.text() and '24层' not in d.cap.text())
    check('trait highlighting preserves exact source text',plain(d.trait_effect)==d.op['effect_initial'])
    d.mode_buttons[True].click();app.processEvents()
    check('elite changes trait cap and training','层数+8' in plain(d.trait_effect) and '24层' in d.cap.text() and '精二60级' in d.training.text())
    check('elite highlighting preserves exact source text',plain(d.trait_effect)==d.op['effect_elite'])
    check('state buttons mutually exclusive',d.mode_buttons[True].isChecked() and not d.mode_buttons[False].isChecked())
    w.grab().save(str(OUT/'trait-elite.png'))
    d.tabs.setCurrentIndex(2);d.skill_buttons[1].click();app.processEvents()
    check('skill one elite data','145%' in plain(d.skill_effect) and d.sp_cost.value.text()=='3' and d.sp_initial.value.text()=='0')
    check('empty duration is not invented',d.duration.value.text()=='—')
    d.mode_buttons[False].click();app.processEvents()
    check('normal data replaces elite without changing skill','125%' in plain(d.skill_effect) and '145%' not in plain(d.skill_effect) and d.skill==1)
    d.skill_buttons[2].click();app.processEvents()
    check('skill selector changes effect',d.skill==2 and '弦月' in d.skill_title.text())
    d.mode_buttons[True].click();app.processEvents();w.grab().save(str(OUT/'skill-elite.png'))
    w.catalog_search.setText('砾');app.processEvents()
    check('operator change preserves page and mode',d.tabs.currentIndex()==2 and d.elite and '鼠群' in d.skill_title.text())
    check('two skill operator hides stale third button',d.skill_buttons[3].isHidden())
    check('new operator replaces all trait fields','卡西米尔' in plain(d.trait_effect) and '乌萨斯' not in plain(d.trait_effect))
    check('reference links retained','href=' in d.source_links.text() and 'PRTS' in d.source_links.text())
    for width,height in ((1100,720),(1380,900),(1600,1000)):
        w.resize(width,height);w.reset_catalog_filters();app.processEvents();viewport=w.catalog_list.viewport().size();grid=w.catalog_list.gridSize()
        for page in range(4):
            d.tabs.setCurrentIndex(page);d.mode_buttons[not d.elite].click();QTest.qWait(30)
            check(f'{width} page {page} keeps selector geometry',w.catalog_list.viewport().size()==viewport and w.catalog_list.gridSize()==grid)
            check(f'{width} page {page} stays inside detail',d.tabs.geometry().right()<=d.width() and d.tabs.widget(page).viewport().width()>200)
        w.grab().save(str(OUT/f'reference-{width}.png'))
    w.catalog_search.setText('不存在的干员测试');app.processEvents()
    check('empty search hides stale pages and image',d.tabs.isHidden() and d.art.pixmap().isNull() and d.source_links.text()=='' and not d.mode_buttons[True].isEnabled())
    w.catalog_search.setText('暴躁铁皮');app.processEvents()
    check('missing portrait and single skill supported',d.art.pixmap().isNull() and '暂无立绘' in d.art.text() and d.skill_buttons[2].isHidden() and d.skill_buttons[3].isHidden())
    w.catalog_search.setText('赫拉格');app.processEvents()
    check('search restores pages and actions',not d.tabs.isHidden() and d.mode_buttons[True].isEnabled() and d.add.isEnabled())
    check('catalog browsing never changes match',fingerprint(w.store.state)==baseline)
    # Exercise every packaged record, including null alternatives and missing art.
    for op in w.db.ops.values():
        w.show_operator(op['operator_id']);d.set_elite(False);d.set_elite(True)
        for number in d.skills:d.select_skill(number)
    check('all 143 records render both states',len(w.db.ops)==143)
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'version':__version__,'checks':len(checks),'passed':all(c['passed'] for c in checks)},ensure_ascii=False))
