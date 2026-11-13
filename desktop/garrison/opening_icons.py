"""Image-only opening icons. No OCR and no operator portrait comparison."""
import hashlib,json,sys
from pathlib import Path
import cv2,numpy as np

def asset_root():
    return (Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'assets/opening'

def edges(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    gray=cv2.medianBlur(gray,3)
    # Continuous magnitude matches both white-on-grey and black-on-green,
    # without threshold edges appearing/disappearing when brightness changes.
    return cv2.magnitude(cv2.Sobel(gray,cv2.CV_32F,1,0),cv2.Sobel(gray,cv2.CV_32F,0,1))

class IconMatcher:
    def __init__(self):self.refs=None;self.review_refs=None
    def load(self,review=False):
        if (self.review_refs if review else self.refs) is not None:return
        data=json.loads((asset_root()/'index.json').read_text('utf8'));refs=[]
        if data.get('version')!=2:raise ValueError('开局盟约图标库需要更新为 PRTS 原图')
        for ref in data['references']:
            if review and ref['kind']=='anchor':continue
            blob=(asset_root()/ref['file']).read_bytes()
            if hashlib.sha256(blob).hexdigest()!=ref['sha256']:raise ValueError('开局图标文件校验失败：'+ref['name'])
            pic=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_UNCHANGED)
            if ref['kind']=='anchor':
                templates=(edges(cv2.resize(pic,None,fx=.5,fy=.5,interpolation=cv2.INTER_AREA)),)
            else:
                if ref.get('source')!='PRTS' or pic is None or pic.ndim!=3 or pic.shape[2]!=4:
                    raise ValueError('开局盟约需要 PRTS 透明原图：'+ref['name'])
                sizes=(40,44,48,50,52,56,60) if review else data['icon_sizes']
                templates=tuple(edges(cv2.resize(pic[:,:,3],(size,size),interpolation=cv2.INTER_AREA)) for size in sizes)
            refs.append((ref,templates))
        if review:self.review_refs=refs
        else:self.refs=refs

    def detect(self,frame,review=False):
        self.load(review);h,w=frame.shape[:2]
        if abs(w/h-16/9)>.12:return []
        image=cv2.resize(frame,(1280,round(h*1280/w)),interpolation=cv2.INTER_AREA);e=edges(image);height=e.shape[0]
        candidates=[];integrals={};valid_windows={}
        for ref,templates in (self.review_refs if review else self.refs):
            anchor=ref['kind']=='anchor'
            if review:box=(int(.02*1280),int(.08*height),int(.98*1280),height)
            elif anchor and ref['name']=='准备入口':box=(int(.79*1280),int(.82*height),int(.88*1280),height)
            elif anchor:box=(int(.05*1280),int(.16*height),int(.10*1280),height)
            else:box=(int(.06*1280),int(.22*height),int(.67*1280),height)
            x0,y0,x1,y1=box;area=e[y0:y1,x0:x1]
            if box not in integrals:integrals[box]=cv2.integral2(area,sdepth=cv2.CV_64F,sqdepth=cv2.CV_64F)
            for template in templates:
                if area.shape[0]<template.shape[0] or area.shape[1]<template.shape[1]:continue
                scores=cv2.matchTemplate(area,template,cv2.TM_CCOEFF_NORMED)
                th,tw=template.shape;key=(box,th,tw)
                if key not in valid_windows:
                    sums,squares=integrals[box]
                    total=sums[th:,tw:]-sums[:-th,tw:]-sums[th:,:-tw]+sums[:-th,:-tw]
                    total_sq=squares[th:,tw:]-squares[:-th,tw:]-squares[th:,:-tw]+squares[:-th,:-tw]
                    valid_windows[key]=total_sq-total*total/(th*tw)>1
                # Remove flat windows before peak selection; otherwise bogus
                # normalized peaks can consume the search budget and hide real
                # icons on large plain in-match information panels.
                scores[~valid_windows[key]]=-1
                for _ in range(2 if anchor else 4):
                    _,score,_,loc=cv2.minMaxLoc(scores)
                    if score<(.64 if anchor else .70):break
                    th,tw=template.shape;lx,ly=loc
                    scores[max(0,ly-th//2):ly+th//2,max(0,lx-tw//2):lx+tw//2]=-1
                    # Float32 integral normalization can produce high scores in
                    # flat patches. Recheck the actual pixels in float64 before
                    # accepting an identity, including fully occluded icons.
                    patch=area[ly:ly+th,lx:lx+tw].astype(np.float64)
                    target=template.astype(np.float64);patch-=patch.mean();target-=target.mean()
                    energy=float(np.sum(patch*patch)*np.sum(target*target))
                    score=float(np.sum(patch*target)/np.sqrt(energy)) if energy>1 else 0
                    if score<(.64 if anchor else .70):continue
                    cx=loc[0]+tw/2+x0;cy=loc[1]+th/2+y0
                    candidates.append({'name':ref['name'],'kind':ref['kind'],'similarity':round(score,4),'x':cx/1280,'y':cy/height,
                                       'rect':[(cx-tw/2)/1280,(cy-th/2)/height,tw/1280,th/height]})
        result=[];used=set()
        for candidate in sorted(candidates,key=lambda c:-c['similarity']):
            near=lambda c:abs(c['x']-candidate['x'])<.026 and abs(c['y']-candidate['y'])<.045
            if any(near(c) for c in result):continue
            rivals=[c['similarity'] for c in candidates if near(c) and c['name']!=candidate['name']]
            margin=candidate['similarity']-max(rivals,default=0)
            if margin<.075 or candidate['name'] in used:continue
            candidate['margin']=round(margin,4);used.add(candidate['name']);result.append(candidate)
        return result

def color_state(frame,entry):
    h,w=frame.shape[:2];x,y=entry['x']*w,entry['y']*h;radius=entry['rect'][2]*w*.42
    crop=frame[max(0,int(y-radius)):min(h,int(y+radius)),max(0,int(x-radius)):min(w,int(x+radius))]
    if not crop.size:return 'unknown'
    b,g,r=cv2.split(crop.astype(np.int16));green=(g>95)&(g>r*1.5)&(b>r*1.25)&(g>b*.8)
    neutral=(np.maximum.reduce([b,g,r])-np.minimum.reduce([b,g,r])<45)&(g>100)
    return 'lit' if green.mean()>.20 else 'grey' if green.mean()<.08 and neutral.mean()>.035 else 'unknown'
