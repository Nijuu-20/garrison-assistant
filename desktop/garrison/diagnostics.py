"""Installation smoke check, also runnable inside the frozen portable executable."""
from pathlib import Path
import json
import time

def run(output_path):
    result={'kind':'packaged installation check','live_game_verified':False,'checks':{}}
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtCore import Qt
        from .core import Database,new_state,covenant_status
        from .recognition import Recognizer
        from .ui import MainWindow,asset_path
        import numpy as np
        import cv2
        from PIL import Image,ImageDraw,ImageFont
        app=QApplication.instance() or QApplication([])
        for font in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+font)
        db=Database();result['checks']['database_count']=len(db.ops)==143
        from windows_capture import WindowsCapture
        import inspect
        result['checks']['graphics_capture_backend']='window_hwnd' in inspect.signature(WindowsCapture).parameters
        result['checks']['avatar_blob']=db.image_bytes('OP001')[:8]==b'\x89PNG\r\n\x1a\n'
        result['checks']['portrait_blob']=bool(db.image_bytes('OP001','portrait'))
        result['checks']['icon_asset']=asset_path('garrison-icon.png').exists()
        from .strategy import verify_bundle,library,ai_material,local_plan
        result['checks']['authored_strategy_bundle']=verify_bundle() and len(library()['routes'])==11
        result['checks']['uploaded_skill_runtime']=bool(ai_material(db,new_state())['mechanics'])
        guide_state=new_state();guide_state['target']='卡西米尔'
        result['checks']['local_guide_recommendations']=bool(local_plan(db,guide_state)['recommendation_list'])
        from .opening import rules,availability,recompute,confirmation_problem,apply_snapshot
        from .opening_icons import IconMatcher
        icons=IconMatcher();icons.load()
        result['checks']['opening_icon_bank']=len(icons.refs)==30 and sum(r.get('source')=='PRTS' for r,_ in icons.refs)==26
        result['checks']['opening_rule_mapping']=len(rules()['operators'])==141
        restricted={'core':[{'name':'乌萨斯','state':'grey'}],'additional':[]}
        result['checks']['opening_ban_rule']=availability(db,restricted)[db.by_name['烈夏']['operator_id']]['status']=='banned'
        unrestricted=recompute(db,{'mode':'fixed','context':'in_match','selected':None,'groups':{},
            'core':[{'name':c['name'],'state':'lit'} for c in db.covenants if c['type']=='核心盟约'],
            'additional':[{'name':c['name'],'state':'lit'} for c in db.covenants if c['type']!='核心盟约']})
        result['checks']['zero_bans_confirmable']=not confirmation_problem(db,unrestricted)
        ongoing=new_state();ongoing.update(phase='整备',round=8,gold=18);apply_snapshot(ongoing,unrestricted)
        result['checks']['in_match_bans_preserve_hud']=ongoing['phase']=='整备' and ongoing['round']==8 and ongoing['gold']==18
        from .battle import BattleRecognizer
        battle=BattleRecognizer();battle.load()
        result['checks']['sprite_database']=battle.meta['operators']==143 and battle.meta['models']==282
        rid=next(i for i,r in enumerate(battle.refs) if r['model_id']=='OP074-front' and not r['flip'])
        sprite=battle.template(rid);scene=np.full((1152,2048,3),70,np.uint8);sh,sw=sprite.shape[:2];alpha=sprite[:,:,3:4]/255.
        scene[300:300+sh,700:700+sw]=(sprite[:,:,:3]*alpha+70*(1-alpha)).astype(np.uint8)
        match=battle.detect(scene,{'field':[.12,.20,.56,.43],'bench':[.10,.63,.80,.115]})
        result['checks']['packaged_sprite_matching']=any(d['op_id']=='OP074' and d['reliable'] for d in match['detections'])
        image=Image.new('RGB',(500,140),(20,30,30));draw=ImageDraw.Draw(image);draw.text((30,30),'资金 18',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',40),fill='white')
        recognized=Recognizer(db).recognize(cv2.cvtColor(np.array(image),cv2.COLOR_RGB2BGR),{'regions':[{'key':'gold','rect':[0,0,1,1]}]})
        result['checks']['offline_ocr_models']=recognized['fields'][0]['value']==18
        result['ocr_ms']=recognized['elapsed_ms']
        window=MainWindow();window.settings['reduce_motion']=True;window.show();app.processEvents()
        result['checks']['ten_pages']=window.stack.count()==10
        result['checks']['opening_review_tab']=window.recognition_tabs.count()==3 and hasattr(window,'opening_table')
        result['checks']['overlay_opening_confirmation']=hasattr(window.overlay,'opening_confirm') and window.settings['opening_auto_confirm']
        result['checks']['overlay_in_match_review_entry']=hasattr(window.overlay,'opening_review_button') and hasattr(window.overlay,'opening_review_cancel')
        restricted={'core':[{'name':'乌萨斯','state':'lit'}],'additional':[{'name':'突袭','state':'grey'}]}
        result['checks']['hellagur_primary_core_correction']=availability(db,restricted)[db.by_name['赫拉格']['operator_id']]['status']=='available'
        window.show_overlay();app.processEvents();window.minimize_overlay();app.processEvents()
        result['checks']['floating_icon']=window.floating.isVisible() and not window.floating.icon_pixmap.isNull()
        window.close_overlay();result['checks']['complete_overlay_close']=not window.overlay.isVisible() and not window.floating.isVisible()
        window.toggle_overlay();result['checks']['main_overlay_toggle_opens']=window.overlay.isVisible() and window.overlay_toggle_button.isChecked()
        window.minimize_overlay();window.toggle_overlay();result['checks']['main_overlay_toggle_closes_floating']=not window.overlay.isVisible() and not window.floating.isVisible() and not window.overlay_toggle_button.isChecked()
        from PySide6.QtWidgets import QPushButton
        result['checks']['overlay_has_no_close_button']=not any(b.text()=='×' for b in window.overlay.findChildren(QPushButton))
        from .tracking import item_key
        tracked={'kind':'operator','op_id':'OP001'};window.toggle_tracking(tracked)
        result['checks']['tracking_controls']=item_key(tracked) in window.ai_pins.buttons and item_key(tracked) in window.overlay.tracking_pins.buttons
        window.toggle_tracking(tracked)
        result['checks']['tracking_cancel']=item_key(tracked) not in window.ai_pins.buttons
        result['checks']['transparent_shop_highlight']=window.shop_highlight.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        window.navigate(2,False);app.processEvents();rects=[window.catalog_list.visualItemRect(window.catalog_list.item(i)) for i in range(5)]
        detail=window.catalog_detail;window.show_operator(db.by_name['赫拉格']['operator_id']);detail.mode_buttons[True].click()
        result['checks']['catalog_pages_and_elite_switch']=detail.tabs.count()==4 and detail.elite and '24层' in detail.cap.text() and '精锐' in detail.state_label.text()
        detail.mode_buttons[False].click();result['checks']['catalog_normal_switch']='12层' in detail.cap.text() and not detail.elite
        result['checks']['four_columns']=len({r.y() for r in rects[:4]})==1 and rects[4].y()>rects[0].y()
        window.catalog_core.buttons['乌萨斯'].click();window.catalog_secondary.buttons['不屈'].click()
        result['checks']['catalog_button_filters']=window.catalog_list.count()>0 and all(
            {'乌萨斯','不屈'}<=set(db.ops[window.catalog_list.item(i).data(Qt.ItemDataRole.UserRole)]['covenants']) for i in range(window.catalog_list.count()))
        window.closing=True;window.hotkeys.clear();window.timer.stop();window.tray.hide();window.close()
        result['passed']=all(result['checks'].values())
    except Exception as e:
        import traceback
        result['passed']=False;result['error']=str(e);result['traceback']=traceback.format_exc()
    path=Path(output_path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
