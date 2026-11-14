"""Watch-list controls and mouse-transparent shop-card emoticon markers."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt,QRectF,QTimer,QEvent
from PySide6.QtGui import QPainter,QPixmap
from PySide6.QtWidgets import QWidget,QVBoxLayout,QDialog,QLineEdit,QTabWidget,QListWidget,QListWidgetItem,QSizePolicy,QGridLayout
from .widgets import FlowLayout,FilterButtons,label,button,row,column,scroll
from .tracking import item_key,valid_rect


class TrackingChoices(QWidget):
    def __init__(self,toggle,pinned=False,manual=None,bulk=None):
        super().__init__();self.toggle=toggle;self.pinned=pinned;self.signature=None;self.buttons={}
        self.fit_timer=QTimer(self);self.fit_timer.setSingleShot(True);self.fit_timer.timeout.connect(self.fit_rows)
        layout=QVBoxLayout(self);layout.setContentsMargins(10,6,10,6);layout.setSpacing(5)
        self.title=label('已追踪 · 点击取消' if pinned else '阵容 / 装备推荐名单','accent',True)
        head=row(self.title);head.layout().setStretch(0,1)
        self.bulk_button=None
        if bulk and not pinned:
            self.bulk_button=button('追踪阵容',bulk);self.bulk_button.setFixedHeight(28)
            self.bulk_button.setStyleSheet('padding: 2px 8px;')
            self.bulk_button.setToolTip('加入下方推荐干员；保留已有追踪，装备仍可逐项选择。')
            head.layout().addWidget(self.bulk_button)
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
        if self.bulk_button:
            operators=[i for i in items if i['kind']=='operator' and i.get('op_id') not in blocked]
            missing=any(item_key(i) not in keys for i in operators)
            self.bulk_button.setEnabled(missing)
            self.bulk_button.setText('阵容已追踪' if operators and not missing else '追踪阵容')
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
            b.setToolTip(caption+'\n'+('点击取消追踪' if selected else '点击追踪；商店出现时显示表情标记')+('\n'+item['reason'] if item.get('reason') else ''))
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
        super().__init__(main);self.main=main;self.setWindowTitle('手动选择追踪');self.resize(820,780);self.setMinimumSize(640,620)
        layout=QVBoxLayout(self);self.pins=TrackingChoices(main.toggle_tracking,True);layout.addWidget(self.pins)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索干员（支持拼音）、装备或效果关键词')
        self.reset_button=button('重置筛选',self.reset_filters);layout.addWidget(row(self.search,self.reset_button))
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1);self.lists=[];self.rows=[];self.counts=[];self.empty_labels=[]
        self.core_filter=FilterButtons('核心盟约',[(c['name'],c['name']) for c in main.db.covenants if c['type']=='核心盟约'])
        self.secondary_filter=FilterButtons('副盟约',[(c['name'],c['name']) for c in main.db.covenants if c['type']=='附加盟约'],'blue')
        self.role_filter=FilterButtons('干员作用',[(x,x) for x in ['叠层','吃层','经济','战斗辅助']],'gold')
        self.operator_tier=FilterButtons('干员等阶',[(f'{i} 阶',i) for i in range(1,7)],exclusive=True)
        self.equipment_type=FilterButtons('装备类型',[('装备',False),('消耗品',True)],'blue',exclusive=True)
        self.equipment_tier=FilterButtons('装备等阶',[(f'{i} 阶',i) for i in sorted({e['tier'] for e in main.db.equipment.values()})],exclusive=True)
        self.filters=[self.core_filter,self.secondary_filter,self.role_filter,self.operator_tier,self.equipment_type,self.equipment_tier]
        for kind,title in [('operator','干员'),('equipment','装备')]:
            choices=QListWidget();choices.setMinimumHeight(100)
            choices.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn);self.lists.append(choices)
            groups=[('核心盟约',self.core_filter),('副盟约',self.secondary_filter),('干员作用',self.role_filter),('等阶',self.operator_tier)] if kind=='operator' else [('类型',self.equipment_type),('等阶',self.equipment_tier)]
            panel=QWidget();grid=QGridLayout(panel);grid.setContentsMargins(0,0,0,0);grid.setColumnStretch(1,1)
            for n,(caption,group) in enumerate(groups):
                grid.addWidget(label(caption,'muted'),n,0,Qt.AlignmentFlag.AlignTop);grid.addWidget(group,n,1)
            count=label('','muted');empty=label('没有匹配项，可减少筛选条件或重置筛选。','muted',True)
            self.counts.append(count);self.empty_labels.append(empty)
            page=column(panel,count,empty,choices);page.layout().setStretch(3,1);self.tabs.addTab(page,title)
            entries=main.db.ops.values() if kind=='operator' else main.db.equipment.values()
            for entry in sorted(entries,key=lambda e:(e['tier'],e['name'])):
                value={'kind':kind,'name':entry['name']}
                if kind=='operator':value['op_id']=entry['operator_id']
                detail=' / '.join(entry.get('covenants',[])+entry.get('categories',[])) if kind=='operator' else ('消耗品' if entry['consumable'] else '装备')
                caption=entry['name']+f'   {entry["tier"]} 阶 · '+detail
                item=QListWidgetItem(caption);item.setData(Qt.ItemDataRole.UserRole,value)
                item.setData(Qt.ItemDataRole.UserRole+1,caption)
                item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked)
                item.setToolTip(entry.get('effect',entry.get('effect_initial','')));choices.addItem(item);self.rows.append(item)
            choices.itemChanged.connect(self.changed)
        layout.addWidget(label('勾选即追踪；上方再次点选取消。开启实时识别和悬浮终端后，在游戏商品卡左侧显示表情提醒。','muted',True))
        layout.addWidget(button('完成',self.accept,True));self.search.textChanged.connect(self.filter)
        for group in self.filters:group.changed.connect(self.filter)
        self.refresh();self.filter()
    def changed(self,item):self.main.toggle_tracking(item.data(Qt.ItemDataRole.UserRole))
    def reset_filters(self):
        self.search.blockSignals(True);self.search.clear();self.search.blockSignals(False)
        for group in self.filters:group.clear(False)
        self.filter()
    def filter(self,*_):
        text=self.search.text().strip().casefold();terms=text.split()
        core,secondary,roles,tiers,types,gear_tiers=[group.values() for group in self.filters]
        matches={o['operator_id'] for o in self.main.db.search(text)}
        for index,choices in enumerate(self.lists):
            visible=0;choices.setUpdatesEnabled(False)
            try:
                for n in range(choices.count()):
                    item=choices.item(n);value=item.data(Qt.ItemDataRole.UserRole)
                    if value['kind']=='operator':
                        e=self.main.db.ops[value['op_id']]
                        show=value['op_id'] in matches and (not core or bool(core.intersection(e['covenants']))) and (not secondary or bool(secondary.intersection(e['covenants']))) and (not roles or bool(roles.intersection(e.get('categories',[])))) and (not tiers or e['tier'] in tiers)
                    else:
                        e=self.main.db.equipment[value['name']]
                        show=all(t in (item.data(Qt.ItemDataRole.UserRole+1)+' '+e['effect']).casefold() for t in terms) and (not types or e['consumable'] in types) and (not gear_tiers or e['tier'] in gear_tiers)
                    item.setHidden(not show);visible+=bool(show)
            finally:choices.setUpdatesEnabled(True)
            self.counts[index].setText(f'{visible} / {choices.count()} 项 · 同组多选取其一，不同组同时满足')
            # Keep the empty-state row allocated so filtering never moves the list.
            self.empty_labels[index].setText('没有匹配项，可减少筛选条件或重置筛选。' if not visible else '勾选加入追踪，筛选不会移除已有追踪。')
        self.reset_button.setEnabled(bool(text or any(group.values() for group in self.filters)))
    def refresh(self):
        keys={item_key(i) for i in self.main.tracked}
        from .advice import ban_context
        blocked=[i['op_id'] for i in ban_context(self.main.db,self.main.store.state)['banned_operators']]
        self.pins.set_items(self.main.tracked,blocked=blocked)
        for choices in self.lists:
            choices.blockSignals(True)
            for n in range(choices.count()):
                item=choices.item(n);value=item.data(Qt.ItemDataRole.UserRole)
                item.setText(item.data(Qt.ItemDataRole.UserRole+1)+('  · 本局禁用' if value.get('op_id') in blocked else ''))
                item.setCheckState(Qt.CheckState.Checked if item_key(value) in keys else Qt.CheckState.Unchecked)
            choices.blockSignals(False)


_marker_pixmap=None


def tracking_marker_pixmap():
    global _marker_pixmap
    if _marker_pixmap is None:
        root=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
        _marker_pixmap=QPixmap(str(root/'assets/tracking-emote.png'))
    return _marker_pixmap


def marker_rect(viewport,item):
    """User's left emblem patch, relative to this frame's actual shop card.

    Keep the marker below the tier/price band and above names/covenants. Both
    preview and the native surface use the same normalized geometry.
    """
    if not valid_rect(item.get('rect')):return QRectF()
    x,y,w,h=item['rect']
    return QRectF(viewport.x()+(x+w*.03)*viewport.width(),
                  viewport.y()+(y+h*.26)*viewport.height(),
                  w*.39*viewport.width(),h*.30*viewport.height())


def paint_matches(p,viewport,matches):
    sprite=tracking_marker_pixmap()
    if sprite.isNull():return
    p.save();p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for item in matches:
        area=marker_rect(viewport,item)
        if area.isEmpty():continue
        scale=min(area.width()/sprite.width(),area.height()/sprite.height())
        w,h=sprite.width()*scale,sprite.height()*scale
        target=QRectF(area.x()+(area.width()-w)/2,area.y()+(area.height()-h)/2,w,h)
        p.drawPixmap(target,sprite,QRectF(sprite.rect()))
    p.restore()


class ShopHighlight(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool
                         |Qt.WindowType.WindowTransparentForInput|Qt.WindowType.WindowDoesNotAcceptFocus)
        for attr in (Qt.WidgetAttribute.WA_TranslucentBackground,Qt.WidgetAttribute.WA_TransparentForMouseEvents,Qt.WidgetAttribute.WA_ShowWithoutActivating):self.setAttribute(attr)
        self.setWindowTitle('卫戍协议 · 商店追踪');self.matches=[]
    def paintEvent(self,event):
        p=QPainter(self);paint_matches(p,QRectF(self.rect()),self.matches)
