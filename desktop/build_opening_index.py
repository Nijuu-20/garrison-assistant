"""Export verified PRTS originals from the local covenant database, offline.

Only four existing layout anchors come from screenshots. Covenant identity
matches use original transparent PNG bytes; no screen crop is a fallback.
"""
from pathlib import Path
import hashlib,json,sqlite3
import cv2,numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OUT=HERE/'assets/opening'
DATABASE=ROOT/'outputs/regulation_covenant_icons_2026-11-14/卫戍协议_规程_盟约图标数据库.sqlite'

def build():
    old=json.loads((OUT/'index.json').read_text('utf8'))
    anchors=[r for r in old['references'] if r['kind']=='anchor']
    assert len(anchors)==4
    con=sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
    try:
        records=con.execute('SELECT c.covenant_id,c.name,c.type,i.* FROM covenants c JOIN icons i USING(covenant_id) ORDER BY c.covenant_id').fetchall()
        sources=[dict(r) for r in con.execute('SELECT title,url,type,revision_id FROM sources')]
        meta=dict(con.execute('SELECT key,value FROM metadata'))
    finally:con.close()
    assert len(records)==26 and len({r['name'] for r in records})==26
    assert sum(r['type']=='核心盟约' for r in records)==10
    refs=[];(OUT/'prts').mkdir(exist_ok=True)
    for r in records:
        blob=r['image_png'];digest=hashlib.sha256(blob).hexdigest()
        assert digest==r['sha256'] and len(blob)==r['byte_size'],r['name']
        pic=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_UNCHANGED)
        assert pic is not None and pic.shape==(r['height'],r['width'],4) and pic[:,:,3].max()>0,r['name']
        filename='prts/'+r['covenant_id']+'.png';(OUT/filename).write_bytes(blob)
        refs.append({'file':filename,'name':r['name'],'kind':'core' if r['type']=='核心盟约' else 'additional',
                     'source':'PRTS','covenant_id':r['covenant_id'],'sha256':digest,'image_url':r['source_image_url'],
                     'file_title':r['file_title'],'collected_on':r['collected_on'],'size':[r['width'],r['height']]})
    for anchor in anchors:
        anchor=dict(anchor);anchor['source']='screenshot-layout-anchor'
        anchor['sha256']=hashlib.sha256((OUT/anchor['file']).read_bytes()).hexdigest();refs.append(anchor)
    data={'version':2,'reference_size':[2560,1440],'normalized_width':1280,'icon_sizes':[48,50,52],
          'references':refs,'source':'26 PRTS original alpha PNGs from local SQLite; four screenshot layout anchors only.',
          'database':DATABASE.relative_to(ROOT).as_posix(),
          'database_sha256':hashlib.sha256(DATABASE.read_bytes()).hexdigest(),
          'sources':sources,'database_metadata':meta,
          'identity_method':'alpha silhouette gradient magnitude; independent of lit/grey foreground polarity',
          'copyright':'图片来自 PRTS Wiki，游戏素材版权归鹰角网络及相关权利人。'}
    (OUT/'index.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf8')
    print('Exported 26 byte-identical PRTS covenant icons and 4 layout anchors.')

if __name__=='__main__':build()