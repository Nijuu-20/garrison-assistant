from __future__ import annotations
import traceback
from PySide6.QtCore import Qt, Signal, QObject, QRunnable, QRect, QSize, QPoint, QMimeData
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QPen, QDrag
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QListWidget, QListWidgetItem, QAbstractItemView, QListView, QSizePolicy, QLayout)
from .terminal import TerminalButton, TerminalPanel, OperatorDelegate

STYLE = '''
* { font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; }
QWidget { color: #e7f3ef; background: transparent; }
QMainWindow, QDialog, QWidget#overlay { background: #191d1e; }
QFrame#titlebar { background: #171c1d; border-bottom: 1px solid #42615a; }
QFrame#sidebar { background: #1b2223; border-right: 1px solid #35504b; }
QFrame#terminalPanel { background: transparent; }
QWidget#layout, QStackedWidget { background: transparent; }
QLabel { background: transparent; }
QLabel#muted { color: #8caaa8; }
QLabel#accent { color: #14dfbb; }
QLabel#title { font-size: 27px; font-weight: 700; color: #e7f3ef; }
QLabel#section { font-size: 15px; font-weight: 700; color: #c9e3d7; padding-bottom: 6px; border-bottom: 1px solid #3b5c53; }
QLabel#number { font-family: "Bahnschrift"; font-size: 32px; color: #14dfbb; }
QLabel#statusbar { color: #8caaa8; background: #0d1719; border-top: 1px solid #35504b; font-size: 11px; }
QLabel#headingCode { color: #14dfbb; background: #193c33; border: 1px solid #346557; padding: 8px; font-family: "Bahnschrift"; font-size: 17px; }
QPushButton { background: #1d2e30; border: 1px solid #42635f; padding: 7px 12px; }
QPushButton:hover { color: #14dfbb; border-color: #14dfbb; }
QPushButton:disabled { color: #64807c; }
QPushButton[nav="true"] { padding: 11px 6px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit, QTextEdit, QPlainTextEdit { background: #101d20; border: 1px solid #3c5c56; padding: 7px; selection-background-color: #286c5a; selection-color: #ffffff; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus { border-color: #14dfbb; }
QComboBox QAbstractItemView { background: #1b2e2e; selection-background-color: #286c5a; }
QListWidget, QTableWidget { background: #132023; alternate-background-color: #192a2b; border: 1px solid #3a5752; outline: 0; }
QListWidget::item { padding: 6px; border-bottom: 1px solid #2c423e; }
QListWidget::item:selected, QTableWidget::item:selected { background: #245b4c; color: #e6fff4; }
QListWidget::item:hover { background: #234038; }
QListWidget#operatorSlots::item { padding: 0; border: none; background: transparent; }
QHeaderView::section { background: #28453e; color: #b5d8ca; padding: 7px; border: none; border-right: 1px solid #466c5c; }
QTabWidget::pane { border: 1px solid #3a5752; background: #121f22; }
QTabBar::tab { background: #1b2d2d; color: #8caaa8; padding: 9px 20px; margin-right: 3px; }
QTabBar::tab:selected { background: #14dfbb; color: #111a1d; font-weight: 700; }
QCheckBox { spacing: 8px; padding: 5px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #55766b; background: #101d20; }
QCheckBox::indicator:checked { background: #14dfbb; border: 3px solid #267660; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #101a1c; width: 7px; }
QScrollBar::handle:vertical { background: #417767; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #101a1c; height: 7px; }
QScrollBar::handle:horizontal { background: #417767; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: #1b3330; color: #e7f3ef; border: 1px solid #14dfbb; padding: 6px; }
QMenu { background: #162725; border: 1px solid #4b7b67; }
QMenu::item { padding: 10px 25px; }
QMenu::item:selected { background: #286c5a; }
QSplitter::handle { background: #35534b; }
QProgressBar { border: 1px solid #35534b; background: #111a1d; text-align: center; height: 6px; }
QProgressBar::chunk { background: #14dfbb; }
'''


def label(text='', role='', wrap=False):
    w = QLabel(text); w.setObjectName(role); w.setWordWrap(wrap)
    w.setTextFormat(Qt.TextFormat.PlainText)
    return w


def button(text, fn=None, primary=False):
    b = TerminalButton(text); b.setProperty('primary', primary)
    if fn: b.clicked.connect(lambda _=False: fn())
    return b


def row(*widgets):
    w = QWidget(); w.setObjectName('layout'); l = QHBoxLayout(w); l.setContentsMargins(0, 0, 0, 0); l.setSpacing(10)
    for x in widgets:
        if x is None: l.addStretch()
        else: l.addWidget(x)
    return w


