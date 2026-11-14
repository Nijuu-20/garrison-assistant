"""Locate the PC HUD from this frame's anchors, never from a cached shop grid.

Coordinates are normalized. Colour proposes price badges; text and geometry
must agree before a proposal becomes a reading region.
"""
from __future__ import annotations
import cv2
import numpy as np
from functools import lru_cache
from pathlib import Path
import sys


@lru_cache(maxsize=1)
def level_capsule_template():
    root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    path=root/'assets/hud/level-capsule.png'
    if not path.is_file():return None
    image=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_GRAYSCALE)
    return cv2.resize(image,(96,32)) if image is not None else None


def is_level_capsule(crop):
    """Verify both the capsule silhouette and its interior LEVEL glyphs."""
    template=level_capsule_template()
    if template is None or not crop.size:return False
    sample=cv2.resize(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(96,32))
    whole=float(cv2.matchTemplate(sample,template,cv2.TM_CCOEFF_NORMED)[0,0])
    # At 720p the capsule is only ~13 pixels tall. Permit a small alignment
    # shift inside the contour, but still require the actual interior glyphs.
    inside=float(cv2.matchTemplate(sample[3:28,10:86],template[7:23,16:80],cv2.TM_CCOEFF_NORMED).max())
    return whole>=.92 and inside>=.84


def roman_ink(crop):
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    _,ink=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    return cv2.resize(ink,(96,72),interpolation=cv2.INTER_AREA)


@lru_cache(maxsize=1)
def roman_templates():
    root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    result={}
    for level in range(1,6):
        path=root/f'assets/hud/roman-{level}.png'
        if not path.is_file():continue
        crop=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
        if crop is not None:result[level]=roman_ink(crop)
    return result


def roman_image(crop):
    """Corroborate OCR against all five non-maximal Roman shapes."""
    if not crop.size or len(roman_templates())!=5:return None
    sample=roman_ink(crop)
    if sample.std()<10:return None
    sample=cv2.copyMakeBorder(sample,4,4,4,4,cv2.BORDER_CONSTANT)
    scores=sorted([(float(cv2.matchTemplate(sample,t,cv2.TM_CCOEFF_NORMED).max()),level) for level,t in roman_templates().items()],reverse=True)
    return scores[0][1] if scores[0][0]>=.90 and scores[0][0]-scores[1][0]>=.08 else None


def rect(x, y, w, h):
    x2, y2 = min(1., x+w), min(1., y+h)
    x, y = max(0., x), max(0., y)
    return [x, y, max(0., x2-x), max(0., y2-y)]


