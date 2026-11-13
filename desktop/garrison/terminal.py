"""Draw the default Stronghold terminal's rails, clipped frames and card slots.

Shapes are rendered at the current device scale; no screenshot is used as UI.
"""
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QLinearGradient
from PySide6.QtWidgets import QWidget, QFrame, QPushButton, QStyledItemDelegate, QStyle

INK = '#191d1e'
PANEL = '#242b2b'
TEAL = '#14dfbb'
GOLD = '#e7b936'
MUTED = '#8caaa8'
WHITE = '#e7f3ef'
TIER = {1:'#96aaa5', 2:'#a9d0bc', 3:'#65bda8', 4:'#63c3d0', 5:'#e5c64c', 6:'#eb9b42'}
ROMAN = ('', 'I', 'II', 'III', 'IV', 'V', 'VI')


def clipped(rect, cut=8):
    r=QRectF(rect); x,y,w,h=r.x(),r.y(),r.width(),r.height(); c=min(cut,w/3,h/3)
    path=QPainterPath(QPointF(x+c,y))
    for px,py in ((x+w-c,y),(x+w,y+c),(x+w,y+h-c),(x+w-c,y+h),(x+c,y+h),(x,y+h-c),(x,y+c)):
        path.lineTo(px,py)
    path.closeSubpath(); return path


def font(px=13, bold=False, numeric=False):
    f=QFont('Bahnschrift' if numeric else 'Microsoft YaHei UI')
    f.setPixelSize(px); f.setBold(bold); return f


def frame(p, rect, color='#3b6462', fill=PANEL, cut=7, inner=False):
    p.setPen(QPen(QColor(color),1));p.setBrush(QColor(fill));p.drawPath(clipped(rect,cut))
    if inner:
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#294e4c'),1))
        p.drawPath(clipped(QRectF(rect).adjusted(4,4,-4,-4),max(2,cut-2)))


class TerminalSurface(QWidget):
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor(INK))
        p.setPen(QColor('#1e2525'))
        for x in range(0,self.width(),64):p.drawLine(x,0,x,self.height())
        for y in range(0,self.height(),64):p.drawLine(0,y,self.width(),y)
        p.setPen(QColor('#283432'))
        for x in range(20,self.width(),120):
            for y in range(20,self.height(),120):
                p.drawLine(x-3,y,x+3,y);p.drawLine(x,y-3,x,y+3)


class TerminalPanel(QFrame):
    def __init__(self):
        super().__init__();self.setObjectName('terminalPanel')
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame(p,QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),inner=True)
        p.setPen(QPen(QColor(TEAL),2));p.drawLine(15,1,46,1)
        p.setPen(QPen(QColor('#49736e'),1));p.drawLine(self.width()-42,self.height()-5,self.width()-14,self.height()-5)


class TerminalButton(QPushButton):
    """Clipped command key; selected navigation uses the card-selection treatment."""
    def __init__(self,text):
        super().__init__(text);self.setMinimumHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r=QRectF(self.rect()).adjusted(1,1,-1,-1)
        nav=bool(self.property('nav'));primary=bool(self.property('primary'))
        active=self.isChecked();hover=self.underMouse();down=self.isDown()
        accent=GOLD if self.property('tone')=='gold' else ('#7bcce7' if self.property('tone')=='blue' else TEAL)
        bright=primary or active
        fill=accent if bright else ('#274442' if hover else '#1d2e30')
        edge=accent if hover or bright or self.hasFocus() else '#42635f'
        if down:fill='#419b8c' if bright else '#30554f'
        if not self.isEnabled():fill='#1b2528';edge='#30413f'
        frame(p,r,edge,fill,0 if primary else (6 if nav else 4))
        if not bright:
            p.setPen(QColor('#29433f'));p.drawLine(8,self.height()-5,self.width()-9,self.height()-5)
        p.setFont(font(13,bright));p.setPen(QColor(INK if bright else (WHITE if self.isEnabled() else '#64807c')))
        dy=1 if down else 0
        if nav:
            number,_,title=self.text().partition('   ')
            p.setFont(font(12,True,True));p.drawText(QRectF(11,dy,27,self.height()),Qt.AlignmentFlag.AlignCenter,number)
            p.setPen(QColor('#35645b' if bright else '#3b5b57'));p.drawLine(43,10,43,self.height()-10)
            p.setPen(QColor(INK if bright else WHITE));p.setFont(font(14,active))
            p.drawText(QRectF(53,dy,self.width()-63,self.height()),Qt.AlignmentFlag.AlignVCenter,title)
        else:
            p.drawText(r.translated(0,dy),Qt.AlignmentFlag.AlignCenter,self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(WHITE),1,Qt.PenStyle.DotLine));p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(clipped(r.adjusted(3,3,-3,-3),3))


