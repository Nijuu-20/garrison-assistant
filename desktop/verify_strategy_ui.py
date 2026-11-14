"""Guide routing and delete controls in an isolated offscreen profile. No network."""
import copy,json,os,tempfile,threading
from pathlib import Path
HERE=Path(__file__).parent;OUT=HERE/'build/strategy-ui';OUT.mkdir(parents=True,exist_ok=True)
profile=tempfile.TemporaryDirectory(prefix='garrison-guide-check-');os.environ['GARRISON_DATA_DIR']=profile.name;os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QFontDatabase
from garrison.ui import MainWindow
from garrison.core import new_state,unit,fingerprint
from garrison.coach import make_context,normalize_result
from garrison.opening import recompute
from garrison.storage import Storage
from garrison.strategy import route_matches,ai_material,skill_text
from garrison import __version__
app=QApplication([])
for f in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+f)
storage=Storage();storage.guides=[{'name':'个人备忘','text':'保留自己的打法记录','favorite':True,'version':'自建','team':None}];storage.save_guides()
w=MainWindow(storage);w.timer.stop();w.hotkeys.clear();w.settings['reduce_motion']=True;w.show();checks=[]
def check(name,ok):checks.append({'test':name,'passed':bool(ok)});assert ok,name
def events():
    for _ in range(6):app.processEvents()