def price_badges(frame):
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([15, 105, 135]), np.array([42, 255, 255]))
    mask[:int(h*.55)] = 0
    # Small antialiased badge outlines need at least a 3 px close at 720p.
    k = max(3, round(h/384))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    badges = []
    for contour in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, bw, bh = cv2.boundingRect(contour)
        fill = cv2.contourArea(contour)/(bw*bh)
        if .018*h <= bh <= .055*h and .012*w <= bw <= .13*w and .7 <= bw/bh <= 4.5 and fill >= .54:
            badges.append([x/w, y/h, bw/w, bh/h])
    # Unaffordable cards use a silver ring instead of yellow. Restrict this
    # second proposal pass to the row of an already found funds/price anchor.
    anchors=[b for b in badges if b[1]>.65]
    if anchors:
        row=float(np.median([b[1] for b in anchors]));gray=cv2.inRange(hsv,np.array([0,0,135]),np.array([179,65,255]))
        gray[:max(0,int((row-.025)*h))]=0;gray[min(h,int((row+.07)*h)):]=0
        gray=cv2.morphologyEx(gray,cv2.MORPH_CLOSE,np.ones((k,k),np.uint8))
        for contour in cv2.findContours(gray,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh=cv2.boundingRect(contour);fill=cv2.contourArea(contour)/(bw*bh)
            if .018*h<=bh<=.050*h and .012*w<=bw<=.04*w and .85<bw/bh<1.8 and fill>.58 and abs(y/h-row)<.025:
                b=[x/w,y/h,bw/w,bh/h]
                if not any(abs(x/w-a[0])<.015 and abs(y/h-a[1])<.02 for a in badges):badges.append(b)
    return sorted(badges, key=lambda b:b[0])


def refine_refresh(frame, regions):
    """The refresh medal touches its button; locate its dark oval interior.

    Text anchors supply the search area. A closed interior is required, so a
    button label, shadow or an arbitrary dark patch cannot become the medal.
    """
    h,w=frame.shape[:2]
    for region in regions:
        if region['key']!='refresh_cost':continue
        x,y,rw,rh=region['rect'];cx=x+rw/2;cy=y+rh/2
        x1=max(0,int((x-.025)*w));x2=min(w,int((x+rw+.035)*w))
        y1=max(0,int((y-.02)*h));y2=min(h,int((y+rh+.02)*h))
        crop=frame[y1:y2,x1:x2]
        if not crop.size:continue
        dark=cv2.inRange(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV),np.array([0,0,0]),np.array([179,255,85]))
        candidates=[]
        for c in cv2.findContours(dark,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            bx,by,bw,bh=cv2.boundingRect(c)
            if bx<=0 or by<=0 or bx+bw>=crop.shape[1] or by+bh>=crop.shape[0]:continue
            fill=cv2.contourArea(c)/(bw*bh)
            if 1.05<bw/bh<1.8 and .018*h<bh<.04*h and .56<fill<.88:
                distance=abs((bx+x1+bw/2)/w-cx)+abs((by+y1+bh/2)/h-cy)
                candidates.append((distance,[((bx+x1)+bw*.12)/w,((by+y1)-bh*.12)/h,bw*.76/w,bh*1.24/h]))
        if candidates:
            distance,box=min(candidates,key=lambda a:a[0])
            if distance<.025:region['rect']=rect(*box)


def level_label_candidates(frame, words):
    """Propose the small LEVEL capsule above this frame's upgrade button.

    Geometry only proposes crops; the recognizer must verify the label image
    or LEVEL in two enlarged views. No level value or cached position is used.
    """
    upgrades=[a for a in words if a['text'].strip()=='升级' and a['y']>.55 and a['confidence']>=.9]
    if len(upgrades)!=1:return []
    x,y,bw,bh=upgrades[0]['rect'];height,width=frame.shape[:2]
    x1=max(0,int((x-bw*.7)*width));x2=min(width,int((x+bw*1.7)*width))
    y1=max(0,int((y-bh*5)*height));y2=min(height,int((y-bh*1.2)*height))
    if x2<=x1 or y2<=y1:return []
    gray=cv2.cvtColor(frame[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY)
    found=[]
    for threshold in (45,65,85):
        mask=cv2.inRange(gray,0,threshold)
        for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            px,py,pw,ph=cv2.boundingRect(c)
            cx=(x1+px+pw/2)/width
            if not (2.4<pw/ph<4.8 and .55*bw*width<pw<1.6*bw*width and .25*bh*height<ph<.95*bh*height):continue
            if abs(cx-(x+bw/2))>bw*.25 or cv2.contourArea(c)/(pw*ph)<.55:continue
            box=[(x1+px)/width,(y1+py)/height,pw/width,ph/height]
            if any(abs(box[0]-b[0])<.004 and abs(box[1]-b[1])<.004 for b in found):continue
            found.append(box)
    return found[:3]


def refine_upgrade_cost(frame, regions, words, badges):
    """Recover a silver cost medal only beside a verified LEVEL anchor.

    The funds/card row bounds the search. Dark interior geometry proposes a
    crop; numeric multi-view voting remains responsible for reading its cost.
    """
    if any(r['key']=='upgrade_cost' for r in regions):return
    levels=[a for a in words if a['text'].strip().upper()=='LEVEL' and a['y']>.55 and a['confidence']>=.9]
    anchors=[b for b in badges if b[1]>.65]
    if len(levels)!=1 or not anchors:return
    level=levels[0];cx=level['x'];row=float(np.median([b[1] for b in anchors]))
    if not .015<level['rect'][1]-row<.13:return
    h,w=frame.shape[:2]
    x1=max(0,int((cx-.035)*w));x2=min(w,int((cx+.035)*w))
    y1=max(0,int((row-.015)*h));y2=min(h,int((row+.065)*h))
    if x2<=x1 or y2<=y1:return
    gray=cv2.cvtColor(frame[y1:y2,x1:x2],cv2.COLOR_BGR2GRAY)
    proposals=[]
    for threshold in (60,75,90,100,110):
        mask=cv2.inRange(gray,0,threshold)
        mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((max(2,round(h/480)),)*2,np.uint8))
        for c in cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]:
            x,y,bw,bh=cv2.boundingRect(c);px=(x+x1+bw/2)/w;py=(y+y1+bh/2)/h
            if x<=0 or y<=0 or x+bw>=gray.shape[1] or y+bh>=gray.shape[0]:continue
            if not (.012*h<bh<.045*h and 1.05<bw/bh<2.05 and cv2.contourArea(c)/(bw*bh)>.43):continue
            if abs(px-cx)>.009 or not row<py<row+.04:continue
            proposals.append((abs(px-cx)+abs(py-(row+.018)),rect((x1+x-bw*.06)/w,(y1+y-bh*.1)/h,bw*1.12/w,bh*1.2/h)))
    if proposals:regions.append({'key':'upgrade_cost','rect':min(proposals,key=lambda a:a[0])[1]})


