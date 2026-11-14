"""Build a clean end-user ZIP and a complete, reproducible source/resource ZIP.

Never packages local user profiles, API credentials, caches or arbitrary outputs.
Verification records stay in desktop/build, outside the end-user distribution.
"""
from pathlib import Path
import hashlib,json,re,shutil,zipfile
from garrison import __version__

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
RELEASE=ROOT/'outputs'/f'desktop_{__version__}'/'卫戍协议助手'
OUT=ROOT/'outputs'/f'distribution_{__version__}'
CLEAN=OUT/'卫戍协议助手'
DEV_LICENSES={'pip','pytest','iniconfig','pluggy','PySide6_Pdf','PySide6_WebEngine'}
UNUSED_DOCS={'setuptools/_vendor/jaraco/text/Lorem ipsum.txt',
    'onnxruntime/tools/mobile_helpers/coreml_supported_mlprogram_ops.md',
    'onnxruntime/tools/mobile_helpers/coreml_supported_neuralnetwork_ops.md',
    'onnxruntime/tools/mobile_helpers/nnapi_supported_ops.md'}
DATABASES=[
 'outputs/regulation_2026-11-13/卫戍协议_规程数据库.json',
 'outputs/regulation_2026-11-13/卫戍协议_规程数据库.sqlite',
 'outputs/regulation_image_databases_2026-11-13/卫戍协议_规程_头像数据库.sqlite',
 'outputs/regulation_image_databases_2026-11-13/卫戍协议_规程_精一立绘数据库.sqlite',
 'outputs/regulation_battle_models_2026-11-13/卫戍协议_规程_战场小人数据库.sqlite',
 'outputs/regulation_covenant_icons_2026-11-14/卫戍协议_规程_盟约图标数据库.sqlite']
FIXTURES={
 'level-transition':['pc-level1-unaffordable.png','pc-level1-unaffordable-before.json','pc-level2.jpg','pc-level3.jpg','pc-level4.jpg','fixtures.json'],
 'opening-recognition':['solo.png','coop.png','solo-words.json','coop-words.json','solo-result.json','coop-result.json'],
 'recognition-real':['pc-round3.png','pc-level5.png','pc-level6.png','result-2048.json','pc-round3-result-2048.json','pc-level5-result-2048.json','pc-level6-result-2048.json'],
 'battle-recognition':['pc-round14.png','pc-round14-b.png','pc-round14-result.json']}

def hash_file(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def safe_source_files():
    files=[p for p in HERE.rglob('*') if p.is_file() and not any(x in ('build','__pycache__','.pytest_cache','dist','.git') for x in p.relative_to(HERE).parts)]
    files.extend(ROOT/name for name in DATABASES)
    files.extend(HERE/'build'/folder/name for folder,names in FIXTURES.items() for name in names)
    files.extend(p for p in (HERE/'build/battle-templates').rglob('*') if p.is_file())
    guide=ROOT/'outputs/strategy_library_2026-11-13/github-verified/garrison-strategy-guide'
    files.extend(p for p in guide.rglob('*') if p.is_file() and '.git' not in p.relative_to(guide).parts)
    for p in files:
        if not p.is_file():raise FileNotFoundError(p)
        if p.name in ('secrets.json','settings.json','session.json','.env') or p.suffix in ('.log','.pyc'):raise ValueError('Unexpected personal/runtime file: '+str(p))
    return sorted(set(files))

def zip_files(path,pairs):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for source,name in pairs:archive.write(source,str(name).replace('\\','/'))
    with zipfile.ZipFile(path) as archive:
        bad=archive.testzip()
        if bad:raise ValueError('Invalid ZIP entry: '+bad)

def main():
    verified=json.loads((RELEASE/'验证报告.json').read_text('utf8'))
    assert verified['version']==__version__ and verified['packaged_installation']['passed']
    OUT.mkdir(parents=True,exist_ok=True);CLEAN.mkdir(exist_ok=True)
    shutil.copy2(RELEASE/'卫戍协议助手.exe',CLEAN/'卫戍协议助手.exe')
    copied=[]
    for p in sorted((RELEASE/'_internal').rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(RELEASE/'_internal')
        if rel.as_posix() in UNUSED_DOCS:continue
        dest=CLEAN/'_internal'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);copied.append(rel.as_posix())
    for p in sorted((RELEASE/'第三方许可').rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(RELEASE/'第三方许可')
        if rel.parts[0] in DEV_LICENSES:continue
        dest=CLEAN/'第三方许可'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    notice=CLEAN/'第三方许可/素材来源.txt'
    notice.write_text('游戏图像与图标来自 PRTS Wiki，版权归鹰角网络及相关权利人。\n'
        'PRTS 资料文字依来源许可 CC BY-NC-SA 3.0 使用；来源地址及条目记录保留在数据库中。\n'
        '攻略作者、原始链接与引用范围保留在 _internal/assets/strategy 中。\n'
        'Qt/PySide6 等组件许可见本目录，动态库位于 _internal，可替换为兼容版本。\n'
        'PRTS：https://prts.wiki/\nCC BY-NC-SA 3.0：https://creativecommons.org/licenses/by-nc-sa/3.0/\n','utf8')
    assert {p.name for p in CLEAN.iterdir()}=={'卫戍协议助手.exe','_internal','第三方许可'}
    assert not any(p.name in ('验证报告.json','SHA256.json','使用说明.txt','更新记录.md','界面设计说明.md') for p in CLEAN.rglob('*'))
    files=safe_source_files()
    suspicious=[]
    credential=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|sk-(?:proj-)?[A-Za-z0-9_-]{35,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
    for p in files:
        if p.suffix in ('.py','.json','.md','.txt','.html','.ps1','.cjs','.mjs') and p.stat().st_size<3_000_000:
            for n,line in enumerate(p.read_text('utf8',errors='replace').splitlines(),1):
                if credential.search(line):suspicious.append({'file':p.relative_to(ROOT).as_posix(),'line':n})
    if suspicious:raise ValueError('Credential-pattern review required: '+json.dumps(suspicious))
    portable=OUT/f'GarrisonAssistant-{__version__}-Windows-x64.zip'
    full=OUT/f'GarrisonAssistant-{__version__}-CompleteSource.zip'
    zip_files(portable,((p,Path('卫戍协议助手')/p.relative_to(CLEAN)) for p in sorted(CLEAN.rglob('*')) if p.is_file()))
    zip_files(full,((p,p.relative_to(ROOT)) for p in files))
    manifest={'version':__version__,'portable_roots':sorted(p.name for p in CLEAN.iterdir()),
              'removed_runtime_docs':sorted(UNUSED_DOCS),'source_files':len(files),'credential_pattern_findings':suspicious,
              'archives':{p.name:{'bytes':p.stat().st_size,'sha256':hash_file(p)} for p in (portable,full)},
              'source_inventory':{p.relative_to(ROOT).as_posix():{'bytes':p.stat().st_size,'sha256':hash_file(p)} for p in files}}
    report=HERE/'build'/f'distribution-{__version__}.json';report.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({'portable':str(portable),'complete_source':str(full),'source_files':len(files),'archives':manifest['archives']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
