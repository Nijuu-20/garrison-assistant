"""Render the real-frame shop markers at multiple DPI scales; no live input."""
import os,json
from pathlib import Path
import cv2,numpy as np
from PIL import Image
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QImage,QPainter
from garrison import __version__
from garrison.core import Database
from garrison.hud import locate,price_badges
from garrison.tracking import shop_observations
from garrison.tracking_view import paint_matches,marker_rect,tracking_marker_pixmap

HERE=Path(__file__).parent;OUT=HERE/'build/tracking-marker';OUT.mkdir(parents=True,exist_ok=True)
app=QApplication([]);db=Database();checks=[]
def check(name,passed):
    checks.append({'test':name,'passed':bool(passed)})
    assert passed,name
sprite=tracking_marker_pixmap()
check('packaged asset has transparency',not sprite.isNull() and sprite.hasAlphaChannel())
raw=np.array(Image.open(HERE/'assets/tracking-emote.png').convert('RGBA'))
check('outer transparent padding is clean',not raw[:8,:,3].any() and not raw[-8:,:,3].any() and not raw[:,:8,3].any() and not raw[:,-8:,3].any())
for scene in ('pc-round3','pc-level5','pc-level6'):
    game=cv2.imdecode(np.fromfile(HERE/f'build/recognition-real/{scene}.png',np.uint8),cv2.IMREAD_COLOR)
    result=json.loads((HERE/f'build/recognition-real/{scene}-result-2048.json').read_text('utf8'))
    h,w=game.shape[:2]
    layout=locate(result['words'],price_badges(game),db,w/h)
    result.update(shop_slots=layout['slots'],regions=layout['regions'],layout_valid=layout['valid'])
    matches=shop_observations(db,result)
    check(scene+' offers available',len(matches)>=3)
    for dpr in (1,1.25,1.5,2):
        canvas=QImage(w,h,QImage.Format.Format_RGBA8888);canvas.fill(Qt.GlobalColor.transparent);canvas.setDevicePixelRatio(dpr)
        viewport=QRectF(0,0,w/dpr,h/dpr)
        painter=QPainter(canvas);paint_matches(painter,viewport,matches);painter.end()
        pixels=np.frombuffer(canvas.constBits(),np.uint8).reshape(h,canvas.bytesPerLine())[:,:w*4].reshape(h,w,4)
        allowed=np.zeros((h,w),bool)
        for item in matches:
            r=marker_rect(viewport,item)
            x,y,rw,rh=item['rect']
            card=QRectF(x*w/dpr,y*h/dpr,rw*w/dpr,rh*h/dpr)
            check(f'{scene} {dpr} slot {item["slot"]} stays in left emblem patch',card.contains(r) and r.right()<=card.x()+card.width()*.43 and r.top()>card.y()+card.height()*.20)
            left,top=max(0,int(r.left()*dpr)-1),max(0,int(r.top()*dpr)-1)
            right,bottom=min(w,int(r.right()*dpr)+2),min(h,int(r.bottom()*dpr)+2)
            allowed[top:bottom,left:right]=True
            check(f'{scene} {dpr} slot {item["slot"]} rendered',np.count_nonzero(pixels[top:bottom,left:right,3])>100)
        check(f'{scene} {dpr} no old frame or caption drawn',not pixels[:,:,3][~allowed].any())
        for region in layout['regions']:
            if region['key'].startswith(('shop:','offer:','cost:')):
                x,y,rw,rh=region['rect']
                check(f'{scene} {dpr} preserves {region["key"]}',not pixels[int(y*h):int((y+rh)*h),int(x*w):int((x+rw)*w),3].any())
        if dpr==1:
            rgb=cv2.cvtColor(game,cv2.COLOR_BGR2RGB)
            background=Image.fromarray(rgb).convert('RGBA')
            background.alpha_composite(Image.fromarray(pixels.copy()))
            background.save(OUT/f'{scene}-markers.png')
            first=next(m for m in matches if m['kind']=='operator')
            x,y,rw,rh=first['rect'];background.crop((int(x*w),int(y*h),int((x+rw)*w),int((y+rh)*h))).save(OUT/f'{scene}-card.png')
report={'version':__version__,'passed':all(c['passed'] for c in checks),'checks':checks,
        'scope':'Historical level 1, 5, 6 screenshots rendered with current marker at DPR 1, 1.25, 1.5, 2; no live desktop.'}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({'checks':len(checks),'passed':report['passed']}))