def locate(words, badges, db, aspect=16/9):
    """Return per-frame regions, including unreadable visible shop slots.

    Card count, card spacing, equipment position and LEVEL position may change
    independently. No operator identity or slot count is inferred from level.
    """
    regions = []; notes = []
    def anchor(predicate):
        choices = [a for a in words if a['confidence'] >= .8 and predicate(a)]
        return max(choices, key=lambda a:a['confidence'], default=None)
    def add(key, box, **extra):
        regions.append({'key':key, 'rect':rect(*box), **extra})
    round_word = anchor(lambda a:'回合' in a['text'] and a['y'] < .22 and '等级' not in a['text'])
    level_word = anchor(lambda a:a['text'].upper().strip() == 'LEVEL' and a['y'] > .55)
    upgrade = anchor(lambda a:a['text'].strip() == '升级' and a['y'] > .55)
    maximum = anchor(lambda a:a['text'].strip() == '已满级' and a['y'] > .55)
    refresh = anchor(lambda a:a['text'].strip() == '刷新' and a['y'] > .5)
    if not round_word or not (level_word or upgrade or maximum) or not refresh:
        return {'regions':[], 'valid':False, 'notes':['未定位到完整商店界面；请展开商店并避免遮挡。'], 'slots':[]}
    x,y,bw,bh = round_word['rect']
    # Keep the explicit label for combined OCR boxes; otherwise isolate its right neighbour.
    if any(c.isdigit() for c in round_word['text']):
        add('round', [x,y,bw,bh], seed=round_word)
    else:
        add('round', [x+bw+bh/aspect*.12, y-bh*.08, bh/aspect*1.85, bh*1.16])
    stages = [a for a in words if a['y'] < .2 and any(s in a['text'] for s in ('休息','休整','整备','招募干员','作战阶段','战斗进行','战斗中','模拟结束','作战失败','行动结束'))]
    if len(stages) == 1: add('phase', stages[0]['rect'], seed=stages[0])
    else: add('phase', [.3,0,.4,.1])
    if maximum:
        x,y,bw,bh=maximum['rect'];cx=x+bw/2
        add('level',maximum['rect'],seed=maximum)
        notes.append('已满级，无升级费用。')
    elif level_word:
        x,y,bw,bh = level_word['rect']; cx=x+bw/2
        # The level is BELOW LEVEL, never the top-left "规程等级".
        add('level', [cx-bw*.5,y+bh,bw,bh*2.6], roman=True)
    else:
        notes.append('未找到 LEVEL 标记，调度等级待确认。')
        x,y,bw,bh=upgrade['rect'];cx=x+bw/2
        add('level', [cx-bw*.45,y-bh*2.8,bw*.9,bh*1.6], unavailable=True)
    level_center = cx
    round_badges = [b for b in badges if b[2]*aspect/b[3] < 2.1]
    nearby = [b for b in round_badges if abs(b[0]+b[2]/2-level_center) < .035 and b[1] < y and y-b[1] < .23]
    upgrade_badge = None if maximum else min(nearby,key=lambda b:abs(b[0]+b[2]/2-level_center)+abs(y-b[1]), default=None)
    def digit_box(b):
        bx,by,bw,bh=b
        return [bx+bw*.16,by+bh*.04,bw*.68,bh*.92]
    if upgrade_badge: add('upgrade_cost',digit_box(upgrade_badge))
    elif not maximum: notes.append('升级费用标记未定位。')
    x,y,bw,bh = refresh['rect']
    # The cost medal is centred above the refresh button, left of the text centre.
    add('refresh_cost', [x-bh/aspect*.45,y-bh*.85,bh/aspect*.95,bh*.90],medal=True)
    # Wide money badges must be adjacent to the shop row, not a top HUD counter.
    wide = [b for b in badges if b[2]*aspect/b[3] > 2.5 and b[1] > .65]
    money = max(wide,key=lambda b:b[0],default=None)
    if money:
        bx,by,bw,bh=money
        add('gold',[bx+bw*.43,by-bh*.02,bw*.45,bh*1.04])
    else:
        notes.append('资金标记未定位，保留待确认。')
        add('gold',[0,0,0,0],unavailable=True)
    # Shop badges form one row close to the upgrade/funds badge. Row detection
    # does not assume 4 cards or a fixed left edge, even when LEVEL shifts.
    row_y = (upgrade_badge or money or [0,.76])[1]
    cards = [b for b in round_badges if abs(b[1]-row_y) < .025 and b is not upgrade_badge]
    if money: cards = [b for b in cards if b[0] < money[0]]
    if upgrade_badge: cards = [b for b in cards if b[0] > upgrade_badge[0]+upgrade_badge[2]]
    candidates=[]
    for a in words:
        name=a['text'].strip()
        if a['y'] > row_y+.09 and (name in db.by_name or name in db.equipment):
            candidates.append(a)
    slots=[];used=[]
    for i,b in enumerate(cards):
        cx=b[0]+b[2]/2
        # Determine each cell from adjacent price markers; this follows both
        # expanded shops and equipment/operator reorderings.
        distances=[abs(cx-(c[0]+c[2]/2)) for c in cards if c is not b]
        pitch=min(distances, default=.11)
        left=cx-pitch*.72;right=cx+pitch*.26
        matches=[a for a in candidates if left <= a['x'] <= right]
        name_word=max(matches,key=lambda a:a['y'],default=None)
        if name_word:used.append(name_word)
        equipment=bool(name_word and name_word['text'].strip() in db.equipment)
        key=f'item:{i}' if not name_word else f'offer:{i}' if equipment else f'shop:{i}'
        if name_word:
            nx,ny,nw,nh=name_word['rect']
            add(key,[nx-nh*.04,ny-nh*.05,nw+nh*.08,nh*1.1], seed=name_word, offer=True)
        else:
            # Failed global OCR does not establish that the card is equipment.
            # Follow neighbouring name plates and retry both identity pools.
            name_y=float(np.median([a['rect'][1] for a in candidates])) if candidates else min(.94,row_y+.18)
            name_h=float(np.median([a['rect'][3] for a in candidates])) if candidates else .025
            add(key,[left+pitch*.13,name_y-name_h*.14,pitch*.82,name_h*1.3],offer=True)
        add(f'cost:{i}',digit_box(b))
        bottom=(ny+nh+.02) if name_word else min(1,row_y+.24)
        slots.append({'slot':i,'key':key,'kind':'equipment' if equipment else 'operator' if name_word else 'unknown',
                      'rect':rect(left,row_y-.008,right-left,bottom-row_y+.008)})
    grid_valid=bool(cards) and len({id(a) for a in used})==len(used)
    if any(a not in used for a in candidates):grid_valid=False
    if len(cards)>2:
        gaps=np.diff([b[0]+b[2]/2 for b in cards])
        if max(gaps)>min(gaps)*1.45:grid_valid=False
    shop_valid=grid_valid and len(used)==len(cards)
    if not shop_valid:notes.append('商品或费用标记不完整，暂不替换商店。')
    return {'regions':regions,'valid':True,'notes':notes,'slots':slots,'shop_valid':shop_valid,'grid_valid':grid_valid}