class HudRail(QWidget):
    def __init__(self,compact=False):
        super().__init__();self.compact=compact;self.state={};self.setFixedHeight(84 if compact else 104)
        self.setAccessibleName('对局状态：回合、阶段和资金')
    def set_state(self,state):self.state=state;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w=self.width();h=self.height();compact=self.compact;s=self.state
        # A continuous rail connects counters to the elevated, double-cut phase plate.
        p.setPen(QColor('#35534f'));p.drawLine(8,h//2,w-8,h//2)
        cwidth=112 if compact else 198;cx=(w-cwidth)/2
        frame(p,QRectF(3,18,w-6,h-27),'#3b5653','#152023',3)
        frame(p,QRectF(cx,5,cwidth,h-12),TEAL,'#203b39',12,True)
        p.setPen(QColor(MUTED));p.setFont(font(9 if compact else 10,False,True))
        p.drawText(QRectF(cx,12,cwidth,15),Qt.AlignmentFlag.AlignCenter,'阶段 / PHASE' if compact else 'STRONGHOLD PROTOCOL')
        p.setPen(QColor(TEAL));p.setFont(font(20 if compact else 28,True))
        p.drawText(QRectF(cx,27,cwidth,34),Qt.AlignmentFlag.AlignCenter,s.get('phase') or '等待连接')
        if not compact:
            p.setFont(font(11));p.setPen(QColor('#a2c6ba'))
            p.drawText(QRectF(cx,65,cwidth,19),Qt.AlignmentFlag.AlignCenter,'卫戍协议 · 规程')
        for x,width,key,title,color in [(12,cx-22,'round','当前回合 / ROUND',TEAL),(cx+cwidth+10,w-cx-cwidth-22,'gold','可用资金 / CREDIT',GOLD)]:
            p.setFont(font(10,False,True));p.setPen(QColor(MUTED))
            p.drawText(QRectF(x,24,width,16),Qt.AlignmentFlag.AlignCenter,title)
            value='—' if s.get(key) is None else str(s[key]).zfill(2)
            p.setFont(font(29 if compact else 39,True,True));p.setPen(QColor(color))
            p.drawText(QRectF(x,40,width,h-42),Qt.AlignmentFlag.AlignCenter,value)
        # Small index ticks, as on the terminal's counter frames.
        p.setPen(QColor('#54877b'))
        for y in range(27,h-10,6):p.drawLine(5,y,8,y);p.drawLine(w-8,y,w-5,y)


class CovenantStrip(QWidget):
    activated = None
    def __init__(self):
        super().__init__();self.entries=[];self.setFixedHeight(82)
        self.setAccessibleName('盟约激活与计数')
    def set_entries(self,entries):self.entries=entries;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.entries:
            p.setPen(QColor(MUTED));p.setFont(font(12))
            p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'盟约容器  /  录入阵容后显示激活状态与计数');return
        step=min(105,self.width()/len(self.entries));start=(self.width()-step*len(self.entries))/2
        for i,c in enumerate(self.entries):
            x=start+i*step+step/2;active=c['active'];color=TEAL if active else '#5a7470';r=QRectF(x-21,2,42,42)
            p.setBrush(QColor('#123b32' if active else '#1b2729'));p.setPen(QPen(QColor('#35534d'),2));p.drawEllipse(r)
            p.setPen(QPen(QColor(color),3));span=min(1,c['effective']/max(1,c['activation_count']))
            p.drawArc(r,90*16,-round(360*16*span));p.setPen(QPen(QColor(color),1));p.drawEllipse(r.adjusted(6,6,-6,-6))
            p.setPen(QColor(color));p.setFont(font(15,True));p.drawText(r,Qt.AlignmentFlag.AlignCenter,str(c['effective']))
            p.setFont(font(11,active));p.setPen(QColor(WHITE if active else MUTED))
            p.drawText(QRectF(x-step/2,47,step,16),Qt.AlignmentFlag.AlignCenter,c['name'])
            p.setFont(font(9));p.setPen(QColor(color))
            p.drawText(QRectF(x-step/2,64,step,14),Qt.AlignmentFlag.AlignCenter,'已激活' if active else f'需要 {c["activation_count"]} 名')


