"""Watch-list controls and a mouse-transparent shop highlight surface."""
from PySide6.QtCore import Qt,QRectF,QTimer,QEvent
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QWidget,QVBoxLayout,QDialog,QLineEdit,QTabWidget,QListWidget,QListWidgetItem,QSizePolicy
from .widgets import FlowLayout,label,button,row,scroll
from .tracking import item_key


class TrackingChoices(QWidget):
    def __init__(self,toggle,pinned=False,manual=None):
        super().__init__();self.toggle=toggle;self.pinned=pinned;self.signature=None;self.buttons={}
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit_rows)
        layout=QVBoxLayout(self);layout.setContentsMargins(10,6,10,6);layout.setSpacing(5)
        self.title=label('已追踪 · 点击取消' if pinned else '阵容 / 装备推荐名单','accent')
        head=row(self.title);head.layout().addStretch()
        if manual:
            b=button('手动选择',manual);b.setFixedHeight(28);b.setStyleSheet('padding: 2px 8px;');head.layout().addWidget(b)
        layout.addWidget(head)
        self.body=QWidget();self.flow=FlowLayout(self.body);self.flow.setSpacing(5)
        self.area=scroll(self.body);self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.area.viewport().installEventFilter(self)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.area.setMinimumHeight(35);self.area.setMaximumHeight(102 if pinned else 120)
        layout.addWidget(self.area)
        self.empty=label('尚未追踪，可手动选择。' if pinned else '分析完成后，点选名单加入追踪。','muted',True);layout.addWidget(self.empty)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
    def set_items(self,items,tracked=(),blocked=()):
        keys={item_key(i) for i in tracked};blocked=set(blocked)
        signature=tuple((item_key(i),i['name'],i.get('reason',''),item_key(i) in keys,i.get('op_id') in blocked) for i in items)
        if signature==self.signature:return
        self.signature=signature
        while self.flow.count():
            old=self.flow.takeAt(0).widget();old.hide();old.deleteLater()
        self.buttons={}
        for item in items:
            key=item_key(item);selected=self.pinned or key in keys;banned=item.get('op_id') in blocked
            caption=('干员 · ' if item['kind']=='operator' else '装备 · ')+item['name']
            if banned:caption+=' / 本局禁用'
            b=button(caption,lambda i=dict(item):self.toggle(i));b.setCheckable(True);b.setChecked(selected)
            b.setFixedHeight(29);b.setFixedWidth(min(315,b.fontMetrics().horizontalAdvance(caption)+22))
            b.full_caption=caption;b.preferred_width=b.width()
            b.setStyleSheet('QPushButton { padding: 3px 7px; font-size:12px; }')
            b.setProperty('tone','gold' if selected else 'blue')
            b.setToolTip(caption+'\n'+('点击取消追踪' if selected else '点击追踪；商店出现时高亮')+('\n'+item['reason'] if item.get('reason') else ''))
            self.buttons[key]=b;self.flow.addWidget(b)
        self.area.setVisible(bool(items));self.empty.setVisible(not items)
        self.title.setText(('已追踪 · '+str(len(items))+' 项 · 点击取消') if self.pinned else '阵容 / 装备推荐名单 · 点选追踪')
        self.fit_rows()
        self.fit_timer.start(0)
        self.updateGeometry()
    def fit_rows(self):
        width=max(120,self.area.viewport().width())
        for b in self.buttons.values():
            b.setFixedWidth(min(b.preferred_width,width))
            b.setText(b.fontMetrics().elidedText(b.full_caption,Qt.TextElideMode.ElideRight,b.width()-18))
        height=self.flow.heightForWidth(width)
        self.body.setMinimumHeight(height)
        target=max(31,min(102 if self.pinned else 120,height+2))
        if self.area.height()!=target:self.area.setFixedHeight(target)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.fit_timer.start(0)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Resize:self.fit_timer.start(0)
        return super().eventFilter(obj,event)