def roman_bars(crop):
    """Conservative I/II/III shape check, only inside a LEVEL-anchored region.

    Score is a geometry score, not an OCR probability. Other Roman levels are
    handled by text recognition. Reject frames, symbols and clipped strokes.
    """
    if crop.size == 0: return None
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY);h,w=gray.shape
    if gray.max()-gray.min()<65:return None
    _,mask=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((max(1,h//15),1),np.uint8))
    _,_,stats,_=cv2.connectedComponentsWithStats(mask)
    bars=[]
    for x,y,bw,bh,area in stats[1:]:
        if area < h*w*.02:continue
        if x == 0 or y == 0 or x+bw >= w or y+bh >= h:
            if area > h*w*.1:return None
            continue
        # The CRT gradient can fade the bottom half of I/II/III; the dark
        # connected portion then has a wider aspect than the full stroke.
        if not (.34*h<bh<.85*h and .13< bw/bh <.62 and area/(bw*bh)>.72):return None
        bars.append((x,y,bw,bh))
    if not 1<=len(bars)<=3:return None
    if max(b[1] for b in bars)-min(b[1] for b in bars)>h*.1:return None
    if max(b[3] for b in bars)-min(b[3] for b in bars)>h*.12:return None
    center=(min(b[0] for b in bars)+max(b[0]+b[2] for b in bars))/2
    if abs(center-w/2)>w*.18:return None
    return len(bars)
