from pathlib import Path
import hashlib
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET
from garrison import __version__

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OUT=ROOT/'outputs'/f'desktop_{__version__}';RELEASE=OUT/'卫戍协议助手'
frozen=json.loads((HERE/'build'/f'frozen-check-{__version__}.json').read_text(encoding='utf-8'))
assert frozen['passed'],frozen
parity=json.loads((HERE/'build'/'frozen-source-parity.json').read_text('utf8'))
assert parity and all(parity.values()),parity
ui=json.loads((HERE/'build'/'ui-validation'/'report.json').read_text(encoding='utf-8'))
assert all(check['passed'] for check in ui),ui
recognition=json.loads((HERE/'build'/'recognition-validation'/'report.json').read_text(encoding='utf-8'))
game=json.loads((HERE/'build'/'recognition-real'/'report.json').read_text(encoding='utf-8'))
assert all(c['passed'] for rep in game['tests'] for c in rep['checks']) and game['negative']['passed']
battle=json.loads((HERE/'build'/'battle-recognition'/'report.json').read_text(encoding='utf-8'))
battle_ui=json.loads((HERE/'build'/'battle-recognition'/'ui-report.json').read_text(encoding='utf-8'))
assert battle['version']==__version__ and battle['passed'] and battle_ui['version']==__version__ and battle_ui['passed']
opening_reports={name:json.loads((HERE/'build/opening-recognition'/filename).read_text('utf8')) for name,filename in [('recognition','report.json'),('ui','ui-report.json'),('rule_parity','rule-parity.json'),('prts_icons','prts-report.json')]}
assert all(r['version']==__version__ and r['passed'] for r in opening_reports.values())
advice=json.loads((HERE/'build/advice-ui/report.json').read_text('utf8'))
assert advice['version']==__version__ and advice['passed']
tracking=json.loads((HERE/'build/tracking-ui/report.json').read_text('utf8'))
assert tracking['version']==__version__ and tracking['passed']
strategy=json.loads((HERE/'build/strategy-ui/report.json').read_text('utf8'))
assert strategy['version']==__version__ and strategy['passed']
catalog_details=json.loads((HERE/'build/catalog-details/report.json').read_text('utf8'))
assert catalog_details['version']==__version__ and catalog_details['passed']
opening_stability=json.loads((HERE/'build/opening-stability/report.json').read_text('utf8'))
assert opening_stability['version']==__version__ and opening_stability['passed']
opening_updates=json.loads((HERE/'build/opening-updates/report.json').read_text('utf8'))
assert opening_updates['version']==__version__ and opening_updates['passed']
test_suites=ET.parse(HERE/'build'/f'tests-{__version__}.xml').getroot().findall('testsuite')
test_counts={k:sum(int(s.get(k,0)) for s in test_suites) for k in ('tests','failures','errors','skipped')}
assert test_counts['tests'] and not (test_counts['failures'] or test_counts['errors']),test_counts
live_path=HERE/'build'/f'live-api-{__version__}.json'
live=json.loads(live_path.read_text(encoding='utf-8')) if live_path.exists() else None
if live:assert live['version']==__version__
game_live_path=HERE/'build'/f'live-game-{__version__}.json'
game_live=json.loads(game_live_path.read_text(encoding='utf-8')) if game_live_path.exists() else None
if game_live:
 assert game_live['version']==__version__ and game_live['passed']
 assert game_live['executable_sha256']==hashlib.sha256((RELEASE/'卫戍协议助手.exe').read_bytes()).hexdigest()
