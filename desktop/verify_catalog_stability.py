"""Regression: filter changes must not oscillate viewport/grid size at fractional DPI."""
import os
import json
import time
from pathlib import Path
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from garrison import __version__
from garrison.ui import MainWindow

ROOT=Path(__file__).resolve().parent
scale=os.environ.get('QT_SCALE_FACTOR','1')
os.environ['GARRISON_DATA_DIR']=str(ROOT/'build'/f'catalog-stability-profile-{scale}')
out=ROOT/'build'/'catalog-stability';out.mkdir(parents=True,exist_ok=True)
app=QApplication([])
for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
window=MainWindow();window.timer.stop();window.hotkeys.clear()
window.settings['reduce_motion']=False;window.show()
events=[]
class Watch(QObject):
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Resize:events.append(event.size().toTuple())
        return False
watch=Watch();window.catalog_list.viewport().installEventFilter(watch)
checks=[]
def check(name,value):
    checks.append({'test':name,'passed':bool(value)})
    assert value,name

def wait_transition(*pages):
    # A fixed sleep can expire before Qt's first animation tick on a busy
    # desktop. Keep pumping events until the actual completion, with a bound.
    deadline=time.monotonic()+1
    while any(window.stack.widget(i).graphicsEffect() is not None for i in pages) and time.monotonic()<deadline:
        QTest.qWait(20)
try:
    window.navigate('catalog');wait_transition(1)
    check('completed_animation_releases_effect',window.stack.widget(1).graphicsEffect() is None)
    window.navigate(0);QTest.qWait(20);window.navigate('catalog');wait_transition(0,1)
    check('interrupted_animation_releases_both_pages',all(window.stack.widget(i).graphicsEffect() is None for i in (0,1)))
    window.navigate(0);window.navigate('catalog',False);QTest.qWait(150)
    check('nonanimated_navigation_releases_prior_effect',all(window.stack.widget(i).graphicsEffect() is None for i in (0,1)))
    for width,height in [(1100,720),(1380,900),(1600,1000)]:
        window.resize(width,height);window.reset_catalog_filters();QTest.qWait(150)
        viewport=window.catalog_list.viewport().size();grid=window.catalog_list.gridSize()
        actions=[('ursas',lambda:window.catalog_core.buttons['乌萨斯'].click()),
                 ('secondary',lambda:window.catalog_secondary.buttons['不屈'].click()),
                 ('role',lambda:window.catalog_category.buttons['叠层'].click()),
                 ('all',window.reset_catalog_filters),
                 ('empty',lambda:window.catalog_search.setText('无匹配对象')),
                 ('restore',window.reset_catalog_filters)]
        for name,action in actions:
            events.clear();action();QTest.qWait(120)
            check(f'{width}_{name}_viewport_stays_fixed',not events and window.catalog_list.viewport().size()==viewport)
            check(f'{width}_{name}_grid_stays_fixed',window.catalog_list.gridSize()==grid)
        window.grab().save(str(out/f'catalog-{scale}-{width}.png'))
    window.resize(1380,900);window.catalog_core.buttons['乌萨斯'].click();QTest.qWait(120)
    window.grab().save(str(out/f'filtered-{scale}.png'))
finally:
    report={'version':__version__,'device_pixel_ratio':window.devicePixelRatioF(),'checks':checks,'passed':bool(checks) and all(c['passed'] for c in checks)}
    (out/f'report-{__version__}-{scale}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    window.finish_transition();window.closing=True;window.tray.hide();window.overlay.hide();window.floating.hide();window.close()
print(json.dumps({'scale':scale,'passed':len(checks)},ensure_ascii=False))