def column(*widgets, margin=0):
    w = QWidget(); w.setObjectName('layout'); l = QVBoxLayout(w); l.setContentsMargins(margin, margin, margin, margin); l.setSpacing(12)
    for x in widgets:
        if x is None: l.addStretch()
        else: l.addWidget(x)
    return w


def card(title, *widgets):
    f = TerminalPanel(); l = QVBoxLayout(f); l.setContentsMargins(15, 13, 15, 13); l.setSpacing(10)
    if title: l.addWidget(label(title, 'section'))
    for x in widgets: l.addWidget(x)
    return f


def scroll(widget):
    s = QScrollArea(); s.setWidgetResizable(True); s.setWidget(widget); return s


class FlowLayout(QLayout):
    """Wrap compact filter buttons while reserving their actual row height."""
    def __init__(self, parent):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(5)
    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientation(0)
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),False)
    def minimumSize(self):
        size=QSize()
        for item in self.items:size=size.expandedTo(item.minimumSize())
        return size
    def sizeHint(self):return self.minimumSize()
    def setGeometry(self,rect):super().setGeometry(rect);self.arrange(rect,True)
    def arrange(self,rect,apply):
        x,y=rect.x(),rect.y();height=0
        for item in self.items:
            size=item.sizeHint()
            if x>rect.x() and x+size.width()>rect.x()+rect.width():
                x=rect.x();y+=height+self.spacing();height=0
            if apply:item.setGeometry(QRect(QPoint(x,y),size))
            x+=size.width()+self.spacing();height=max(height,size.height())
        return y+height-rect.y()


