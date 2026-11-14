"""Offline source provenance and perturbation/occlusion checks for PRTS icons."""
import hashlib,json,sqlite3
from pathlib import Path
import cv2,numpy as np
from garrison import __version__
from garrison.core import Database
from garrison.opening import OpeningRecognizer,snapshot_key
from garrison.opening_icons import asset_root

HERE=Path(__file__).resolve().parent;OUT=HERE/'build/opening-recognition'
index=json.loads((asset_root()/'index.json').read_text('utf8'))
source=HERE.parent/index['database'];source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
con=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
originals={name:blob for name,blob in con.execute('SELECT c.name,i.image_png FROM covenants c JOIN icons i USING(covenant_id)')};con.close()
checks=[];samples=[];r=OpeningRecognizer(Database())
def check(name,value):
    checks.append({'test':name,'passed':bool(value)})
    if not value:print('FAILED',name)

refs=[ref for ref in index['references'] if ref['kind']!='anchor']
check('all 26 identities come exclusively from local PRTS database',len(refs)==26 and {e['name'] for e in refs}==set(originals) and all(e['source']=='PRTS' for e in refs))
check('database provenance hash unchanged',source_hash==index['database_sha256'])
for ref in refs:
    blob=(asset_root()/ref['file']).read_bytes()
    check('byte-identical original / '+ref['name'],blob==originals[ref['name']] and hashlib.sha256(blob).hexdigest()==ref['sha256'])
check('runtime bundle contains no legacy covenant screen crops',not any((asset_root()/f'{prefix}-0.png').exists() for prefix in ('core','additional','solo')))
for scene in ('solo','coop'):
    frame=cv2.imdecode(np.fromfile(OUT/(scene+'.png'),np.uint8),1);base=r.recognize(frame)
    check(scene+' baseline has all 26 observed icons',base is not None and base['complete'] and len(base['icon_matches'])==26)
    samples_to_test=[('brightness70',cv2.convertScaleAbs(frame,alpha=.70)),('brightness85',cv2.convertScaleAbs(frame,alpha=.85)),
                     ('brightness110',cv2.convertScaleAbs(frame,alpha=1.10)),('brightness120',cv2.convertScaleAbs(frame,alpha=1.20)),
                     ('blur',cv2.GaussianBlur(frame,(3,3),.65)),
                     ('shift',cv2.warpAffine(frame,np.float32([[1,0,3],[0,1,-3]]),(frame.shape[1],frame.shape[0]))),
                     ('1600x900',cv2.resize(frame,(1600,900),interpolation=cv2.INTER_AREA)),
                     ('3840x2160',cv2.resize(frame,(3840,2160),interpolation=cv2.INTER_LINEAR))]
    jpeg=cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,85])[1]
    samples_to_test.append(('jpeg85',cv2.imdecode(jpeg,1)))
    for name,image in samples_to_test:
        result=r.recognize(image)
        valid=bool(result and result['complete'] and snapshot_key(result['opening'])==snapshot_key(base['opening']))
        check(scene+'/'+name+' exact identity, state and selection',valid)
        samples.append({'scene':scene,'transform':name,'passed':valid,'elapsed_ms':result['elapsed_ms'] if result else None,
                        'observed_icons':len(result['icon_matches']) if result else 0})
    # Every individual identity must disappear when its visual evidence is gone.
    # This also catches positional guesses or accidental fallback to old crops.
    for entry in base['icon_matches']:
        hidden=frame.copy();h,w=frame.shape[:2];x,y,rw,rh=entry['rect'];pad=7
        hidden[max(0,int(y*h)-pad):min(h,int((y+rh)*h)+pad),max(0,int(x*w)-pad):min(w,int((x+rw)*w)+pad)]=20
        result=r.recognize(hidden)
        check(scene+'/hidden '+entry['name']+' abstains',result and not result['complete'] and
              result['fields'][0]['value'] is None and entry['name'] not in {e['name'] for e in result['icon_matches']})
        if not checks[-1]['passed']:
            print('Unexpected',{'hidden':entry,'complete':result['complete'] if result else None,
                                'matches':[e for e in result['icon_matches'] if e['name']==entry['name']] if result else []})
check('source database is read-only during export and replay',hashlib.sha256(source.read_bytes()).hexdigest()==source_hash)
report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,'samples':samples,
        'templates':'26 byte-identical original PRTS alpha PNGs exported from the existing local covenant SQLite database',
        'database_sha256':source_hash,'limits':'Two historical PC screenshots and synthetic transformations/occlusions. Not independent live solo/co-op accuracy or animation validation.'}
(OUT/'prts-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({'passed':report['passed'],'checks':len(checks),'samples':samples},ensure_ascii=False))
raise SystemExit(0 if report['passed'] else 1)