class TrackingDialog(QDialog):
    def __init__(self,main):
        super().__init__(main);self.main=main;self.setWindowTitle('手动选择追踪');self.resize(650,650)
        layout=QVBoxLayout(self);self.pins=TrackingChoices(main.toggle_tracking,True);layout.addWidget(self.pins)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索干员、盟约或装备名称');layout.addWidget(self.search)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1);self.lists=[];self.rows=[]
        from .advice import ban_context
        banned={i['op_id'] for i in ban_context(main.db,main.store.state)['banned_operators']}
        for kind,title in [('operator','干员'),('equipment','装备')]:
            choices=QListWidget();self.lists.append(choices);self.tabs.addTab(choices,title)
            entries=main.db.ops.values() if kind=='operator' else main.db.equipment.values()
            for entry in sorted(entries,key=lambda e:(e['tier'],e['name'])):
                value={'kind':kind,'name':entry['name']}
                if kind=='operator':value['op_id']=entry['operator_id']
                detail=' / '.join(entry.get('covenants',[])) if kind=='operator' else f'{entry["tier"]} 阶'
                caption=entry['name']+'   '+detail+('  · 本局禁用' if value.get('op_id') in banned else '')
                item=QListWidgetItem(caption);item.setData(Qt.ItemDataRole.UserRole,value)
                item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked)
                item.setToolTip(entry.get('effect',entry.get('effect_initial','')));choices.addItem(item);self.rows.append(item)
            choices.itemChanged.connect(self.changed)
        layout.addWidget(label('勾选即追踪；上方再次点选取消。开启实时识别和悬浮终端后，在游戏商店框选提醒。','muted',True))
        layout.addWidget(button('完成',self.accept,True));self.search.textChanged.connect(self.filter);self.refresh()
    def changed(self,item):self.main.toggle_tracking(item.data(Qt.ItemDataRole.UserRole))
    def filter(self,text):
        for item in self.rows:item.setHidden(text.strip().casefold() not in item.text().casefold())
    def refresh(self):
        keys={item_key(i) for i in self.main.tracked}
        from .advice import ban_context
        blocked=[i['op_id'] for i in ban_context(self.main.db,self.main.store.state)['banned_operators']]
        self.pins.set_items(self.main.tracked,blocked=blocked)
        for choices in self.lists:
            choices.blockSignals(True)
            for n in range(choices.count()):
                item=choices.item(n);item.setCheckState(Qt.CheckState.Checked if item_key(item.data(Qt.ItemDataRole.UserRole)) in keys else Qt.CheckState.Unchecked)
            choices.blockSignals(False)


def paint_matches(p,viewport,matches):
    p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for item in matches:
        x,y,w,h=item['rect'];r=QRectF(viewport.x()+x*viewport.width(),viewport.y()+y*viewport.height(),w*viewport.width(),h*viewport.height()).adjusted(2,2,-2,-2)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor(18,25,25,220),6));p.drawRect(r)
        p.setPen(QPen(QColor('#ffd16a'),2.5));p.drawRect(r)
        caption='追踪 · '+item['name'];width=min(r.width(),p.fontMetrics().horizontalAdvance(caption)+12)
        tag=QRectF(r.x(),max(viewport.y(),r.y()-22),width,22)
        p.fillRect(tag,QColor(30,33,27,235));p.setPen(QColor('#ffe09b'));p.drawText(tag.adjusted(6,0,-2,0),Qt.AlignmentFlag.AlignVCenter,caption)
    p.restore()


class ShopHighlight(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool
                         |Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
        for attr in (Qt.WidgetAttribute.WA_TranslucentBackground,Qt.WidgetAttribute.WA_TransparentForMouseEvents,Qt.WidgetAttribute.WA_ShowWithoutActivating):self.setAttribute(attr)
        self.setWindowTitle('卫戍协议 · 商店追踪');self.matches=[]
    def paintEvent(self,event):
        p=QPainter(self);paint_matches(p,QRectF(self.rect()),self.matches)