class FilterButtons(QWidget):
    changed=Signal()
    def __init__(self,title,choices,tone='',exclusive=False):
        super().__init__();self.buttons={};self.exclusive=exclusive;layout=FlowLayout(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        for text,value in [('全部',None),*choices]:
            b=button(text);b.setCheckable(True);b.setChecked(value is None)
            b.setProperty('tone',tone);b.setFixedSize(max(50,b.fontMetrics().horizontalAdvance(text)+24),30)
            b.setAccessibleName(f'{title}：{text}')
            b.setToolTip(f'{title} / {text}'+(' · 再次点按取消' if value is not None else ' · 清除此组筛选'))
            b.clicked.connect(lambda checked,v=value:self.select(v,checked))
            self.buttons[value]=b;layout.addWidget(b)
    def values(self):return {v for v,b in self.buttons.items() if v is not None and b.isChecked()}
    def select(self,value,checked):
        if value is None:self.clear(False)
        else:
            if self.exclusive and checked:
                for v,b in self.buttons.items():
                    if v!=value:b.setChecked(False)
            self.buttons[None].setChecked(not self.values())
        self.changed.emit()
    def clear(self,emit=True):
        for value,b in self.buttons.items():b.setChecked(value is None)
        if emit:self.changed.emit()


class DashboardScroll(QScrollArea):
    """Keep the HUD and bottom dock together; small windows scroll the whole view."""
    def __init__(self,widget):
        super().__init__();self.setWidget(widget)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.widget().resize(self.viewport().width(),max(748,self.viewport().height()))


class JobSignals(QObject):
    result = Signal(object); error = Signal(str); finished = Signal()


class Job(QRunnable):
    def __init__(self, fn): super().__init__(); self.fn = fn; self.signals = JobSignals()
    def run(self):
        try: self.signals.result.emit(self.fn())
        except Exception as e: self.signals.error.emit(str(e))
        finally: self.signals.finished.emit()


class DragList(QListWidget):
    dropped = Signal(str, str)
    def __init__(self, zone='', source=False):
        super().__init__(); self.zone = zone; self.source = source
        self.setDragEnabled(True); self.setAcceptDrops(not source)
        self.setDefaultDropAction(Qt.DropAction.CopyAction if source else Qt.DropAction.MoveAction)
    def startDrag(self, _actions):
        item = self.currentItem()
        if not item: return
        data = QMimeData(); data.setText(('op:' if self.source else 'unit:') + str(item.data(Qt.ItemDataRole.UserRole)))
        drag = QDrag(self); drag.setMimeData(data); drag.exec(Qt.DropAction.CopyAction if self.source else Qt.DropAction.MoveAction)
    def dragEnterEvent(self, e):
        if e.mimeData().text().startswith(('op:', 'unit:')): e.acceptProposedAction()
    def dragMoveEvent(self, e): e.acceptProposedAction()
    def dropEvent(self, e):
        self.dropped.emit(e.mimeData().text(), self.zone); e.acceptProposedAction()


class FourColumnList(QListWidget):
    """Keep exactly four avatar choices across while the splitter is resized."""
    def __init__(self):
        super().__init__()
        self.setObjectName('operatorSlots');self.setItemDelegate(OperatorDelegate(self));self.setMouseTracking(True)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setWordWrap(False)
        self.setSpacing(0)
        self.setIconSize(QSize(64,64))
        self.setMinimumWidth(420)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Auto-hide changes the viewport width, which changes grid size, which
        # in turn changes scroll-bar necessity. Reserve the same gutter even
        # for a short/empty result to break that resize feedback loop.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
    def update_grid(self):
        size=QSize(max(80,(self.viewport().width()-2)//4),138)
        if size!=self.gridSize():self.setGridSize(size)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_grid()
    def showEvent(self,event):
        super().showEvent(event)
        self.update_grid()


class PortraitView(QLabel):
    """Paint the original image at the display's pixel scale without changing layout."""
    def __init__(self):
        super().__init__();self.setAlignment(Qt.AlignmentFlag.AlignCenter);self.setFixedHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
    def sizeHint(self):return QSize(200,210)
    def minimumSizeHint(self):return QSize(0,210)
    def paintEvent(self,event):
        pixmap=self.pixmap()
        if pixmap.isNull():return super().paintEvent(event)
        size=pixmap.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        target=QRect((self.width()-size.width())//2,(self.height()-size.height())//2,size.width(),size.height())
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(target,pixmap)


class CalibrationCanvas(QWidget):
    selected = Signal(object)
    def __init__(self):
        super().__init__(); self.pixmap = QPixmap(); self.regions = []; self.detected_regions = []; self.tracking_regions=[]; self.start = None; self.end = None
        self.setMinimumSize(480, 280); self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
    def set_image(self, pixmap): self.pixmap = pixmap; self.update()
    def image_rect(self):
        if self.pixmap.isNull(): return QRect()
        size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect((self.width()-size.width())//2, (self.height()-size.height())//2, size.width(), size.height())
    def paintEvent(self, event):
        p = QPainter(self); p.fillRect(self.rect(), QColor('#101719')); rect = self.image_rect()
        if rect.isEmpty():
            p.setPen(QColor('#9ba9aa')); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '选择游戏窗口截取画面，或导入 / 粘贴截图\n默认自动定位；需要手动补充时可拖出区域'); return
        p.drawPixmap(rect, self.pixmap)
        p.setPen(QPen(QColor('#14dfbb'), 2))
        from .recognition import field_label
        shown=self.detected_regions or self.regions
        labels=[]
        for region in shown:
            p.setPen(QPen(QColor('#ffbf55' if region.get('pending') else '#14dfbb'),2))
            x,y,w,h = region['rect']; r = QRect(int(rect.x()+x*rect.width()), int(rect.y()+y*rect.height()), int(w*rect.width()), int(h*rect.height()))
            text=region.get('label') or field_label(region['key']);tw=min(p.fontMetrics().horizontalAdvance(text)+8,rect.width())
            choices=[QRect(r.x(),r.y()-20,tw,20),QRect(r.x(),r.y(),tw,20),QRect(r.right()+2,r.y(),tw,20),QRect(r.x()-tw-2,r.y(),tw,20)]
            caption=next((c for c in choices if rect.contains(c) and not any(c.intersects(a) for a in labels)),choices[1])
            labels.append(caption);p.drawRect(r);p.fillRect(caption,QColor(15,24,23,220));p.drawText(caption.x()+4,caption.y()+15,text)
        from .tracking_view import paint_matches
        paint_matches(p,rect,self.tracking_regions)
        if self.start is not None and self.end is not None: p.drawRect(QRect(self.start, self.end).normalized())
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(e.position().toPoint()):
            self.start = e.position().toPoint(); self.end = self.start
    def mouseMoveEvent(self, e):
        if self.start is not None: self.end = e.position().toPoint(); self.update()
    def mouseReleaseEvent(self, e):
        if self.start is None: return
        ir = self.image_rect(); r = QRect(self.start, e.position().toPoint()).normalized().intersected(ir)
        if r.width() > 8 and r.height() > 8:
            self.selected.emit([round((r.x()-ir.x())/ir.width(),6), round((r.y()-ir.y())/ir.height(),6), round(r.width()/ir.width(),6), round(r.height()/ir.height(),6)])
        self.start = None; self.end = None; self.update()