stability=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((HERE/'build'/'catalog-stability').glob(f'report-{__version__}-*.json'))]
assert len(stability)==3 and all(r['passed'] for r in stability),stability
shutil.copy2(HERE/'使用说明.txt',RELEASE/'使用说明.txt')
report={
 'version':__version__,'date':'2026-11-14','edition':'Windows development preview',
 'rules_and_api_tests':{'passed':test_counts['tests']-test_counts['skipped'],'failed':0,'skipped':test_counts['skipped'],'includes':'covenants, sequential budgets, unknown/expired observations, promotion exceptions, equipment rules, DPAPI, export isolation, cancellation, timeouts, call limits, reasoning-model request parameters, redacted API errors, unusable connection responses'},
 'ui_checks':ui,'catalog_stability':stability,'packaged_installation':frozen,'synthetic_recognition':recognition,'real_game_frame_replay':game,
 'battlefield_sprite_replay':battle,'battlefield_ui':battle_ui,
 'opening_briefing':opening_reports,
 'opening_confirmation':{'automatic_default':True,'independent_of_tactical_auto_apply':True,'overlay_manual_confirmation':True,'never_clicks_game':True},
 'ban_rule_correction':{'basis':'User live observation: Hellagur remains obtainable when Ursus is available and Assault is banned. Apply primary-core precedence; only operators without a primary core use the all-additional-banned rule. Original HTML membership mapping is retained.','new_live_test_performed':False},
 'analysis_and_overlay_ui':advice,
 'tracking_controls_and_shop_replay':tracking,
 'authored_strategy_and_delete_controls':strategy,
 'paged_catalog_and_state_switch':catalog_details,
 'solo_opening_temporal_replay':opening_stability,
 'low_difficulty_and_in_match_reconfirmation':opening_updates,
 'packaged_source_matches_current_source':parity,
 'live_game_verified':bool(game_live and game_live['passed']),'live_game_checks':game_live,
 'live_provider_verified':bool(live and live['passed']),'live_provider_checks':live,
 'ui_checks_origin':f'Rerun on {__version__}, including catalog button interactions and real-frame results through the UI stable-frame and shop snapshot transaction.',
 'recognition_replay_origin':f'Rerun on {__version__}; old HUD frames and new round14 sprite fixtures use the current recognition source.',
 'limitations':['Low-difficulty zero/variable bans, relocated in-match information and repeated group changes use synthetic layouts and offscreen UI sequences. No new actual low-difficulty or in-match game screen has been captured.',
 'Covenant identity templates use 26 PRTS original alpha icons from the existing local database. Four layout anchors and two historical test scenes use supplied screenshots. Replay transformations and occlusions are not independent live-game accuracy validation. No desktop interaction performed for this release.',
 'Authored strategy matching is a local heuristic over the existing November 13 library. API request content and selected skill documents were verified with a simulated provider; no new real-provider strategy quality or live-game replay was measured.',
 'Shop watch controls and boxes were checked offscreen with saved frames and mocked native geometry/foreground/pixel polling. Live click-through overlays, mixed-DPI monitors and refresh animations have not been validated on the user desktop.',
 'Detailed AI advice and explicit ban inputs were tested with a local simulated provider and offscreen UI. No real user API was called; actual provider quality and latency were not measured.',
 'Opening recommendations use target covenant, low-tier assembly cost and stacking capability; not measured win rates or boss-specific counters.',
 'Three real PC screenshots (levels 1, 5, 6) with the Closure theme; resized copies are not independent game frames. Other themes and game states remain unverified.',
 'Elite icons, equipment icons and empty slots require samples or manual maintenance; visible text is recognized.',
 'No population accuracy or strategy-quality claim. Sprite matching uses the independent model database and remains partial: 8 / 7 accepted out of 9 visible operators in two idle instants of round14.',
 'Sprite-only elite state is unknown. Invisible instances are excluded from recommendations. Complete roster review is required before automatic AI coaching.',
 'Individual API timings do not establish sustained latency or reliability.'],
 'data':{'operators':143,'covenants':26,'equipment':70,'commands':61,'skills':360,'avatars':143,'portraits':142,'battle_models':282,'battle_templates':2788},
 'requested_ui_updates':{'theme':'default Stronghold Protocol terminal','hud_layout':True,'catalog_columns':4,'dense_operator_slots':True,'catalog_button_filters':['core covenant','secondary covenant','role','tier'],'price_badge_selection_overlap_fixed':True,'main_overlay_toggle':True,'overlay_internal_close_button':False,'analysis_before_target_covenants':True,'no_overlay_recognition_logs':True,'explicit_bans_in_ai_input':True,'generated_application_and_floating_icon':True,'floating_size_default':56},
}
(OUT/'验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(OUT/'验证报告.json',RELEASE/'验证报告.json')
preview=OUT/'预览';preview.mkdir(exist_ok=True)
for source,name in [('page-01.png','作战终端示例.png'),('page-03.png','图鉴四列.png'),('catalog-selection.png','图鉴选中与费用.png'),('overlay.png','悬浮面板.png'),('floating-button.png','悬浮图标.png'),('empty-home.png','主窗口.png')]:
 shutil.copy2(HERE/'build'/'ui-validation'/source,preview/name)
shutil.copy2(HERE/'build'/'ui-validation'/'catalog-filter-active.png',preview/'图鉴组合筛选.png')
for source,name in [('pc-round14-annotated.png','战场小人比对.png'),('assistant-battle-preview.png','小人比对界面.png'),('assistant-battle-roster.png','小人实例与待确认状态.png')]:
 shutil.copy2(HERE/'build'/'battle-recognition'/source,preview/name)
for source,name in [('assistant-solo.png','单人开局推荐.png'),('assistant-coop.png','联机开局禁选.png'),('overlay-solo.png','开局悬浮建议.png')]:
 shutil.copy2(HERE/'build/opening-recognition'/source,preview/name)
for source,name in [('overlay-analysis.png','悬浮优先分析.png'),('main-detailed-analysis.png','AI详细建议.png'),('overlay-opening.png','开局建议与目标.png')]:
 shutil.copy2(HERE/'build/advice-ui'/source,preview/name)
shutil.copy2(HERE/'assets'/'garrison-icon.png',OUT/'应用图标.png')
for source,name in [('overlay-tracking.png','悬浮追踪名单.png'),('main-tracking.png','AI推荐与追踪.png'),('manual-selection.png','手动选择追踪.png'),('shop-tracking.png','商店框选高亮.png')]:
 shutil.copy2(HERE/'build/tracking-ui'/source,preview/name)
for source,name in [('local-guide-overlay.png','本地攻略悬浮建议.png'),('local-guide-main.png','本地攻略与候选.png'),('ai-guide-main.png','AI攻略与出处.png'),('guide-delete-button.png','攻略线路删除.png'),('api-delete-button.png','API配置删除.png')]:
 shutil.copy2(HERE/'build/strategy-ui'/source,preview/name)
shutil.copy2(HERE/'build/opening-recognition/overlay-confirm-opening.png',preview/'悬浮确认本局禁选.png')
shutil.copy2(HERE/'build/opening-updates/overlay-reconfirmed.png',preview/'悬浮局内重新确认禁选.png')
for source,name in [('overview.png','图鉴概览.png'),('trait-elite.png','图鉴精锐特质.png'),('skill-elite.png','图鉴精锐技能.png'),('reference.png','图鉴资料来源.png')]:
 shutil.copy2(HERE/'build/catalog-details'/source,preview/name)
shutil.copy2(HERE/'assets'/'icon-generation.json',OUT/'图标生成记录.json')

portable=OUT/f'卫戍协议助手-{__version__}-Windows便携版.zip'
with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for path in RELEASE.rglob('*'):
  if path.is_file():z.write(path,Path('卫戍协议助手')/path.relative_to(RELEASE))

source_zip=OUT/f'卫戍协议助手-{__version__}-Source.zip'
with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for path in HERE.rglob('*'):
  if not path.is_file() or any(p in ('build','__pycache__','.pytest_cache','dist') for p in path.relative_to(HERE).parts):continue
  z.write(path,Path('desktop')/path.relative_to(HERE))
 for relative in ['outputs/regulation_2026-11-13/卫戍协议_规程数据库.json',
                  'outputs/regulation_image_databases_2026-11-13/卫戍协议_规程_头像数据库.sqlite',
                  'outputs/regulation_image_databases_2026-11-13/卫戍协议_规程_精一立绘数据库.sqlite',
                  'outputs/regulation_covenant_icons_2026-11-14/卫戍协议_规程_盟约图标数据库.sqlite']:
  z.write(ROOT/relative,relative)
for path in (portable,source_zip):
 with zipfile.ZipFile(path) as z:assert z.testzip() is None
manifest={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (portable,source_zip,RELEASE/'卫戍协议助手.exe',OUT/'应用图标.png')}
(OUT/'SHA256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