answer=[QMessageBox.StandardButton.No];QMessageBox.question=lambda *_args,**_kwargs:answer[0]
try:
    check('eleven authored routes and custom note coexist',len(w.builtin_guides)==11 and len(w.guide_entries)==12 and w.storage.guides[0]['name']=='个人备忘')
    s=new_state();s.update(target='卡西米尔',phase='整备',round=5,level=3,gold=8,
        units=[unit(w.db.by_name['砾']['operator_id'])],shop=[{'op_id':w.db.by_name['瑕光']['operator_id'],'cost':3,'slot':0}])
    s['opening']=recompute(w.db,{'mode':'coop','selected':None,'groups':{},
        'core':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']=='核心盟约'],
        'additional':[{'name':c['name'],'state':'lit'} for c in w.db.covenants if c['type']!='核心盟约']})
    w.store.state=s;w.refresh_all();w.show_overlay();w.navigate('analysis',False);events()
    check('AI off uses authored local advice',not w.settings['ai_enabled'] and w.coach.calls==0 and '低本卡西米尔' in w.ai_output.toPlainText() and w.overlay.activity.text()=='本地攻略')
    check('local advice supplies trackable equipment',any('精准狙击镜' in b.text() for b in w.ai_choices.buttons.values()))
    check('source credits link to registered author pages','某中二的鸽子' in w.overlay.sources.text() and 'BV1SNWe6gEvP' in w.overlay.sources.text())
    check('home also uses guide', '阶段参考' in w.local_advice.toPlainText() and 'S05' in w.home_sources.text())
    w.overlay.grab().save(str(OUT/'local-guide-overlay.png'));w.grab().save(str(OUT/'local-guide-main.png'))
    w.ai_choices.buttons[next(iter(w.ai_choices.buttons))].click();tracked=copy.deepcopy(w.tracked)
    material=make_context(w.db,s)['strategy_guide']
    check('AI retrieves exact uploaded relevant files',next(r['content'] for r in material['routes'] if r['route_id']=='R02')==skill_text('references/routes/R02.md') and len(material['routes'])<=3)
    w.ai_result=normalize_result({'goal':'采用某中二的鸽子与独步天下的卫戍均层交流群的低本卡西米尔路线。',
        'assessment':'当前三本、8资金，商店有瑕光，可推进现有再部署框架。',
        'actions':[{'type':'buy','slot':0,'reason':'已有砾，补充攻略核心成员','expected_gain':'取得瑕光后核对部署位，再计算盟约人数','condition':'商店与价格仍为当前记录'}],
        'economy':'买入后剩余5资金；玛恩纳当前需晋升奖励等特殊获取，不能假设三本直接刷新。',
        'guide_source_ids':['S05'],'recommendation_list':[{'kind':'equipment','name':'精准狙击镜','reason':'来源S05，玛恩纳装备方向；确认距离条件'}]},w.db,s)
    w.ai_result['fingerprint']=fingerprint(s);w.ai_toggle.setChecked(True);w.refresh_all();events()
    check('AI replaces local body but uses verified citations',w.overlay.activity.text()=='AI 分析' and 'S05' in w.ai_sources.text() and '购买 瑕光' in w.ai_output.toPlainText())
    w.grab().save(str(OUT/'ai-guide-main.png'))
    w.ai_toggle.setChecked(False);check('AI off restores local guide and keeps pins','阶段参考' in w.ai_output.toPlainText() and w.tracked==tracked)
    # Two fictitious provider profiles and test-only DPAPI keys.
    w.settings['ai_profiles']=[{'id':pid,'name':name,'url':'https://example.invalid/v1','model':'mock'} for pid,name in [('delete-me','测试配置 A'),('keep-me','测试配置 B')]]
    w.settings['ai_profile']='delete-me';w.storage.save_key('delete-me','test-only-A');w.storage.save_key('keep-me','test-only-B');w.fill_ai_profiles()
    w.navigate('api',False);events();w.grab().save(str(OUT/'api-delete-button.png'))
    w.api_delete_button.click();check('cancel API deletion preserves selection and key',len(w.settings['ai_profiles'])==2 and w.storage.get_key('delete-me')=='test-only-A')
    answer[0]=QMessageBox.StandardButton.Yes;w.request_cancel=threading.Event();generation=w.ai_generation;w.ai_toggle.setChecked(True)
    w.api_delete_button.click();events()
    check('delete removes only selected profile and key',[p['id'] for p in w.settings['ai_profiles']]==['keep-me'] and not w.storage.get_key('delete-me') and w.storage.get_key('keep-me')=='test-only-B')
    check('delete cancels requests and clears AI state',w.request_cancel.is_set() and w.ai_generation>generation and not w.settings['ai_enabled'] and w.ai_result is None)
    check('deleted API selection cleared and button disabled',w.ai_profile_combo.currentData()=='' and not w.api_delete_button.isEnabled() and not w.api_key.text())
    persisted=Storage();check('API deletion survives reload',[p['id'] for p in persisted.settings['ai_profiles']]==['keep-me'])
    w.navigate('guides',False);index=next(i for i,g in enumerate(w.guide_entries) if g.get('route_id')=='R02');w.guide_list.setCurrentRow(index);events();w.grab().save(str(OUT/'guide-delete-button.png'))
    answer[0]=QMessageBox.StandardButton.No;w.guide_delete_button.click();check('cancel guide deletion changes nothing',len(w.builtin_guides)==11 and not w.settings['disabled_guide_routes'])
    answer[0]=QMessageBox.StandardButton.Yes;w.guide_delete_button.click();events()
    check('deleted route removed from UI and local retrieval',len(w.builtin_guides)==10 and not any(m['route_id']=='R02' for m in route_matches(w.db,s,20)))
    check('deleted route removed from AI material','R02' in ai_material(w.db,s)['disabled_routes'] and not any(r['route_id']=='R02' for r in ai_material(w.db,s)['routes']))
    check('route deletion persists without deleting originals','R02' in Storage().settings['disabled_guide_routes'] and bool(skill_text('references/routes/R02.md')))
    check('deleting route does not remove tracked items',w.tracked==tracked)
    w.guide_list.setCurrentRow(len(w.guide_entries)-1);state_before=fingerprint(w.store.state);w.guide_delete_button.click()
    check('custom guide deletion preserves current session',not w.storage.guides and fingerprint(w.store.state)==state_before)
    # Empty-list controls remain usable and never index an unrelated entry.
    while w.guide_entries:w.guide_list.setCurrentRow(0);w.guide_delete_button.click()
    check('last guide deletion clears editor and disables button',not w.guide_delete_button.isEnabled() and not w.guide_text.toPlainText())
    w.new_guide();check('new guide still works after deleting all',len(w.guide_entries)==1 and not w.guide_text.isReadOnly())
finally:
    (OUT/'report.json').write_text(json.dumps({'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,
        'scope':'Isolated offscreen controls; original local knowledge and uploaded skill snapshot; model reply mocked, no real API or desktop interaction'},ensure_ascii=False,indent=2),'utf8')
    w.closing=True;w.hotkeys.clear();w.timer.stop();w.shop_highlight.hide();w.overlay.hide();w.floating.hide();w.tray.hide();w.close();profile.cleanup()
print(json.dumps(checks,ensure_ascii=False))
