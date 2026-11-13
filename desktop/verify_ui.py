"""Native Qt integration checks using an isolated test profile; no game automation."""
import os
import sys
import json
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
os.environ['GARRISON_DATA_DIR']=str(ROOT/'build'/'ui-validation-profile')
from PySide6.QtWidgets import QApplication, QPushButton, QComboBox
from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import Qt
from garrison.ui import MainWindow
from garrison.core import unit, fingerprint
from garrison.recognition import apply_fields

app=QApplication([])
for file in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+file)
window=MainWindow();window.settings['reduce_motion']=True;window.hotkeys.clear();window.show();app.processEvents()
out=ROOT/'build'/'ui-validation';out.mkdir(parents=True,exist_ok=True)
results=[]
def check(name,condition):
    results.append({'test':name,'passed':bool(condition)})
    assert condition,name
try:
    window.load_example();app.processEvents();check('example_is_labeled',window.store.state['name'].startswith('示例'))
    check('covenant_detail_matches_selected_row',window.covenant_text.toPlainText().startswith(window.covenant_rows[window.covenant_table.currentRow()]['name']))
    for i in range(window.stack.count()):
        window.navigate(i,False);app.processEvents();window.grab().save(str(out/f'page-{i+1:02}.png'))
    window.add_unit('OP001','bench');uid=window.store.state['units'][-1]['uid'];window.select_unit(uid)
    window.drop_unit('unit:'+uid,'field');check('board_move',window.selected_unit()['zone']=='field')
    window.undo();check('undo_move',window.selected_unit()['zone']=='bench');window.redo();check('redo_move',window.selected_unit()['zone']=='field')
    window.store.state['inventory']=['维式重锤','维式重锤'];window.refresh_all()
    row=next(i for i,r in enumerate(window.recipe_rows) if r['result']=='维式重锤 · 进阶');window.recipe_table.selectRow(row);window.craft()
    check('craft_action',window.store.state['inventory']==['维式重锤 · 进阶'])
    window.show_overlay();app.processEvents();check('overlay_visible',window.overlay.isVisible())
    check('overlay_topmost',bool(window.overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
    window.overlay.grab().save(str(out/'overlay.png'))
    window.minimize_overlay();app.processEvents();check('overlay_minimizes_to_button',not window.overlay.isVisible() and window.floating.isVisible())
    check('button_topmost',bool(window.floating.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
    window.floating.grab().save(str(out/'floating-button.png'));window.show_overlay();check('restore_overlay',window.overlay.isVisible() and not window.floating.isVisible())
    window.close_overlay();app.processEvents();check('overlay_complete_close',not window.overlay.isVisible() and not window.floating.isVisible())
    window.show_overlay();app.processEvents()
    window.navigate(2,False);app.processEvents()
    rects=[window.catalog_list.visualItemRect(window.catalog_list.item(i)) for i in range(8)]
    check('catalog_exactly_four_columns',len({r.y() for r in rects[:4]})==1 and rects[4].y()>rects[0].y())
    check('catalog_cards_fill_cells',rects[0].width()>=window.catalog_list.gridSize().width()-2)
    # Exercise real item hit targets; inspect normal, selected and hover frames together.
    QTest.mouseClick(window.catalog_list.viewport(),Qt.MouseButton.LeftButton,pos=rects[1].center())
    QTest.mouseMove(window.catalog_list.viewport(),rects[2].center());app.processEvents()
    check('catalog_click_updates_details',window.current_op==window.catalog_list.item(1).data(Qt.ItemDataRole.UserRole))
    window.grab().save(str(out/'catalog-selection.png'))
    for width,height in [(1100,720),(1600,1000)]:
        window.resize(width,height);app.processEvents()
        rects=[window.catalog_list.visualItemRect(window.catalog_list.item(i)) for i in range(8)]
        check(f'four_columns_at_{width}',len({r.y() for r in rects[:4]})==1 and rects[4].y()>rects[0].y())
        window.grab().save(str(out/f'catalog-{width}.png'))
        window.navigate(0,False);app.processEvents();window.grab().save(str(out/f'home-{width}.png'))
        window.navigate(2,False);app.processEvents()
    window.resize(1380,900);app.processEvents()
    check('catalog_has_no_dropdown_filters',not window.stack.widget(2).findChildren(QComboBox))
    check('covenant_buttons_are_separated',len(window.catalog_core.buttons)==11 and len(window.catalog_secondary.buttons)==17)
    QTest.mouseClick(window.catalog_core.buttons['乌萨斯'],Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.catalog_secondary.buttons['不屈'],Qt.MouseButton.LeftButton)
    QTest.mouseClick(window.catalog_category.buttons['叠层'],Qt.MouseButton.LeftButton);app.processEvents()
    actual={window.catalog_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window.catalog_list.count())}
    expected={o['operator_id'] for o in window.db.ops.values() if {'乌萨斯','不屈'}<=set(o['covenants']) and '叠层' in o['categories']}
    check('catalog_combines_core_secondary_role',bool(actual) and actual==expected)
    window.grab().save(str(out/'catalog-filter-active.png'))
    window.catalog_search.setText('折桠');app.processEvents()
    check('catalog_search_combines_with_buttons',window.catalog_list.count()==1 and window.operator_name.text()=='折桠')
    window.catalog_search.setText('不存在的干员检验');app.processEvents()
    check('empty_filter_clears_stale_details',window.catalog_list.count()==0 and window.current_op is None and window.operator_art.pixmap().isNull()
          and not window.catalog_add.isEnabled() and not window.catalog_compare.isEnabled())
    QTest.mouseClick(window.catalog_reset,Qt.MouseButton.LeftButton);app.processEvents()
    check('catalog_reset_clears_search_and_all_groups',window.catalog_list.count()==143 and not window.catalog_search.text() and all(not g.values() for g in window.catalog_filters))
    for name in ('炎','谢拉格'):QTest.mouseClick(window.catalog_core.buttons[name],Qt.MouseButton.LeftButton)
    actual={window.catalog_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window.catalog_list.count())}
    expected={o['operator_id'] for o in window.db.ops.values() if {'炎','谢拉格'}.intersection(o['covenants'])}
    check('catalog_same_group_multiselect',actual==expected)
    QTest.mouseClick(window.catalog_core.buttons['炎'],Qt.MouseButton.LeftButton)
    check('catalog_second_click_deselects',window.catalog_core.values()=={'谢拉格'})
    QTest.mouseClick(window.catalog_tier.buttons[3],Qt.MouseButton.LeftButton)
    check('catalog_tier_button_combines',window.catalog_list.count()>0 and all(window.db.ops[window.catalog_list.item(i).data(Qt.ItemDataRole.UserRole)]['tier']==3 for i in range(window.catalog_list.count())))
    QTest.mouseClick(window.catalog_tier.buttons[3],Qt.MouseButton.LeftButton)
    check('catalog_tier_second_click_restores_all',not window.catalog_tier.values() and window.catalog_tier.buttons[None].isChecked())
    window.reset_catalog_filters();app.processEvents()
    check('overlay_has_no_close_button',not any(b.text()=='×' or b.accessibleName()=='完全关闭悬浮面板' for b in window.overlay.findChildren(QPushButton)))
    window.show_overlay();QTest.mouseClick(window.overlay_toggle_button,Qt.MouseButton.LeftButton);app.processEvents()
    check('main_overlay_toggle_closes',not window.overlay.isVisible() and not window.floating.isVisible() and not window.overlay_toggle_button.isChecked())
    window.show_overlay();window.settings['overlay_scale']=150;window.overlay.update_content();app.processEvents()
    window.overlay.grab().save(str(out/'overlay-large-text.png'))
    window.settings['overlay_scale']=100;window.overlay.update_content()
    window.hotkey(1);app.processEvents();check('main_hotkey_minimize',window.isMinimized());window.hotkey(1);app.processEvents();check('main_hotkey_restore',not window.isMinimized())
    window.hotkey(2);app.processEvents();check('overlay_hotkey_minimize',window.floating.isVisible())
    window.export_image(str(out/'share.png'));check('share_exists',(out/'share.png').exists())
    # A delayed frame must not overwrite a manual edit made while recognition was running.
    before=fingerprint(window.store.state);window.store.state['gold']=50;window.live=True;window.settings['auto_apply']=True
    result={'fields':[{'key':'gold','value':1,'label':'1','confidence':1.,'raw':'1','method':'test','time':time.time()}], 'elapsed_ms':1,'time':time.time(),'candidates':[]}
    window.receive_recognition(result,before);window.receive_recognition(result,before)
    check('delayed_capture_does_not_overwrite',window.store.state['gold']==50)
    old_session=window.store.state['session_id'];window.new_session();check('new_session_clears_state',window.store.state['session_id']!=old_session and not window.store.state['units'] and window.store.state['gold'] is None)
    # Exercise the real frame result through the UI's same two-frame transaction.
    replay=ROOT/'build'/'recognition-real'/'result-2048.json'
    if replay.exists():
        import cv2
        import numpy as np
        from PIL import Image
        actual=json.loads(replay.read_text(encoding='utf-8'))
        window.set_frame(cv2.cvtColor(np.array(Image.open(replay.parent/'pc-round3.png')),cv2.COLOR_RGB2BGR))
        window.gate.reset();window.live=True;window.settings['auto_apply']=True
        window.receive_recognition(actual,fingerprint(window.store.state))
        check('auto_shop_waits_for_whole_stable_snapshot',not window.store.state['shop'])
        window.receive_recognition(actual,fingerprint(window.store.state))
        check('real_frame_hud_reaches_state',all(window.store.state[k]==v for k,v in [('round',3),('gold',6),('level',1)]))
        check('equipment_and_operators_keep_physical_slots',[x['slot'] for x in window.store.state['shop']]==[1,2,3] and window.store.state['recognized_offers']['0']['name']=='维式重锤')
        check('shop_equipment_not_owned',not window.store.state['inventory'])
        window.live=False;window.navigate(7,False);app.processEvents();window.grab().save(str(out/'recognition-real.png'))
        check('automatic_regions_are_visible',len([r for r in window.canvas.detected_regions if not r['key'].startswith('sprite:')])==14)
        for level,gold,region_count in [(5,18,18),(6,6,17)]:
            actual=json.loads((replay.parent/f'pc-level{level}-result-2048.json').read_text(encoding='utf-8'))
            window.set_frame(cv2.cvtColor(np.array(Image.open(replay.parent/f'pc-level{level}.png')),cv2.COLOR_RGB2BGR))
            window.live=True
            window.receive_recognition(actual,fingerprint(window.store.state))
            window.receive_recognition(actual,fingerprint(window.store.state))
            check(f'level_{level}_hud_reaches_state',window.store.state['level']==level and window.store.state['gold']==gold)
            check(f'level_{level}_shop_replaces_shifted_slots',[x['slot'] for x in window.store.state['shop']]==[1,2,3,4,5] and window.store.state['recognized_offers']['0']['name']=='炎国短刀')
            check(f'level_{level}_regions_relocated',len([r for r in window.canvas.detected_regions if not r['key'].startswith('sprite:')])==region_count)
            if level==6:check('maximum_clears_old_upgrade_cost',window.store.state['upgrade_cost'] is None and window.economy_fields['upgrade_cost'].specialValueText()=='已满级')
            window.live=False;app.processEvents();window.grab().save(str(out/f'recognition-level{level}.png'))
    window.ai_toggle.setChecked(True);window.ai_toggle.setChecked(False);check('ai_toggle_independent',not window.settings['ai_enabled'])
    window.new_session()
    window.navigate(0,False);app.processEvents();window.grab().save(str(out/'empty-home.png'))
finally:
    (out/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    window.closing=True;window.timer.stop();window.hotkeys.clear();window.overlay.hide();window.floating.hide();window.tray.hide();window.close()
print(json.dumps({'passed':len(results),'screenshots':str(out)},ensure_ascii=False))