class OperatorDelegate(QStyledItemDelegate):
    """Four-column roster slots with separate tier, funds, portrait and covenant zones."""
    def sizeHint(self,option,index):
        size=self.parent().gridSize()
        return size if size.isValid() else QSize(108,138)
    def paint(self,p,opt,index):
        data=index.data(Qt.ItemDataRole.UserRole+1)
        if not data:return super().paint(p,opt,index)
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        selected=bool(opt.state & QStyle.StateFlag.State_Selected);hover=bool(opt.state & QStyle.StateFlag.State_MouseOver)
        r=QRectF(opt.rect).adjusted(3,9,-3,-2);color=TIER.get(data['tier'],TEAL)
        frame(p,r,TEAL if selected else (WHITE if hover else color),'#162225',4)
        # Portrait is dominant; the base gradient leaves readable, fixed text bands.
        icon=index.data(Qt.ItemDataRole.DecorationRole)
        portrait=QRectF(r.x()+4,r.y()+12,r.width()-8,r.height()-51)
        if icon:
            size=min(portrait.width(),portrait.height());pix=icon.pixmap(QSize(round(size*2),round(size*2)))
            p.drawPixmap(QRectF(portrait.center().x()-size/2,portrait.y(),size,size),pix,QRectF(pix.rect()))
        grad=QLinearGradient(0,r.bottom()-66,0,r.bottom());grad.setColorAt(0,QColor('#00162225'));grad.setColorAt(1,QColor('#12d5b2' if selected else '#182a2a'))
        p.fillRect(QRectF(r.x()+1,r.bottom()-68,r.width()-2,66),grad)
        p.setPen(QColor(color));p.setFont(font(13,True,True));p.drawText(QRectF(r.x()+6,r.y()+3,26,19),Qt.AlignmentFlag.AlignLeft,ROMAN[data['tier']])
        p.setFont(font(12,True));p.setPen(QColor(INK if selected else WHITE))
        name=p.fontMetrics().elidedText(data['name'],Qt.TextElideMode.ElideRight,int(r.width()-10))
        p.drawText(QRectF(r.x()+5,r.bottom()-44,r.width()-10,20),Qt.AlignmentFlag.AlignCenter,name)
        p.setFont(font(10));p.setPen(QColor('#14463b' if selected else '#9db4aa'))
        text=p.fontMetrics().elidedText(' · '.join(data['covenants']),Qt.TextElideMode.ElideRight,int(r.width()-10))
        p.drawText(QRectF(r.x()+5,r.bottom()-24,r.width()-10,18),Qt.AlignmentFlag.AlignCenter,text)
        p.fillRect(QRectF(r.x()+3,r.bottom()-3,r.width()-6,2),QColor(TEAL if selected else color))
        if selected:
            p.setPen(QPen(QColor(TEAL),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(clipped(r.adjusted(3,3,-3,-3),3))
        # The badge sits in a break in both outlines. Draw it after focus/selection
        # so a selected slot never places a frame stroke across the price glyph.
        badge=QRectF(r.center().x()-20,r.y()-8,40,18)
        p.fillRect(badge.adjusted(-3,-2,3,2),QColor('#132023'))
        frame(p,badge,GOLD,'#202a24',8)
        p.setPen(QColor(GOLD));p.setFont(font(11,True,True));p.drawText(badge,Qt.AlignmentFlag.AlignCenter,'◆ '+str(data['cost']))
        p.restore()


class RecommendationSlot(QWidget):
    def __init__(self):
        super().__init__();self.data=None;self.pixmap=None;self.empty_text='等待局面信息';self.setMinimumSize(96,146)
        self.setAccessibleName('补强候选')
    def set_recommendation(self,data,pixmap=None):
        self.data=data;self.pixmap=pixmap
        self.setToolTip((data['name']+' / '+' / '.join(data['reasons'])) if data else '连接游戏或录入阵容后显示补强候选')
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);r=QRectF(self.rect()).adjusted(2,10,-2,-2)
        frame(p,r,TIER.get(self.data.get('tier'),TEAL) if self.data else '#426b62',PANEL,4)
        if not self.data:
            p.setPen(QColor('#40635a'));p.setFont(font(28,False,True));p.drawText(QRectF(0,25,self.width(),45),Qt.AlignmentFlag.AlignCenter,'+')
            p.setFont(font(12));p.setPen(QColor(MUTED));p.drawText(QRectF(0,78,self.width(),30),Qt.AlignmentFlag.AlignCenter,self.empty_text);return
        d=self.data
        badge=QRectF(r.center().x()-25,2,50,20);frame(p,badge,GOLD,'#283025',8)
        price=('◆ ' if d.get('cost_confirmed') else '≈ ')+str(d['cost'])
        p.setPen(QColor(GOLD));p.setFont(font(12,True,True));p.drawText(badge,Qt.AlignmentFlag.AlignCenter,price)
        p.setPen(QColor(TIER.get(d.get('tier'),TEAL)));p.setFont(font(12,True,True))
        p.drawText(QRectF(8,18,25,18),Qt.AlignmentFlag.AlignLeft,ROMAN[d.get('tier',1)])
        size=min(80,self.width()-20)
        if self.pixmap and not self.pixmap.isNull():p.drawPixmap(round((self.width()-size)/2),28,size,size,self.pixmap)
        p.setPen(QColor(WHITE));p.setFont(font(13,True));name=p.fontMetrics().elidedText(d['name'],Qt.TextElideMode.ElideRight,self.width()-14)
        p.drawText(QRectF(7,self.height()-48,self.width()-14,21),Qt.AlignmentFlag.AlignCenter,name)
        p.setPen(QColor('#a0b7aa'));p.setFont(font(10))
        reason=p.fontMetrics().elidedText(d['reasons'][0],Qt.TextElideMode.ElideRight,self.width()-14)
        p.drawText(QRectF(7,self.height()-27,self.width()-14,18),Qt.AlignmentFlag.AlignCenter,reason)
        p.fillRect(QRectF(7,self.height()-6,self.width()-14,2),QColor(TIER.get(d.get('tier'),TEAL)))
