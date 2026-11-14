"""Home workflow and information architecture in an isolated offscreen application."""
import copy,json,os,tempfile,time
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/workspace-ui';OUT.mkdir(exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-workspace-')
os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QLineEdit
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import Qt
import garrison.ui as ui
from garrison import __version__
from garrison.core import new_state,unit
from garrison.storage import Storage
from garrison.opening import recompute
from garrison.recognition import apply_fields
from garrison.battle import observation_fields
app=QApplication([])
for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
windows=[{'hwnd':123,'pid':456,'title':'明日方舟（测试窗口）','width':2560,'height':1440}]
ui.enum_windows=lambda:list(windows)
ui.capture_window=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Live capture forbidden in this test'))
store=Storage();store.settings['ai_profiles']=[{'id':'preserve','name':'已保存的配置','url':'https://example.invalid/v1','model':'test'}]
store.settings['ai_profile']='preserve';store.settings['ai_enabled']=False;store.save_settings()
protected=copy.deepcopy(store.settings['ai_profiles'])
w=ui.MainWindow(store);w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.store.state=new_state();w.refresh_all();w.show()
checks=[]
def check(name,value):checks.append({'test':name,'passed':bool(value)});assert value,name
def events():
    for _ in range(6):app.processEvents()
def snap(name):events();w.grab().save(str(OUT/(name+'.png')))
try:
    check('five task-oriented pages',w.stack.count()==5 and list(w.page_ids)==['home','catalog','guides','tools','settings'])
    check('home first and primary references next',[b.text() for b in w.nav[:3]]==['01   首页','02   资料图鉴','03   阵容攻略'])
    check('API profile preserved',store.settings['ai_profiles']==protected and store.settings['ai_profile']=='preserve')
    check('API key field remains masked',w.api_key.echoMode()==QLineEdit.EchoMode.Password)
    check('catalog includes all reference types',[w.catalog_tabs.tabText(i) for i in range(w.catalog_tabs.count())]==['干员','盟约','装备','策略 / 指令','并排对比'])
    check('settings groups',[w.settings_tabs.tabText(i) for i in range(w.settings_tabs.count())]==['外观与快捷键','画面识别','AI / API','数据与来源'])
    check('home bind and AI controls share original model',w.home_step_cards[0].isAncestorOf(w.window_combo) and w.home_step_cards[1].isAncestorOf(w.ai_toggle))
    check('home confirmation starts safely',not w.home_ban_confirm.isEnabled() and not w.home_roster_confirm.isEnabled())
    snap('home-empty')
    w.window_combo.setCurrentIndex(1);w.live_button.click();events()
    check('bind starts sync from legacy capture-only profile without leaving home',w.live and w.settings['auto_apply'] and w.auto_apply_check.isChecked() and w.window_combo.currentData()['pid']==456 and w.stack.currentIndex()==w.page_ids['home'])
    generation=w.capture_generation;w.home_refresh_windows.click()
    check('refresh preserves same live binding',w.live and w.capture_generation==generation and w.window_combo.currentData()['hwnd']==123)
    w.live_button.click();check('home pauses capture',not w.live)
    w.ai_toggle.click();events();check('home AI enables existing profile',w.settings['ai_enabled'] and '已保存的配置' in w.home_api_status.text() and not w.coach.calls)
    w.ai_toggle.click();check('home AI disables independently',not w.settings['ai_enabled'] and not w.live)
    opening=recompute(w.db,{'mode':'coop','selected':None,'groups':{},
        'core':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']=='核心盟约'],
        'additional':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']!='核心盟约']})
    w.last_recognition={'opening':opening,'fields':[],'manual_opening':True};w.refresh_all()
    check('zero-ban preview can be confirmed from home',w.home_ban_confirm.isEnabled())
    w.home_ban_confirm.click();events();check('home confirms same opening state',w.store.state['opening'] and '已确认' in w.home_ban_status.text() and not w.home_ban_confirm.isEnabled())
    w.store.state.update(round=3,phase='整备');w.last_recognition=None;w.solo_briefing.reset()
    w.add_unit('OP001','field');w.add_unit('OP002','bench');events();w.home_roster_confirm.click()
    check('home confirms complete lineup',not w.store.state['field_meta']['battle_roster']['uncertain'] and '已确认' in w.home_roster_status.text())
    w.store.state['round']=4;w.refresh_all();check('new round requires recheck',w.home_roster_confirm.isEnabled() and '待核对' in w.home_roster_status.text())
    w.store.state['units'][0]['sprite_missing']=True;w.refresh_all();w.home_roster_confirm.click()
    check('home retains missing member for review instead of confirming',len(w.store.state['units'])==2 and '暂不可见' in w.home_roster_brief.text() and '待核对' in w.home_roster_status.text() and w.home_tabs.currentIndex()==w.home_tab_ids['roster'])
    w.select_unit(w.store.state['units'][0]['uid']);w.detach_sprite();w.home_roster_confirm.click()
    check('manual verification restores home confirmation','已确认' in w.home_roster_status.text())
    w.home_roster_details.click();check('lineup editable inside home',w.stack.currentIndex()==0 and w.home_tabs.currentIndex()==w.home_tab_ids['roster'])
    w.home_ban_details.click();check('ban details inside home',w.stack.currentIndex()==0 and w.home_tabs.currentIndex()==w.home_tab_ids['bans'])
    w.home_api_button.click();check('API shortcut opens settings subpage',w.stack.currentIndex()==4 and w.settings_tabs.currentIndex()==2)
    for name in ('home','catalog','guides','tools','settings'):
        w.navigate(name,False);snap(name)
    for key in ('covenants','equipment','commands','recognition','api','data','roster','bans'):
        w.navigate(key,False);snap(key)
    check('reference controls relocated intact',w.catalog_tabs.isAncestorOf(w.covenant_table) and w.catalog_tabs.isAncestorOf(w.equipment_list) and w.catalog_tabs.isAncestorOf(w.command_list))
    check('advanced controls only in settings',w.settings_tabs.isAncestorOf(w.canvas) and w.settings_tabs.isAncestorOf(w.api_url) and not w.home_content.isAncestorOf(w.api_url))
    check('inventory operations remain available',w.tools_tabs.isAncestorOf(w.inventory_list) and w.tools_tabs.count()==2)
    w.navigate('inventory',False);check('inventory shortcut selects its tab',w.stack.currentIndex()==3 and w.tools_tabs.currentIndex()==1)
    # Same manual picker is opened from the overlay and home; all filters use database fields.
    from garrison.tracking import item_key
    w.open_tracking();events();d=w.tracking_dialog
    def shown(index=0):return [d.lists[index].item(n) for n in range(d.lists[index].count()) if not d.lists[index].item(n).isHidden()]
    def names(index=0):return {i.data(Qt.ItemDataRole.UserRole)['name'] for i in shown(index)}
    op=w.db.by_name['赫拉格'];d.core_filter.buttons['乌萨斯'].click()
    check('manual core covenant filter',names()=={e['name'] for e in w.db.ops.values() if '乌萨斯' in e['covenants']})
    d.secondary_filter.buttons['突袭'].click()
    check('manual core and secondary combine',names()=={e['name'] for e in w.db.ops.values() if {'乌萨斯','突袭'}<=set(e['covenants'])} and op['name'] in names())
    role=op['categories'][0];d.role_filter.buttons[role].click();d.operator_tier.buttons[op['tier']].click()
    check('manual type and tier combine',names()=={e['name'] for e in w.db.ops.values() if {'乌萨斯','突袭'}<=set(e['covenants']) and role in e['categories'] and e['tier']==op['tier']})
    d.search.setText('hlg');check('manual search combines with filters',names()=={'赫拉格'})
    selected=shown()[0];selected.setCheckState(Qt.CheckState.Checked);events();saved=copy.deepcopy(w.tracked)
    check('filtered selection synchronizes overlay and home',item_key(selected.data(Qt.ItemDataRole.UserRole)) in w.overlay.tracking_pins.buttons and w.tracked==saved and bool(saved))
    d.search.setText('无匹配对象');events();check('empty result is explicit and keeps pins',not names() and '没有匹配项' in d.empty_labels[0].text() and w.tracked==saved)
    d.reset_button.click();events();check('reset restores all entries and preserves checked state',len(names())==len(w.db.ops) and selected.checkState()==Qt.CheckState.Checked and w.tracked==saved)
    d.core_filter.buttons['乌萨斯'].click();d.core_filter.buttons['炎'].click()
    check('same-group selections use union',names()=={e['name'] for e in w.db.ops.values() if {'乌萨斯','炎'}.intersection(e['covenants'])})
    d.tabs.setCurrentIndex(1);d.equipment_type.buttons[True].click()
    check('equipment consumable filter independent of operator covenants',names(1)=={e['name'] for e in w.db.equipment.values() if e['consumable']})
    gear=next(e for e in w.db.equipment.values() if e['consumable']);d.equipment_tier.buttons[gear['tier']].click()
    check('equipment tier combines with type',names(1)=={e['name'] for e in w.db.equipment.values() if e['consumable'] and e['tier']==gear['tier']})
    chosen=shown(1)[0];chosen.setCheckState(Qt.CheckState.Checked);events()
    check('filtered equipment can be tracked',item_key(chosen.data(Qt.ItemDataRole.UserRole)) in w.home_pins.buttons)
    d.equipment_type.buttons[False].click();check('nonconsumable False value is a real filter',names(1)=={e['name'] for e in w.db.equipment.values() if not e['consumable'] and e['tier']==gear['tier']})
    d.reset_button.click();d.tabs.setCurrentIndex(0);d.core_filter.buttons['乌萨斯'].click();events();d.grab().save(str(OUT/'manual-filters.png'))
    for width,height in ((640,620),(820,780)):
        d.resize(width,height);events();d.grab().save(str(OUT/f'manual-filters-{width}.png'))
        bounds=d.lists[0].geometry();d.search.setText('无匹配对象');events()
        check(f'manual filter keeps list geometry at {width}',d.lists[0].geometry()==bounds and bounds.height()>=100)
        d.search.clear();events()
    d.pins.buttons[item_key(selected.data(Qt.ItemDataRole.UserRole))].click();events()
    check('cancel pinned item while filtered updates checkbox',selected.checkState()==Qt.CheckState.Unchecked)
    d.accept();events()
    w.navigate('home',False);w.open_home_tab('overview',False)
    for width,height in ((1100,720),(1380,900),(1600,1000)):
        w.resize(width,height);events();snap(f'home-{width}')
        check(f'four setup cards stay inside home at {width}',all(c.x()>=0 and c.x()+c.width()<=w.home_flow.width()+1 for c in w.home_step_cards))
        check(f'home actions not clipped at {width}',all(b.width()>=b.sizeHint().width()-2 for b in (w.home_ban_confirm,w.home_ban_details,w.home_roster_confirm,w.home_roster_details,w.live_button)))
    w.window_combo.setCurrentIndex(1);w.live_button.click();windows.clear();w.home_refresh_windows.click()
    check('closed process resets binding',not w.live and w.window_combo.currentData() is None and not w.live_button.isEnabled())
    check('no provider or game operation',w.coach.calls==0)
finally:
    report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'scope':'Offscreen real widgets and mock window handles; no live capture, game interaction or provider calls.'}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.timer.stop();w.hotkeys.clear();w.overlay.hide();w.floating.hide();w.tray.hide();w.close()
print(json.dumps({'passed':report['passed'],'checks':len(checks)}))
