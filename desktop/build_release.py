"""Reproducible portable Windows build. Keeps original databases untouched."""
from pathlib import Path
import importlib.metadata
import json
import shutil
import subprocess
import sys
from garrison import __version__

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
OUT=ROOT/'outputs'/f'desktop_{__version__}';WORK=HERE/'build'/'pyinstaller'
OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
args=[sys.executable,'-m','PyInstaller','--clean','--noconfirm','--windowed','--onedir','--name','卫戍协议助手',
      '--distpath',str(OUT),'--workpath',str(WORK),'--specpath',str(HERE/'build'),
      '--icon',str(HERE/'assets'/'garrison.ico'),
      '--collect-all','rapidocr','--collect-all','onnxruntime','--collect-all','windows_capture','--collect-data','pypinyin',
      '--exclude-module','PySide6.QtWebEngineCore','--exclude-module','PySide6.QtWebEngineWidgets',
      '--exclude-module','PySide6.QtPdf','--exclude-module','tkinter',
      '--add-data',str(HERE/'assets'/'garrison-icon.png')+';assets',
      '--add-data',str(HERE/'assets'/'battle-index.npz')+';assets',
      '--add-data',str(HERE/'assets'/'battle-index.json')+';assets']
args+=['--add-data',str(HERE/'assets'/'opening')+';assets/opening']
args+=['--add-data',str(HERE/'assets'/'strategy')+';assets/strategy']
for path in [ROOT/'outputs'/'regulation_2026-11-13'/'卫戍协议_规程数据库.json',
             ROOT/'outputs'/'regulation_image_databases_2026-11-13'/'卫戍协议_规程_头像数据库.sqlite',
             ROOT/'outputs'/'regulation_image_databases_2026-11-13'/'卫戍协议_规程_精一立绘数据库.sqlite']:
    args+=['--add-data',str(path)+';resources']
args.append(str(HERE/'app.py'))
subprocess.run(args,check=True,cwd=HERE)
release=OUT/'卫戍协议助手'
# PyInstaller can discover an unrelated ICU from the host PATH. Qt's Windows
# wheel uses the OS ICU API (unsuffixed exports), not that private ICU build.
internal=release/'_internal'
for name in ('icuuc.dll','icudt78.dll'):
    candidate=internal/name
    if candidate.is_file():candidate.unlink()
import PySide6
for runtime in Path(PySide6.__file__).parent.glob('*140*.dll'):
    shutil.copy2(runtime,internal/runtime.name)
shutil.copy2(HERE/'使用说明.txt',release/'使用说明.txt')
shutil.copy2(HERE/'CHANGELOG.md',release/'更新记录.md')
shutil.copy2(HERE/'assets'/'garrison-icon.png',release/'应用图标.png')
shutil.copy2(HERE/'DESIGN.md',release/'界面设计说明.md')
licenses=release/'第三方许可';licenses.mkdir(exist_ok=True)
for dist in importlib.metadata.distributions():
    for f in dist.files or []:
        if '.dist-info/licenses/' in str(f).replace('\\','/'):
            source=Path(dist.locate_file(f))
            if source.is_file():
                dest=licenses/dist.metadata['Name']/Path(str(f).split('licenses',1)[1].lstrip('/\\'))
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
print(json.dumps({'release':str(release)},ensure_ascii=False))
