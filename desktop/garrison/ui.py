from __future__ import annotations
import copy
import ctypes
from ctypes import wintypes
import datetime
import json
import os
import sys
import threading
from pathlib import Path
import time
import uuid
import cv2
import numpy as np
from PySide6.QtCore import Qt, QSize, QRectF, QUrl, QTimer, QThreadPool, QPropertyAnimation, QEasingCurve, QAbstractNativeEventFilter
from PySide6.QtGui import QPixmap, QImage, QIcon, QPainter, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QStackedWidget, QLineEdit, QComboBox, QListWidget, QListWidgetItem, QSplitter, QTabWidget,
    QTextEdit, QTextBrowser, QPlainTextEdit, QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QMessageBox, QInputDialog, QDialog, QDialogButtonBox, QKeySequenceEdit,
    QSystemTrayIcon, QMenu, QGraphicsOpacityEffect)
from .core import (Database, StateStore, new_state, unit, covenant_status, recommend, evaluated_effect,
    promotion_need, craft_options, equip_item, validate_actions, validate_state, fingerprint, replacement_options,shop_review_note,pending_shop_field)
from .storage import Storage, read_json, atomic_json
from .windows import Hotkeys, enum_windows, capture_window, stop_capture, set_capture_excluded,client_geometry,place_highlight,peek_capture
from .recognition import Recognizer, StabilityGate, apply_fields, applicable_fields, field_label, mark_uncertain, ready_for_auto, LABELS
from .coach import Coach, endpoint
from .widgets import STYLE, label, button, row, column, card, scroll, DragList, FourColumnList, FilterButtons, PortraitView, CalibrationCanvas, DashboardScroll, Job
from .terminal import TerminalSurface, HudRail, CovenantStrip, RecommendationSlot, TEAL, GOLD, INK, PANEL, frame
from . import __version__
from .battle import mark_missing,known_units,roster_signature,update_roster_status
from .opening import (describe as describe_opening, recompute as recompute_opening, availability as opening_availability,
                      confirmation_problem, snapshot_key as opening_key, core_unrestricted, ban_summary)
from .opening_icons import asset_root as opening_assets
from .advice import overlay_advice,analysis_text,target_candidates
from .tracking import normalize_items,item_key,current_candidates,ShopWatch,same_shop_pixels
from .tracking_view import TrackingChoices,TrackingDialog,ShopHighlight
from .strategy import local_plan,sources_html,bundled_guides,route_matches,route_identity
from .catalog import CatalogDetails
from .briefing import SoloBriefing
from .workspace import WorkspaceMixin


def make_icon():
    path=asset_path('garrison-icon.png')
    if path.exists():return QIcon(str(path))
    pix = QPixmap(64,64); pix.fill(QColor(INK)); p=QPainter(pix)
    p.setPen(QColor(TEAL)); p.setFont(QFont('Microsoft YaHei UI', 30, QFont.Weight.Bold))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, '卫'); p.end(); return QIcon(pix)


def asset_path(name):
    return (Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'assets'/name


def combo(items):
    c = QComboBox()
    for x in items:
        if isinstance(x, tuple): c.addItem(str(x[0]), x[1])
        else: c.addItem(str(x))
    return c


def spin(value=0, minimum=0, maximum=9999):
    s = QSpinBox(); s.setRange(minimum, maximum); s.setValue(value); return s


def table(headers, widths=None):
    t = QTableWidget(0,len(headers)); t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True); t.verticalHeader().hide(); t.verticalHeader().setDefaultSectionSize(40)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def fill_table(t, rows):
    t.setRowCount(len(rows))
    for r, values in enumerate(rows):
        for c, v in enumerate(values):
            item=QTableWidgetItem(str(v)); item.setToolTip(str(v)); t.setItem(r,c,item)


class NativeEvents(QAbstractNativeEventFilter):
    def __init__(self, window): super().__init__(); self.window = window
    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312:
            self.window.hotkey(int(msg.wParam)); return True, 0
        return False, 0


class MoveBar(QFrame):
    def __init__(self, window):
        super().__init__(); self.window = window; self.offset = None; self.setObjectName('titlebar')
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.window.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self, e):
        if isinstance(self.window, MainWindow): self.window.toggle_maximize()


class RouteLockControl(QWidget):
    def __init__(self,main):
        super().__init__();self.main=main;self.choice=None
        self.title=label('','accent',True);self.toggle=button('锁定路线',self.clicked)
        self.toggle.setFixedHeight(30)
        self.track=button('追踪推荐阵容',main.track_recommended_formation);self.track.setFixedHeight(30)
        self.track.setToolTip('将推荐干员加入追踪；已有关注保留，装备可在名单中单独选择。')
        layout=QVBoxLayout(self);layout.setContentsMargins(0,3,0,3);layout.setSpacing(4)
        layout.addWidget(self.title);layout.addWidget(row(self.toggle,self.track))
    def refresh(self):
        m=self.main;s=m.store.state;locked=route_identity(s.get('route_lock'));matches=route_matches(m.db,s,3)
        result=m.ai_result or {};ai_id=result.get('guide_profile_id') if m.settings['ai_enabled'] and result.get('fingerprint')==fingerprint(s) and not result.get('route_conflict') else None
        self.choice=locked or next((r for r in matches if r['id']==ai_id),matches[0] if matches else None)
        self.title.setText(('已锁定路线 / ' if locked else '当前路线 / ')+self.choice['title'] if self.choice else '攻略路线 / 等待推荐')
        self.toggle.setText('解锁路线' if locked else '锁定这条路线');self.toggle.setEnabled(bool(self.choice))
        self.toggle.setToolTip('锁定后只更新回合步骤，不自动换线；禁选与策略条件仍需满足。')
        view=overlay_advice(m.db,s,m.ai_result,m.visible_opening(),m.settings['ai_enabled'])
        candidates=[i for i in view.get('recommendation_list',[]) if i.get('kind')=='operator']
        tracked={item_key(i) for i in m.tracked};missing=any(item_key(i) not in tracked for i in candidates)
        self.track.setEnabled(missing);self.track.setText('阵容已追踪' if candidates and not missing else '追踪推荐阵容')
    def clicked(self):
        if self.choice:self.main.toggle_route_lock(self.choice['id'])


def opening_lock_style(widget,locked):
    if widget.property('openingLocked')==locked:return
    widget.setProperty('openingLocked',locked)
    widget.setStyleSheet('QLabel { color:#ffe09b; background:#29342e; border:1px solid #677056; padding:4px 7px; }' if locked else '')


class Overlay(QWidget):
    def __init__(self, main):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.main=main; self.setWindowTitle('卫戍协议 · 悬浮面板'); self.setMinimumWidth(340)
        self.setStyleSheet(STYLE); self.setObjectName('overlay'); self.resize(370,460)
        l=QVBoxLayout(self); l.setContentsMargins(1,1,1,1); l.setSpacing(0)
        bar=MoveBar(self); bl=QHBoxLayout(bar);bl.setContentsMargins(10,5,6,5);bl.setSpacing(5)
        bl.addWidget(label('卫戍终端 / 决策建议', 'accent')); bl.addStretch()
        home=button('↗', main.restore_main);home.setToolTip('打开主窗口');minimize=button('−', main.minimize_overlay);minimize.setToolTip('最小化为置顶悬浮按钮')
        for b in (home,minimize):b.setFixedSize(28,28);b.setStyleSheet('QPushButton { padding:0; font-size:16px; }');bl.addWidget(b)
        l.addWidget(bar)
        self.tracking_pins=TrackingChoices(main.toggle_tracking,True,main.open_tracking);l.addWidget(self.tracking_pins)
        self.hud=HudRail(compact=True);l.addWidget(self.hud)
        self.activity=label('','accent',True);self.content=label('',wrap=True)
        self.content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.sources=label('','muted',True);self.sources.setTextFormat(Qt.TextFormat.RichText);self.sources.setOpenExternalLinks(True)
        self.route_lock=RouteLockControl(main)
        self.analysis_box=card('优先分析',self.activity,self.route_lock,self.content,self.sources)
        self.opening_status=label('','accent',True);self.opening_bans=label('',wrap=True)
        self.opening_auto_check=QCheckBox('稳定识别后自动确认')
        self.opening_auto_check.setChecked(main.settings['opening_auto_confirm'])
        self.opening_auto_check.toggled.connect(main.toggle_opening_auto_confirm)
        self.opening_confirm=button('确认本局禁选',main.apply_opening,True)
        self.opening_box=card('本局禁选',self.opening_status,self.opening_bans,self.opening_auto_check,self.opening_confirm)
        self.goal=label('目标盟约推荐','section',True)
        self.suggestions=[];suggestion_boxes=[]
        for i in range(2):
            title=label('','section',True);reason=label('',wrap=True)
            box=card('',title,reason);self.suggestions.append((box,title,reason));suggestion_boxes.append(box)
        self.links=label('', 'muted',True)
        self.tracking_choices=TrackingChoices(main.toggle_tracking,bulk=main.track_recommended_formation)
        inner=column(self.analysis_box,self.opening_box,self.tracking_choices,self.goal,*suggestion_boxes,self.links,None,margin=10)
        self.advice_layout=inner.layout()
        l.addWidget(scroll(inner),1)
        capture=button('重新识别',main.capture_once);capture.setProperty('tone','blue')
        self.opening_review_button=button('核对本局禁选',main.begin_opening_review)
        self.opening_review_cancel=button('返回局面',main.end_opening_review)
        self.new_session_button=button('新对局（一键清空）',main.new_session)
        self.new_session_button.setToolTip('归档上一局，清空本局阵容、禁选、追踪和建议；保留 API 与识别配置。')
        l.addWidget(column(row(self.opening_review_button,self.opening_review_cancel),row(capture,button('AI 分析',main.analyze,True)),self.new_session_button,margin=9))
        self.resize(410,720)
    def update_content(self):
        m=self.main;s=m.store.state
        self.route_lock.refresh()
        m.fill_tracking(self.tracking_pins,self.tracking_choices)
        view=overlay_advice(m.db,s,m.ai_result,m.visible_opening(),m.settings['ai_enabled'])
        self.hud.set_state(s);self.goal.setText('目标盟约推荐')
        self.activity.setText(view['source']+(' · 正在细化建议' if m.ai_busy else ''))
        self.content.setText(view['analysis']);ranked=view['targets']
        self.sources.setText(sources_html(view.get('source_ids',[]),view.get('source_label','攻略来源')));self.sources.setVisible(bool(self.sources.text()))
        confirmation=m.opening_confirmation()
        self.opening_review_button.setText('重新读取禁选' if m.review_opening else '核对本局禁选')
        self.opening_review_cancel.setVisible(m.review_opening)
        self.opening_box.setVisible(confirmation['visible'])
        self.opening_status.setText(confirmation['status']);self.opening_bans.setText(confirmation['bans'])
        opening_lock_style(self.opening_status,confirmation.get('locked',False))
        self.opening_confirm.setText(confirmation['button']);self.opening_confirm.setEnabled(confirmation['enabled'])
        for i,(box,title,reason) in enumerate(self.suggestions):
            box.setVisible(i<len(ranked))
            if i<len(ranked):
                r=ranked[i];title.setText(('优先 / ' if i==0 else '备选 / ')+r['name'])
                names='、'.join(c['name']+('（商店）' if c['in_shop'] else '') for c in r['candidates'][:2])
                reason.setText(r['reason']+'\n'+r['progress']+('\n补位留意：'+names if names else '')+('\n本局禁选尚未确认，先核对可用性。' if r['conditional'] else ''))
        self.links.setText('先确认阵容与本局可用盟约，再决定主力方向。' if not ranked else '')
        self.links.setVisible(not ranked)
        appearance=(m.settings['overlay_opacity'],m.settings['overlay_scale'])
        if getattr(self,'appearance',None)!=appearance:
            self.appearance=appearance;self.setWindowOpacity(appearance[0])
            self.setStyleSheet(STYLE + f'QLabel {{ font-size: {round(13*appearance[1]/100)}px; }}')
    def closeEvent(self,e): e.ignore(); self.main.close_overlay()


class FloatingButton(QWidget):
    def __init__(self,main):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.main=main; self.setWindowTitle('卫戍协议 · 快速访问'); self.setFixedSize(main.settings['floating_size'],main.settings['floating_size']); self.start=None; self.moved=False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground);self.icon_pixmap=QPixmap(str(asset_path('garrison-icon.png')));self.hover=False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('单击恢复悬浮面板 · 双击主窗口 · 按住拖动')
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pad=0 if self.hover else 2;p.drawPixmap(self.rect().adjusted(pad,pad,-pad,-pad),self.icon_pixmap)
    def enterEvent(self,e):self.hover=True;self.update()
    def leaveEvent(self,e):self.hover=False;self.update()
    def mousePressEvent(self,e): self.start=e.globalPosition().toPoint()-self.pos(); self.origin=self.pos(); self.moved=False
    def mouseMoveEvent(self,e):
        if self.start is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint()-self.start); self.moved=(self.pos()-self.origin).manhattanLength()>5
    def mouseReleaseEvent(self,e):
        self.start=None
        if not self.moved: self.main.show_overlay()
    def mouseDoubleClickEvent(self,e): self.main.restore_main()


class MainWindow(WorkspaceMixin,QMainWindow):
    def __init__(self, storage=None):
        super().__init__(); self.storage=storage or Storage(); self.settings=self.storage.settings
        override=self.settings.get('database_override'); self.db=Database(override if override and Path(override).exists() else None)
        self.db.disabled_guide_routes=list(self.settings.get('disabled_guide_routes',[]))
        saved=read_json(self.storage.root/'session.json',None)
        try: saved=validate_state(saved,self.db) if saved else None
        except ValueError: saved=None
        self.store=StateStore(saved); self.pool=QThreadPool(self); self.pool.setMaxThreadCount(3); self.jobs=set()
        self.recognizer=Recognizer(self.db); self.gate=StabilityGate.from_settings(self.settings); self.coach=Coach()
        self.battle_gate=StabilityGate(self.settings['stable_frames']);self.battle_busy=False
        self.solo_briefing=SoloBriefing();self.review_opening=False
        self.live=False; self.capture_busy=False; self.ai_busy=False; self.closing=False; self.frame=None; self.last_recognition=None
        self.capture_generation=0; self.ai_generation=0; self.ai_result=None; self.recognition_status='尚未识别 · 等待连接游戏'
        self.tracked=normalize_items(self.db,self.storage.tracking);self.shop_watch=ShopWatch()
        self.tracking_dialog=None;self.watch_source=None;self.tracking_frame=None
        self.auto_keys=set(); self.pixmaps={}; self.compare_ids=[]; self.current_op=next(iter(self.db.ops)); self.board_uid=None
        self.setWindowTitle('卫戍协议助手'); self.setWindowIcon(make_icon())
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.resize(1380,900); self.setMinimumSize(1100,720); self.setStyleSheet(STYLE)
        root=TerminalSurface(); self.setCentralWidget(root); root_layout=QVBoxLayout(root); root_layout.setContentsMargins(0,0,0,0); root_layout.setSpacing(0)
        title=MoveBar(self); tl=QHBoxLayout(title); tl.setContentsMargins(14,6,8,6);tl.setSpacing(6)
        title_icon=QLabel();title_icon.setPixmap(self.windowIcon().pixmap(28,28));tl.addWidget(title_icon)
        tl.addWidget(label('卫戍协议助手', 'accent')); tl.addWidget(label('  /  规程 · 序列Ⅰ', 'muted')); tl.addStretch()
        self.overlay_toggle_button=button('悬浮终端 · 关',self.toggle_overlay);self.overlay_toggle_button.setCheckable(True)
        self.overlay_toggle_button.setAccessibleName('切换悬浮终端');tl.addWidget(self.overlay_toggle_button)
        for text,fn,tip in [('—',self.showMinimized,'最小化主窗口'),('□',self.toggle_maximize,'最大化 / 还原'),('×',self.close,'收起到系统托盘')]:
            b=button(text,fn);b.setFixedSize(32,30);b.setToolTip(tip);b.setAccessibleName(tip);tl.addWidget(b)
        root_layout.addWidget(title)
        body=QHBoxLayout(); body.setSpacing(0); root_layout.addLayout(body,1)
        side=QFrame(); side.setObjectName('sidebar'); side.setFixedWidth(188); sl=QVBoxLayout(side); sl.setContentsMargins(9,14,9,10); sl.setSpacing(4)
        logo=label('卫 戍 协 议','title');sl.addWidget(logo);sl.addWidget(label('STRONGHOLD PROTOCOL','muted'))
        sl.addWidget(label('辅助终端  /  '+__version__,'accent'));sl.addSpacing(10)
        self.stack=QStackedWidget();self.nav=[];self.page_ids={};self.workspace_ready=False
        parts={name:build() for name,build in [('home',self.build_home),('roster',self.page_board),('catalog',self.page_catalog),
            ('covenants',self.page_covenants),('equipment',self.page_equipment),('tools',self.page_economy),
            ('guides',self.page_guides),('recognition',self.page_recognition),('api',self.page_coach),('settings',self.page_settings)]}
        for i,(name,title,content) in enumerate(self.compose_workspace(parts)):
            if i==3:sl.addSpacing(12)
            self.page_ids[name]=i
            b=button(title,lambda idx=i:self.navigate(idx)); b.setCheckable(True); b.setProperty('nav',True);b.setFixedHeight(38);sl.addWidget(b); self.nav.append(b)
            wrap=QWidget();wl=QVBoxLayout(wrap);wl.setContentsMargins(18,14,18,12);wl.addWidget(content);self.stack.addWidget(wrap)
        self.workspace_ready=True
        sl.addStretch();sl.addWidget(label('本地资料 / 即时推荐\n官方 PC 端优先适配','muted'));body.addWidget(side);body.addWidget(self.stack,1)
        self.status=label('准备就绪','statusbar');self.status.setMargin(7);root_layout.addWidget(self.status)
        self.overlay=Overlay(self); self.floating=FloatingButton(self);self.shop_highlight=ShopHighlight()
        area=QApplication.primaryScreen().availableGeometry(); self.overlay.move(area.right()-410, area.top()+120); self.floating.move(area.right()-100,area.top()+200)
        self.hotkeys=Hotkeys(int(self.winId())); self.native_filter=NativeEvents(self); QApplication.instance().installNativeEventFilter(self.native_filter)
        try: self.configure_hotkeys()
        except ValueError as e: self.status.setText(str(e))
        self.tray=QSystemTrayIcon(self.windowIcon(),self); self.tray.setToolTip('卫戍协议助手')
        menu=QMenu(); menu.addAction('打开主窗口',self.restore_main); menu.addAction('打开悬浮面板',self.show_overlay); menu.addAction('退出',self.quit_app)
        self.tray.setContextMenu(menu); self.tray_menu=menu; self.tray.activated.connect(lambda reason:self.restore_main() if reason==QSystemTrayIcon.ActivationReason.Trigger else None); self.tray.show()
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(350)
        self.last_capture=0; self.navigate(0,False); self.refresh_all()
        QShortcut(QKeySequence('Ctrl+Z'),self,activated=self.undo); QShortcut(QKeySequence('Ctrl+Y'),self,activated=self.redo)

    def heading(self,title,subtitle):
        codes={'首页':'01','资料图鉴':'02','阵容攻略库':'03','对局工具':'04','设置':'05'}
        code=label(codes.get(title,'//'),'headingCode');code.setFixedSize(44,56);code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text=column(label(title,'title'),label(subtitle,'muted',True));text.layout().setSpacing(3)
        heading=row(code,text);heading.layout().setStretch(1,1);heading.setFixedHeight(60);return heading
    def notify(self,text): self.status.setText(text)
    def error(self,text): self.notify(text); QMessageBox.warning(self,'需要注意',text)
    def run_job(self,fn,result,error=None,done=None):
        job=Job(fn); self.jobs.add(job)
        job.signals.result.connect(result); job.signals.error.connect(error or self.notify)
        def finish():
            self.jobs.discard(job)
            if done: done()
        job.signals.finished.connect(finish); self.pool.start(job)
    def change(self,fn,reason='手动更新'):
        try:
            if self.store.change(fn,reason): self.refresh_all()
        except (ValueError,KeyError,TypeError) as e: self.error(str(e))
    def refresh_all(self):
        if 'battle_roster' in self.store.state['field_meta']:update_roster_status(self.store.state)
        self.storage.save_state(self.store.state)
        for fn in (self.refresh_home,self.refresh_board,self.refresh_covenants,self.refresh_inventory,self.refresh_shop,self.refresh_strategies,self.refresh_ai,self.refresh_opening): fn()
        self.overlay.update_content()
        self.refresh_tracking()

    def fill_tracking(self,pins,choices):
        from .advice import ban_context
        blocked=[i['op_id'] for i in ban_context(self.db,self.store.state)['banned_operators']]
        pins.set_items(self.tracked,blocked=blocked)
        view=overlay_advice(self.db,self.store.state,self.ai_result,self.visible_opening(),self.settings['ai_enabled'])
        candidates=view.get('recommendation_list',[])
        choices.set_items(candidates,self.tracked)
    def refresh_tracking(self):
        if hasattr(self,'home_pins'):self.fill_tracking(self.home_pins,self.home_choices)
        if hasattr(self,'ai_pins'):self.fill_tracking(self.ai_pins,self.ai_choices)
        if hasattr(self,'overlay'):self.fill_tracking(self.overlay.tracking_pins,self.overlay.tracking_choices)
        if self.tracking_dialog is not None:self.tracking_dialog.refresh()
        for control in (getattr(self,'home_route_lock',None),getattr(self,'ai_route_lock',None),getattr(getattr(self,'overlay',None),'route_lock',None)):
            if control is not None:control.refresh()
        self.refresh_shop_matches()
    def toggle_tracking(self,item):
        items=normalize_items(self.db,[item])
        if not items:return
        item=items[0];key=item_key(item);exists=any(item_key(i)==key for i in self.tracked)
        self.tracked=[i for i in self.tracked if item_key(i)!=key] if exists else [*self.tracked,item]
        self.storage.save_tracking(self.tracked);self.refresh_tracking()
    def track_recommended_formation(self):
        view=overlay_advice(self.db,self.store.state,self.ai_result,self.visible_opening(),self.settings['ai_enabled'])
        candidates=normalize_items(self.db,[i for i in view.get('recommendation_list',[]) if i.get('kind')=='operator'],self.store.state)
        keys={item_key(i) for i in self.tracked};added=[i for i in candidates if item_key(i) not in keys]
        if not added:return
        self.tracked+=added;self.storage.save_tracking(self.tracked);self.refresh_tracking()
        self.notify(f'已加入 {len(added)} 名推荐干员；商店出现时显示追踪标记')
    def toggle_route_lock(self,profile_id):
        locked=self.store.state.get('route_lock')
        if not locked and profile_id not in {m['id'] for m in route_matches(self.db,self.store.state,20)}:return
        self.cancel_ai();self.ai_result=None;self.auto_keys.clear()
        self.change(lambda s:s.update(route_lock='' if locked else profile_id),'解除攻略路线锁定' if locked else '锁定攻略路线')
        self.notify('已恢复自动选择攻略路线' if locked else '攻略路线已锁定；后续建议沿用该路线，当前回合步骤仍会更新')
    def open_tracking(self):
        if self.tracking_dialog is not None:self.tracking_dialog.raise_();return
        dialog=TrackingDialog(self);self.tracking_dialog=dialog
        dialog.finished.connect(lambda _:(setattr(self,'tracking_dialog',None),dialog.deleteLater()))
        dialog.show()
    def clear_shop_tracking(self):
        self.shop_watch.reset();self.watch_source=None;self.tracking_frame=None;self.pixel_missing_since=None
        if hasattr(self,'canvas'):self.canvas.tracking_regions=[];self.canvas.update()
        if hasattr(self,'shop_highlight'):self.shop_highlight.hide();self.shop_highlight.matches=[]
    def refresh_shop_matches(self):
        if not hasattr(self,'canvas'):return
        matches=self.shop_watch.matches(self.tracked)
        from .advice import ban_context
        banned={i['op_id'] for i in ban_context(self.db,self.store.state)['banned_operators']}
        self.canvas.tracking_regions=[i for i in matches if i.get('op_id') not in banned];self.canvas.update()
        if hasattr(self,'shop_highlight'):self.update_shop_highlight()
    def update_shop_highlight(self):
        surface=self.shop_highlight;source=self.watch_source;matches=self.canvas.tracking_regions
        if not (self.live and source and matches and (self.overlay.isVisible() or self.floating.isVisible())):
            surface.hide();return
        selected=self.window_combo.currentData() or {}
        if any(selected.get(k)!=source.get(k) for k in ('hwnd','pid')):self.clear_shop_tracking();return
        try:
            geometry=client_geometry(source['hwnd'],source['pid'])
            if geometry is None:surface.hide();return
            if tuple(geometry[2:])!=tuple(source['size']):self.clear_shop_tracking();return
            latest=peek_capture(source['hwnd'],source['pid'])
            if latest is None:
                now=time.monotonic()
                if getattr(self,'pixel_missing_since',None) is None:self.pixel_missing_since=now
                if now-self.pixel_missing_since>1:surface.hide()
                if now-self.pixel_missing_since>3:self.clear_shop_tracking()
                return
            self.pixel_missing_since=None
            matches=self.shop_watch.visible_matches(latest,self.tracking_frame,matches)
            self.canvas.tracking_regions=matches
            if not matches:surface.hide();return
            surface.matches=matches
            if not surface.isVisible():
                set_capture_excluded(int(surface.winId()));surface.show()
            place_highlight(int(surface.winId()),geometry);surface.update()
        except (RuntimeError,OSError):self.clear_shop_tracking()
    def navigate(self,index,animate=True):
        index=self.resolve_destination(index)
        self.finish_transition()
        changed=self.stack.currentIndex()!=index
        self.stack.setCurrentIndex(index)
        for i,b in enumerate(self.nav): b.setChecked(i==index)
        if changed and animate and not self.settings['reduce_motion']:
            widget=self.stack.currentWidget();effect=QGraphicsOpacityEffect(widget);widget.setGraphicsEffect(effect)
            self.transition_widget=widget
            self.transition=QPropertyAnimation(effect,b'opacity',self);self.transition.setDuration(120);self.transition.setStartValue(.65);self.transition.setEndValue(1);self.transition.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.transition.finished.connect(self.finish_transition);self.transition.start()
    def finish_transition(self):
        transition=getattr(self,'transition',None);self.transition=None
        if transition is not None:transition.stop();transition.deleteLater()
        widget=getattr(self,'transition_widget',None);self.transition_widget=None
        if widget is not None:
            # At opacity 1 the page must return to direct, DPI-aware painting;
            # retaining the effect keeps its offscreen texture around forever.
            widget.setGraphicsEffect(None);widget.update()
    def toggle_maximize(self): self.showNormal() if self.isMaximized() else self.showMaximized()
    def restore_main(self): self.showNormal(); self.raise_(); self.activateWindow()
    def show_overlay(self):
        self.floating.hide(); self.overlay.update_content(); self.overlay.show(); self.overlay.raise_(); set_capture_excluded(int(self.overlay.winId()))
        self.sync_overlay_toggle()
    def minimize_overlay(self):
        self.overlay.hide(); self.floating.show(); self.floating.raise_(); set_capture_excluded(int(self.floating.winId()))
        self.sync_overlay_toggle()
    def close_overlay(self):
        self.overlay.hide();self.floating.hide();self.notify('悬浮面板已完全关闭，可从主窗口或快捷键重新打开')
        self.shop_highlight.hide()
        self.sync_overlay_toggle()
    def toggle_overlay(self):
        if self.overlay.isVisible() or self.floating.isVisible():self.close_overlay()
        else:self.show_overlay()
    def sync_overlay_toggle(self):
        enabled=self.overlay.isVisible() or self.floating.isVisible()
        self.overlay_toggle_button.setChecked(enabled);self.overlay_toggle_button.setText('悬浮终端 · '+('开' if enabled else '关'))
        self.overlay_toggle_button.setToolTip('点击关闭悬浮面板和悬浮图标' if enabled else '点击开启悬浮面板')
    def configure_hotkeys(self): self.hotkeys.configure({1:self.settings['main_hotkey'],2:self.settings['overlay_hotkey'],3:self.settings['capture_hotkey'],4:self.settings['coach_hotkey']})
    def hotkey(self,key):
        if key==1: self.restore_main() if self.isMinimized() or not self.isVisible() else self.showMinimized()
        elif key==2: self.minimize_overlay() if self.overlay.isVisible() else self.show_overlay()
        elif key==3: self.capture_once()
        elif key==4: self.analyze()
    def undo(self):
        if self.store.undo(): self.refresh_all()
    def redo(self):
        if self.store.redo(): self.refresh_all()
    def closeEvent(self,event):
        if self.closing: event.accept()
        else: event.ignore(); self.hide(); self.tray.showMessage('卫戍协议助手','已收起到托盘；可通过快捷键或托盘恢复。')
    def quit_app(self):
        self.closing=True; self.live=False; self.timer.stop(); self.coach.cancel(); self.hotkeys.clear()
        self.clear_shop_tracking()
        stop_capture()
        self.storage.save_settings(); self.storage.save_state(self.store.state); self.overlay.hide(); self.floating.hide(); self.tray.hide(); QApplication.instance().quit()
    def pixmap(self,oid,kind='avatar'):
        key=(oid,kind)
        if key not in self.pixmaps:
            p=QPixmap(); blob=self.db.image_bytes(oid,kind)
            if blob: p.loadFromData(blob)
            self.pixmaps[key]=p
        return self.pixmaps[key]

    def page_home(self):return self.build_home()

    def refresh_home(self):
        s=self.store.state;links=covenant_status(self.db,s)
        self.refresh_home_setup()
        self.home_route_lock.refresh()
        self.home_hud.set_state(s);self.home_level.setText('—' if s['level'] is None else str(s['level']))
        visible=sorted([c for c in links if c['count'] or c['name']==s['target']],key=lambda c:(not c['active'],-c['count']))
        self.home_links.set_entries(visible[:9])
        self.home_goal.setText('目标盟约 / ' + (s['target'] or '尚未选择'))
        roster_units=known_units(s);missing=sum(bool(u.get('sprite_missing')) for u in roster_units)
        self.home_status.setText(f'{s["phase"]}阶段 · 战场 {sum(u["zone"]=="field" for u in roster_units)} 人 · 整备 {sum(u["zone"]=="bench" for u in roster_units)} 人'+(f' · {missing} 人待核对（沿用上次阵容）' if missing else ''))
        ranked=recommend(self.db,s,bool(s['shop']))[:5]; lines=[]
        for i,slot in enumerate(self.home_slots):
            r=ranked[i] if (s['units'] or s['shop']) and i<len(ranked) else None
            slot.empty_text='暂无更多候选' if s['units'] or s['shop'] else '等待局面信息'
            slot.set_recommendation({**r,'tier':self.db.ops[r['op_id']]['tier']} if r else None,self.pixmap(r['op_id']) if r else None)
        if not s['units'] and not s['shop']: lines=['添加当前干员，或连接游戏并开启自动定位识别。','\n识别完成后，本地建议会先更新；AI 可独立启用。']
        else:
            if s['field_meta'].get('battle_roster',{}).get('uncertain'):
                lines+=['小人比对为局部结果，完整阵容尚未核对；建议仅按已知干员计算。','']
            if any(v.get('uncertain') for k,v in s['field_meta'].items() if k=='gold' or k.startswith(('shop:','cost:'))):
                lines+=['注意：资金或商店有未确认区域。下列建议基于上次记录，请先核对当前画面。','']
            for i,r in enumerate(ranked):
                cost=f'{r["cost"]}资金' + ('' if r['cost_confirmed'] else '（基础估算）')
                lines.extend([f'{i+1:02}  {r["name"]}  /  {cost}', ' · '.join(r['reasons']), ''])
            lines.append('这些是规则与协同建议，不代表实战胜率。' if not s['shop'] else '购买前确认实际价格；推荐按当前可见商店计算。')
        opening=self.visible_opening()
        if opening:
            lines=[describe_opening(self.db,opening,s['target'])]
            self.home_goal.setText('开局盟约 / 禁选推算与单人起步建议')
            for slot in self.home_slots:slot.set_recommendation(None,None)
        view=overlay_advice(self.db,s,self.ai_result,opening,self.settings['ai_enabled'])
        if not opening:
            lines=[analysis_text(self.db,s,self.ai_result) if view['source']=='AI 分析' else local_plan(self.db,s)['analysis']]
        self.home_sources.setText(sources_html(view.get('source_ids',[]),view.get('source_label','攻略来源')))
        content='\n'.join(lines)
        if self.local_advice.toPlainText()!=content:self.local_advice.setPlainText(content)
        self.home_roster.clear()
        for u in s['units']:
            o=self.db.ops[u['op_id']]; item=QListWidgetItem(QIcon(self.pixmap(u['op_id'])),f'{o["name"]}   {"精锐待确认" if u.get("sprite_elite_unknown") else "精锐" if u["elite"] else "初始"}\n{"战场" if u["zone"]=="field" else "整备"}  /  {" · ".join(o["covenants"])}');item.setData(Qt.ItemDataRole.UserRole,u['uid']);self.home_roster.addItem(item)

        for i,u in enumerate(s['units']):
            item=self.home_roster.item(i)
            if u.get('sprite_missing'):item.setText(item.text()+' · 待核对（沿用上次记录）')
            if u.get('sprite_elite_unknown'):item.setText(item.text().replace('初始','精锐待确认'))

    def page_board(self):
        self.board_search=QLineEdit(); self.board_search.setPlaceholderText('搜索名称 / 拼音 / 盟约'); self.board_search.textChanged.connect(self.fill_board_pool)
        self.board_pool=DragList(source=True); self.board_pool.setIconSize(QSize(44,44)); self.board_pool.itemDoubleClicked.connect(lambda item:self.add_unit(item.data(Qt.ItemDataRole.UserRole),'field'))
        self.field_list=DragList('field'); self.bench_list=DragList('bench')
        for w in (self.field_list,self.bench_list):
            w.setIconSize(QSize(56,56)); w.dropped.connect(self.drop_unit); w.itemClicked.connect(lambda item:self.select_unit(item.data(Qt.ItemDataRole.UserRole)))
        self.team_name=QLineEdit(self.store.state['name']); self.team_name.setPlaceholderText('阵容名称')
        self.target_combo=combo([('未指定目标','')]+[(c['name'],c['name']) for c in self.db.covenants]); self.target_combo.currentIndexChanged.connect(lambda:self.change(lambda s:s.update(target=self.target_combo.currentData()),'修改目标盟约'))
        self.unit_title=label('选择阵容中的干员','section'); self.unit_elite=QCheckBox('精锐状态');self.unit_capacity=QCheckBox('已确认四栏暴躁铁皮策略');self.unit_capacity.toggled.connect(self.set_unit_capacity)
        self.unit_skill=QComboBox(); self.unit_gear=QListWidget(); self.unit_gear.setMaximumHeight(100)
        self.unit_elite.toggled.connect(self.set_unit_elite)
        self.unit_skill.currentIndexChanged.connect(self.set_unit_skill)
        detail=card('实例设置',self.unit_title,self.unit_elite,button('确认所选精锐状态',self.confirm_unit_elite),button('所选干员改为手动维护',self.detach_sprite),self.unit_capacity,self.unit_skill,self.unit_gear,
                    row(button('装备',self.assign_equipment),button('卸下',self.remove_equipment)),
                    row(button('移至另一侧',self.move_selected),button('移除',self.remove_selected)),button('满足同名条件后晋升',self.promote_selected))
        left=column(self.board_search,self.board_pool); left.setMinimumWidth(220)
        middle=column(card('战场区  /  拖入干员',self.field_list),card('整备区  /  经济盟约在此仍可计数',self.bench_list))
        split=QSplitter(); split.addWidget(left); split.addWidget(middle); split.addWidget(detail); split.setSizes([250,500,270])
        self.saved_teams=combo([(x['name'],i) for i,x in enumerate(self.storage.teams)])
        self.fill_board_pool()
        return column(label('核对战场与整备区：拖入或双击添加成员，选择成员修正精锐、位置与装备。','muted',True),
            row(self.team_name,self.target_combo,button('保存阵容',self.save_team,True),button('撤销',self.undo),button('恢复',self.redo)),
            split,row(self.saved_teams,button('载入',self.load_team),button('导入阵容',self.import_team),button('导出阵容',self.export_team),button('分享图',self.export_image)),button('已核对当前完整阵容',self.confirm_battle_roster))

    def fill_board_pool(self):
        if not hasattr(self,'board_pool'):return
        self.board_pool.clear()
        for o in self.db.search(self.board_search.text()):
            item=QListWidgetItem(QIcon(self.pixmap(o['operator_id'])),f'{o["name"]}  /  {o["recruit_cost"]}资金\n{" · ".join(o["covenants"])}'); item.setData(Qt.ItemDataRole.UserRole,o['operator_id']); self.board_pool.addItem(item)
    def add_unit(self,oid,zone): self.change(lambda s:s['units'].append(unit(oid,zone)),f'加入{self.db.ops[oid]["name"]}')
    def drop_unit(self,text,zone):
        kind,value=text.split(':',1)
        if kind=='op': self.add_unit(value,zone)
        else: self.change(lambda s:next(u for u in s['units'] if u['uid']==value).update(zone=zone),'移动干员')
    def refresh_board(self):
        s=self.store.state
        for w in (self.field_list,self.bench_list): w.clear()
        for u in s['units']:
            o=self.db.ops[u['op_id']]; item=QListWidgetItem(QIcon(self.pixmap(u['op_id'])),f'{o["name"]}   {"◆ 精锐" if u["elite"] else "◇ 初始"}\n{" · ".join(o["covenants"])}   /   装备 {len(u["equipment"])}/{u["capacity"]}')
            item.setData(Qt.ItemDataRole.UserRole,u['uid']); (self.field_list if u['zone']=='field' else self.bench_list).addItem(item)
            if u.get('sprite_missing'):item.setText(item.text()+'\n待核对 · 保留阵容与盟约贡献')
            if u.get('sprite_elite_unknown'):item.setText(item.text().replace('◇ 初始','◇ 精锐状态待确认'))
        self.target_combo.blockSignals(True); self.target_combo.setCurrentIndex(max(0,self.target_combo.findData(s['target']))); self.target_combo.blockSignals(False)
        self.select_unit(self.board_uid)
    def selected_unit(self): return next((u for u in self.store.state['units'] if u['uid']==self.board_uid),None)
    def select_unit(self,uid):
        self.board_uid=uid; u=self.selected_unit(); self.unit_elite.blockSignals(True);self.unit_capacity.blockSignals(True); self.unit_skill.blockSignals(True); self.unit_skill.clear(); self.unit_gear.clear()
        self.unit_capacity.setEnabled(bool(u and self.db.ops[u['op_id']]['name']=='“暴躁铁皮”'));self.unit_capacity.setChecked(bool(u and u['capacity']==4))
        self.unit_elite.setEnabled(bool(u)); self.unit_skill.setEnabled(bool(u))
        if u:
            o=self.db.ops[u['op_id']]; self.unit_title.setText(o['name']); self.unit_elite.setChecked(u['elite'])
            self.unit_skill.addItem('使用数据库推荐', '')
            for sk in self.db.skills.values():
                if sk['operator_id']==u['op_id']: self.unit_skill.addItem(f'S{sk["skill_number"]} {sk["skill_name"]}',sk['skill_id'])
            self.unit_skill.setCurrentIndex(max(0,self.unit_skill.findData(u['skill']))); self.unit_gear.addItems(u['equipment'])
        else: self.unit_title.setText('选择阵容中的干员'); self.unit_elite.setChecked(False)
        self.unit_elite.blockSignals(False);self.unit_capacity.blockSignals(False); self.unit_skill.blockSignals(False)
    def set_unit_capacity(self,on):
        u=self.selected_unit()
        if not u:return
        if not on and len(u['equipment'])>2:self.error('先卸下超出两栏的装备');self.select_unit(u['uid']);return
        self.change(lambda s:next(x for x in s['units'] if x['uid']==u['uid']).update(capacity=4 if on else 2),'确认装备容量例外')
    def set_unit_elite(self,value):
        if self.selected_unit(): self.change(lambda s:next(u for u in s['units'] if u['uid']==self.board_uid).update(elite=value,sprite_elite_unknown=False),'修正精锐状态')
    def confirm_unit_elite(self):
        if self.selected_unit():self.set_unit_elite(self.unit_elite.isChecked())
    def detach_sprite(self):
        u=self.selected_unit()
        if not u:return
        def detach(s):
            item=next(x for x in s['units'] if x['uid']==u['uid'])
            s['field_meta'].pop(item.pop('recognition_key',''),None)
            for key in ('sprite_managed','sprite_missing','sprite_rect'):item.pop(key,None)
        self.change(detach,'所选干员改为手动维护')
    def confirm_battle_roster(self):
        if any(u.get('sprite_missing') for u in self.store.state['units']):
            self.notify('请先核对暂不可见的干员：仍在场可改为手动维护，已离场则移除');return
        def confirm(s):s['field_meta']['battle_roster']={'time':time.time(),'source':'手动核对','uncertain':False,'signature':roster_signature(s)}
        self.change(confirm,'确认本回合阵容完整');self.notify('阵容完整性已核对；人员、位置或回合变化后会重新提示')
    def set_unit_skill(self):
        if self.selected_unit(): self.change(lambda s:next(u for u in s['units'] if u['uid']==self.board_uid).update(skill=self.unit_skill.currentData() or ''),'调整技能')
    def move_selected(self):
        u=self.selected_unit()
        if u:self.drop_unit('unit:'+u['uid'],'bench' if u['zone']=='field' else 'field')
    def remove_selected(self):
        u=self.selected_unit()
        if not u:return
        def remove(s):
            s['inventory'].extend(u['equipment']); s['units']=[x for x in s['units'] if x['uid']!=u['uid']]
        self.change(remove,'从助手阵容移除干员（未推算出售收入）')
    def promote_selected(self):
        u=self.selected_unit()
        if not u:return
        actions=validate_actions(self.db,self.store.state,[{'type':'promote','op_id':u['op_id']}])
        if not actions[0]['valid']: self.error(actions[0]['validation']);return
        def promote(s):
            matches=[x for x in s['units'] if x['op_id']==u['op_id'] and not x['elite'] and not x.get('sprite_missing') and not x.get('sprite_elite_unknown')][:promotion_need(self.db,u['op_id'])]
            for x in matches:s['inventory'].extend(x['equipment']);s['units'].remove(x)
            s['units'].append(unit(u['op_id'],u['zone'],True))
        self.change(promote,'记录晋升；装备回收至库存。请在游戏内完成免费三选一。')
    def assign_equipment(self):
        u=self.selected_unit()
        if not u:return
        inv=self.store.state['inventory']
        if not inv:self.error('先在对局工具的“库存与合成”中录入持有装备');return
        name,ok=QInputDialog.getItem(self,'装备分配','选择库存装备',inv,0,False)
        if ok:
            self.change(lambda s:equip_item(self.db,s,u['uid'],name),'分配装备 / 同名自动进阶')
    def remove_equipment(self):
        u=self.selected_unit(); item=self.unit_gear.currentItem()
        if u and item:
            e=item.text();self.change(lambda s:(next(x for x in s['units'] if x['uid']==u['uid'])['equipment'].remove(e),s['inventory'].append(e)),'卸下装备')

    def page_catalog(self):
        self.catalog_search=QLineEdit();self.catalog_search.setPlaceholderText('名称、拼音首字母、效果关键词…')
        self.catalog_core=FilterButtons('核心盟约',[(c['name'],c['name']) for c in self.db.covenants if c['type']=='核心盟约'])
        self.catalog_secondary=FilterButtons('副盟约',[(c['name'],c['name']) for c in self.db.covenants if c['type']=='附加盟约'],'blue')
        self.catalog_category=FilterButtons('干员作用',[(x,x) for x in ['叠层','吃层','经济','战斗辅助']],'gold')
        self.catalog_tier=FilterButtons('等阶',[(f'{i} 阶',i) for i in range(1,7)],exclusive=True)
        self.catalog_filters=[self.catalog_core,self.catalog_secondary,self.catalog_category,self.catalog_tier]
        filters=QWidget();filter_layout=QGridLayout(filters);filter_layout.setContentsMargins(0,0,0,0)
        filter_layout.setHorizontalSpacing(10);filter_layout.setVerticalSpacing(4);filter_layout.setColumnStretch(1,1)
        for i,(title,group) in enumerate(zip(('核心盟约','副盟约','干员作用','等阶'),self.catalog_filters)):
            caption=label(title,'muted');caption.setFixedWidth(66);caption.setMinimumHeight(30)
            filter_layout.addWidget(caption,i,0,Qt.AlignmentFlag.AlignTop);filter_layout.addWidget(group,i,1)
        self.catalog_count=label('','accent');self.catalog_count.setFixedWidth(84)
        self.catalog_count.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        self.catalog_reset=button('重置筛选',self.reset_catalog_filters)
        self.catalog_reset.setFixedWidth(98)
        self.catalog_list=FourColumnList()
        self.catalog_list.currentItemChanged.connect(lambda item,old:self.show_operator(item.data(Qt.ItemDataRole.UserRole)) if item else None)
        self.catalog_detail=CatalogDetails(self.db,self.pixmap,lambda:self.add_unit(self.current_op,'field'),self.add_compare)
        self.operator_name=self.catalog_detail.name;self.operator_art=self.catalog_detail.art
        self.catalog_add=self.catalog_detail.add;self.catalog_compare=self.catalog_detail.compare
        split=QSplitter();split.addWidget(self.catalog_list);split.addWidget(self.catalog_detail);split.setSizes([500,500]);split.setChildrenCollapsible(False)
        self.compare_table=table(['项目']);self.compare_table.setMinimumHeight(180)
        self.catalog_tabs=QTabWidget()
        operators=column(row(self.catalog_search,self.catalog_count,self.catalog_reset),filters,split);operators.layout().setStretch(2,1);operators.layout().setSpacing(7)
        self.catalog_tabs.addTab(operators,'干员');self.catalog_tabs.addTab(column(self.compare_table,button('清空对比',self.clear_compare)),'并排对比')
        for group in self.catalog_filters:group.changed.connect(self.fill_catalog)
        self.catalog_search.textChanged.connect(self.fill_catalog);self.fill_catalog()
        content=column(self.heading('资料图鉴','干员、盟约、装备、策略与指令，在这里统一查阅。'),self.catalog_tabs)
        content.layout().setStretch(1,1)
        content.layout().setSpacing(7);return content
    def reset_catalog_filters(self):
        self.catalog_search.blockSignals(True);self.catalog_search.clear();self.catalog_search.blockSignals(False)
        for group in self.catalog_filters:group.clear(False)
        self.fill_catalog()
    def fill_catalog(self):
        selected=getattr(self,'current_op',None)
        core,secondary,categories,tiers=[group.values() for group in self.catalog_filters]
        matches=[o for o in self.db.search(self.catalog_search.text())
                 if (not core or core.intersection(o['covenants'])) and (not secondary or secondary.intersection(o['covenants']))
                 and (not categories or categories.intersection(o['categories'])) and (not tiers or o['tier'] in tiers)]
        self.catalog_list.setUpdatesEnabled(False);self.catalog_list.blockSignals(True);selection=0
        try:
            self.catalog_list.clear()
            for i,o in enumerate(matches):
                if o['operator_id']==selected:selection=i
                item=QListWidgetItem(QIcon(self.pixmap(o['operator_id'])),f'{o["name"]}\n{o["tier"]}阶 · {o["recruit_cost"]}资金')
                item.setData(Qt.ItemDataRole.UserRole+1,{'name':o['name'],'tier':o['tier'],'cost':o['recruit_cost'],'covenants':o['covenants']})
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);item.setToolTip(o['name']+' / '+' · '.join(o['covenants']));item.setData(Qt.ItemDataRole.UserRole,o['operator_id']);self.catalog_list.addItem(item)
            if matches:self.catalog_list.setCurrentRow(selection)
            self.catalog_list.doItemsLayout()
        finally:
            self.catalog_list.blockSignals(False);self.catalog_list.setUpdatesEnabled(True)
        self.catalog_count.setText(f'{len(matches)} / {len(self.db.ops)} 位')
        self.catalog_reset.setEnabled(bool(self.catalog_search.text() or core or secondary or categories or tiers))
        self.catalog_add.setEnabled(bool(matches));self.catalog_compare.setEnabled(bool(matches))
        if matches:
            if selected!=matches[selection]['operator_id'] or self.operator_art.pixmap().isNull():self.show_operator(matches[selection]['operator_id'])
        else:
            self.current_op=None;self.catalog_detail.set_operator(None)
    def show_operator(self,oid):
        self.current_op=oid;self.catalog_detail.set_operator(self.db.ops[oid])
    def add_compare(self):
        if self.current_op not in self.db.ops:return
        if self.current_op not in self.compare_ids:self.compare_ids.append(self.current_op)
        self.compare_ids=self.compare_ids[-4:];self.refresh_compare();self.notify('已加入并排对比，打开“并排对比”标签查看')
    def clear_compare(self):self.compare_ids=[];self.refresh_compare()
    def refresh_compare(self):
        ops=[self.db.ops[x] for x in self.compare_ids];self.compare_table.setColumnCount(len(ops)+1);self.compare_table.setHorizontalHeaderLabels(['项目']+[o['name'] for o in ops])
        keys=[('等阶','tier'),('招募资金','recruit_cost'),('盟约','covenants'),('初始特质','effect_initial'),('精锐特质','effect_elite'),('推荐技能','recommended_skill'),('理由','recommendation_reason')]
        fill_table(self.compare_table,[[title]+[(' / '.join(o[k]) if isinstance(o[k],list) else o[k]) for o in ops] for title,k in keys]);self.compare_table.resizeRowsToContents()

    def page_covenants(self):
        self.covenant_table=table(['盟约','计数 / 门槛','状态','层数','下一档']);self.covenant_table.setMinimumHeight(280)
        self.covenant_table.itemSelectionChanged.connect(self.show_covenant)
        self.covenant_text=QPlainTextEdit();self.covenant_text.setReadOnly(True)
        self.stack_value=spin(0,0,999999);self.fixed_layers=spin(0,0,999999);self.temp_layers=spin(0,0,999999)
        return column(label('盟约规则与本局进度 · 按实际成员计数，层数可以核对后记录。','muted',True),
            self.covenant_table,row(label('所选盟约层数'),self.stack_value,button('记录层数',self.save_layers),None),
            row(label('乌萨斯固定'),self.fixed_layers,label('临时'),self.temp_layers,button('分别记录',self.save_ursas),None),self.covenant_text)
    def refresh_covenants(self):
        self.covenant_rows=covenant_status(self.db,self.store.state)
        self.covenant_table.blockSignals(True)
        selected=self.covenant_table.currentRow();fill_table(self.covenant_table,[[c['name'],f'{c["count"]}'+(f' +{c["bonus"]}调和' if c['bonus'] else '')+f' / {c["activation_count"]}',
            '待核对（沿用记录）' if c['needs_review'] else '已激活' if c['active'] else ('互斥失效' if c['name']=='独行' and c['count']>=2 else '未激活'),self.store.state['stacks'].get(c['name'],0),c['next'] or '—'] for c in self.covenant_rows])
        self.covenant_table.selectRow(max(0,selected));self.fixed_layers.setValue(self.store.state['ursas_fixed']);self.temp_layers.setValue(self.store.state['ursas_temporary'])
        self.covenant_table.blockSignals(False);self.show_covenant()
    def show_covenant(self):
        idx=self.covenant_table.currentRow()
        if not hasattr(self,'covenant_rows') or idx<0 or idx>=len(self.covenant_rows):return
        c=self.covenant_rows[idx];layers=self.store.state['stacks'].get(c['name'],0)
        if c['name']=='乌萨斯':layers=self.store.state['ursas_fixed']+self.store.state['ursas_temporary']
        self.stack_value.setValue(layers)
        candidates='、'.join(self.db.ops[x]['name'] for x in c['candidates'])
        related=[o for o in self.db.ops.values() if c['name'] in o['covenants'] and any(x in o['categories'] for x in ['叠层','吃层','经济'])]
        lines=[c['name']+'  /  '+('整备区也计数' if c['bench_counts'] else '仅战场计数'),c['membership_rule'],
               '\n原始规则\n'+c['effect'],f'\n代入 {layers} 层（仅替换明确公式，原文所有条件仍需满足）\n'+evaluated_effect(c['effect'],layers),
               '\n补位候选\n'+candidates,'\n相关干员与触发：']
        if c['needs_review']:lines.insert(1,'待核对：当前人数与激活进度沿用最后确认的阵容。')
        for o in related:lines.append(f'{o["name"]} / {" · ".join(o["categories"])}\n初始：{o["effect_initial"]}\n精锐：{o["effect_elite"]}')
        self.covenant_text.setPlainText('\n'.join(lines))
    def save_layers(self):
        idx=self.covenant_table.currentRow()
        if idx>=0:
            name=self.covenant_rows[idx]['name']
            if name=='乌萨斯':self.notify('乌萨斯请在下方分别记录固定与临时层数');return
            self.change(lambda s:s['stacks'].update({name:self.stack_value.value()}),'记录盟约层数')
    def save_ursas(self):self.change(lambda s:s.update(ursas_fixed=self.fixed_layers.value(),ursas_temporary=self.temp_layers.value()),'记录乌萨斯层数')

    def page_equipment(self):
        self.equipment_search=QLineEdit();self.equipment_search.setPlaceholderText('搜索装备名称 / 效果');self.equipment_search.textChanged.connect(self.fill_equipment)
        self.equipment_list=QListWidget();self.equipment_list.currentTextChanged.connect(self.show_equipment)
        self.equipment_description=QPlainTextEdit();self.equipment_description.setReadOnly(True)
        self.inventory_list=QListWidget();self.recipe_table=table(['合成结果','材料 A','材料 B','条件'])
        equipment_split=QSplitter();equipment_split.addWidget(column(self.equipment_search,self.equipment_list))
        equipment_split.addWidget(card('装备效果与获取',self.equipment_description,button('加入持有库存',self.add_inventory),button('管理本局库存',lambda:self.navigate('inventory'))));equipment_split.setSizes([280,700])
        right=column(card('本局库存',self.inventory_list,button('移除所选库存',self.remove_inventory)),card('可合成与缺少材料',self.recipe_table,button('记录合成结果',self.craft,True)))
        self.inventory_page=column(label('本局库存与合成 · 查阅或添加装备请前往图鉴；分配装备请在首页核对阵容。','muted',True),right,button('打开装备图鉴',lambda:self.navigate('equipment')))
        self.fill_equipment();return equipment_split
    def fill_equipment(self):
        self.equipment_list.clear();q=self.equipment_search.text().strip()
        self.equipment_list.addItems([n for n,e in self.db.equipment.items() if q in n+e['effect']])
        if self.equipment_list.count():self.equipment_list.setCurrentRow(0)
    def show_equipment(self,name):
        if name not in self.db.equipment:return
        e=self.db.equipment[name];self.equipment_description.setPlainText(f'{name}  /  {e["tier"]}阶  /  {e["purchase_cost"]}资金\n\n{e["effect"]}\n\n适配判断：依据效果中的攻击、防御、回复与触发条件选择干员；不推算未提供的战斗伤害。\n\n通常每名干员两件装备；策略四栏暴躁铁皮需单独确认。')
    def add_inventory(self):
        item=self.equipment_list.currentItem()
        if item:self.change(lambda s:s['inventory'].append(item.text()),'录入持有装备')
    def remove_inventory(self):
        i=self.inventory_list.currentRow()
        if i>=0:self.change(lambda s:s['inventory'].pop(i),'移除库存记录')
    def refresh_inventory(self):
        self.inventory_list.clear();self.inventory_list.addItems(self.store.state['inventory']);self.recipe_rows=craft_options(self.db,self.store.state['inventory'])
        fill_table(self.recipe_table,[[r['result'],r['component_a'],r['component_b'],'可合成' if r['ready'] else '缺少 '+ '、'.join(r['missing'])] for r in self.recipe_rows])
    def craft(self):
        i=self.recipe_table.currentRow()
        if i<0:return
        r=self.recipe_rows[i]
        if not r['ready']:self.notify('缺少材料，不能记录合成');return
        def change(s):s['inventory'].remove(r['component_a']);s['inventory'].remove(r['component_b']);s['inventory'].append(r['result'])
        self.change(change,'记录装备合成')

    def page_economy(self):
        self.economy_fields={};form=QFormLayout();box=QWidget();box.setLayout(form)
        for key,text in [('gold','当前资金'),('round','当前回合'),('level','调度中心等级'),('upgrade_cost','本次升级费用'),('refresh_cost','本次刷新费用')]:
            w=spin(-1,-1,6 if key=='level' else 9999);w.setSpecialValueText('未知');self.economy_fields[key]=w;form.addRow(text,w)
        self.phase_combo=combo(['未知','开局','整备','作战','结束']);self.carry_check=QCheckBox('已确认本局策略允许结转余额');form.addRow('阶段',self.phase_combo);form.addRow(self.carry_check)
        self.shop_op=combo([(o['name'],o['operator_id']) for o in self.db.ops.values()]);self.shop_op.setEditable(True);self.shop_op.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.shop_cost=spin(-1,-1,999);self.shop_cost.setSpecialValueText('价格未确认')
        self.shop_table=table(['槽位','干员','实际价格','晋升与协同']);self.shop_table.setMinimumHeight(220)
        self.shop_equipment=label('','muted',True)
        self.budget_plan=[];self.budget_table=table(['顺序','计划','核验','结余']);self.budget_table.setMinimumHeight(180)
        self.replacement_text=label('',wrap=True)
        shop=column(row(self.shop_op,self.shop_cost,button('添加商店候选',self.add_shop)),self.shop_table,self.shop_equipment,
            row(button('移除候选',self.remove_shop),button('查看替换影响',self.show_replacement),button('记录三选一候选',self.promotion_reward)),self.replacement_text,
            row(button('计划购买所选',self.plan_buy),button('计划升级',lambda:self.add_plan({'type':'upgrade'})),button('计划刷新',lambda:self.add_plan({'type':'refresh'})),button('清空计划',self.clear_plan)),self.budget_table)
        econ=QSplitter();econ.addWidget(column(card('本局条件',box,button('保存 / 手动锁定这些字段',self.save_economy,True)),label('通常休整期结束后余额不能保留。\n折扣与实际费用请按游戏当前显示填写。','muted',True),None));econ.addWidget(shop);econ.setSizes([280,650])
        self.command_search=QLineEdit();self.command_search.setPlaceholderText('搜索策略 / 指令 / 效果');self.command_search.textChanged.connect(self.fill_commands)
        self.command_list=QListWidget();self.command_list.currentTextChanged.connect(self.show_command)
        self.command_detail=QPlainTextEdit();self.command_detail.setReadOnly(True);self.selected_strategies=QListWidget()
        self.cooldown=QLineEdit();self.cooldown.setPlaceholderText('手动记录冷却状态，例如：剩余 2 回合')
        cmd=QSplitter();cmd.addWidget(column(self.command_search,self.command_list));cmd.addWidget(column(self.command_detail,
            row(button('加入本局策略',self.add_strategy),button('记录一次使用',self.use_command)),row(self.cooldown,button('更新冷却',self.set_cooldown)),
            label('本局已选策略 / 指令','section'),self.selected_strategies,button('从本局移除',self.remove_strategy)))
        self.command_catalog_page=cmd
        self.tools_tabs=QTabWidget();self.tools_tabs.addTab(econ,'商店与资金');self.fill_commands()
        return column(self.heading('对局工具','记录商店、核算资金与管理库存；阵容在首页核对，资料在图鉴查阅。'),self.tools_tabs)
    def save_economy(self):
        def change(s):
            for key,w in self.economy_fields.items():
                s[key]=None if w.value()<0 else w.value();s['field_meta'][key]={'time':time.time(),'source':'手动','locked':w.value()>=0}
            s['phase']=self.phase_combo.currentText();s['carry_gold']=self.carry_check.isChecked()
            s['field_meta']['phase']={'time':time.time(),'source':'手动','locked':s['phase']!='未知'}
        self.change(change,'手动确认回合条件')
    def add_shop(self):
        oid=self.shop_op.currentData()
        if self.shop_op.currentText() in self.db.by_name:oid=self.db.by_name[self.shop_op.currentText()]['operator_id']
        elif self.shop_op.currentText()!=self.shop_op.itemText(self.shop_op.currentIndex()):self.error('请选择数据库中的干员');return
        if not oid:return
        price=None if self.shop_cost.value()<0 else self.shop_cost.value()
        def add(s):
            if len(s['shop'])>=20:raise ValueError('最多记录 20 个商店候选')
            s['shop'].append({'op_id':oid,'cost':price,'slot':max([x.get('slot',i) for i,x in enumerate(s['shop'])],default=-1)+1})
        self.change(add,'录入商店候选')
    def remove_shop(self):
        i=self.shop_table.currentRow()
        if i>=0:self.change(lambda s:s['shop'].pop(i),'移除商店候选')
    def refresh_shop(self):
        s=self.store.state;rank={r['slot']:r for r in recommend(self.db,s,True)}
        fill_table(self.shop_table,[[x.get('slot',i)+1,self.db.ops[x['op_id']]['name'],x['cost'] if x.get('cost') is not None else '待确认',' / '.join(rank.get(i,{'reasons':['等待商店稳定核验']})['reasons'])] for i,x in enumerate(s['shop'])])
        offers=s.get('recognized_offers',{})
        self.shop_equipment.setText('商店装备（尚未购买）：'+ '；'.join(f'槽位 {int(k)+1} · {v["name"]} · {v["cost"] if v.get("cost") is not None else "?"} 资金' for k,v in offers.items()) if offers else '')
        if shop_review_note(s):self.shop_equipment.setText(self.shop_equipment.text()+'\n'+shop_review_note(s))
        for k,w in self.economy_fields.items():
            if k=='upgrade_cost':w.setSpecialValueText('已满级' if s.get('level')==6 else '未知')
            if not w.hasFocus():w.setValue(-1 if s[k] is None else s[k])
        self.phase_combo.setCurrentText(s['phase']);self.carry_check.setChecked(s['carry_gold']);self.refresh_plan()
    def add_plan(self,a):self.budget_plan.append(a);self.refresh_plan()
    def plan_buy(self):
        i=self.shop_table.currentRow()
        if i>=0:self.add_plan({'type':'buy','slot':i,'op_id':self.store.state['shop'][i]['op_id']})
    def clear_plan(self):self.budget_plan=[];self.refresh_plan()
    def refresh_plan(self):
        results=validate_actions(self.db,self.store.state,self.budget_plan)
        fill_table(self.budget_table,[[i+1,{'buy':'购买 '+self.db.ops.get(a.get('op_id'),{}).get('name',''),'upgrade':'升级调度中心','refresh':'刷新商店'}.get(a['type'],a['type']),a['validation'],a['balance_after'] if a['balance_after'] is not None else '未知'] for i,a in enumerate(results)])
    def show_replacement(self):
        i=self.shop_table.currentRow()
        if i<0:return
        oid=self.store.state['shop'][i]['op_id'];opts=replacement_options(self.db,self.store.state,oid)[:4]
        self.replacement_text.setText('\n'.join(f'替换 {o["name"]}：新增 {"、".join(o["gain"]) or "无"}；失去 {"、".join(o["loss"]) or "无"}' for o in opts) or '先在首页的“阵容核对”中录入战场干员')
    def promotion_reward(self):
        names,ok=QInputDialog.getText(self,'晋升免费三选一','输入三个候选名称，以中文逗号或英文逗号分隔')
        if not ok:return
        parts=[x.strip() for x in names.replace('，',',').split(',')]
        if len(parts)!=3 or any(x not in self.db.by_name for x in parts):self.error('请填写三个数据库中的准确干员名称');return
        s=copy.deepcopy(self.store.state);s['shop']=[{'op_id':self.db.by_name[n]['operator_id'],'cost':0} for n in parts]
        result=recommend(self.db,s,True);QMessageBox.information(self,'三选一协同对比','\n\n'.join(f'{i+1}. {r["name"]}\n'+ ' / '.join(r['reasons']) for i,r in enumerate(result)))
    def fill_commands(self):
        self.command_list.clear();q=self.command_search.text();self.command_list.addItems([n for n,c in self.db.commands.items() if q in n+c['effect']+c['initiator']])
        if self.command_list.count():self.command_list.setCurrentRow(0)
    def show_command(self,name):
        if name not in self.db.commands:return
        c=self.db.commands[name];s=self.store.state;active=[x['name'] for x in covenant_status(self.db,s) if x['active']]
        synergy=[x for x in active if x in c['effect']]
        self.command_detail.setPlainText(f'{name}  /  {c["initiator"]}  /  {c["type"]}\n\n{c["effect"]}\n\n初始费用：{c["initial_cost"] if c["initial_cost"] is not None else "不适用"}\n冷却：{c["cooldown"]}\n次数限制：{c["usage_limit"]}\n本局已记使用：{s["command_uses"].get(name,0)}\n当前冷却：{s["command_cooldowns"].get(name,"待确认")}\n\n相关已激活盟约：{"、".join(synergy) or "无直接文字匹配"}\n当前共激活 {len(active)} 种盟约；获得时/叠层增益需依原文判断。')
    def add_strategy(self):
        item=self.command_list.currentItem()
        if item and item.text() not in self.store.state['strategies']:self.change(lambda s:s['strategies'].append(item.text()),'选择策略')
    def use_command(self):
        item=self.command_list.currentItem()
        if item:self.change(lambda s:s['command_uses'].update({item.text():s['command_uses'].get(item.text(),0)+1}),'记录指令使用（资金需核对）')
    def set_cooldown(self):
        item=self.command_list.currentItem()
        if item:self.change(lambda s:s['command_cooldowns'].update({item.text():self.cooldown.text()}),'记录冷却')
    def refresh_strategies(self):
        self.selected_strategies.clear();self.selected_strategies.addItems(self.store.state['strategies'])
        if self.command_list.currentItem():self.show_command(self.command_list.currentItem().text())
    def remove_strategy(self):
        item=self.selected_strategies.currentItem()
        if item:self.change(lambda s:s['strategies'].remove(item.text()),'移除本局策略')

    def page_guides(self):
        self.builtin_guides=[g for g in bundled_guides() if g['route_id'] not in self.db.disabled_guide_routes]
        self.guide_list=QListWidget();self.guide_list.currentRowChanged.connect(self.show_guide)
        self.guide_title=QLineEdit();self.guide_title.setPlaceholderText('攻略名称');self.guide_favorite=QCheckBox('收藏')
        self.guide_text=QTextBrowser();self.guide_text.setOpenExternalLinks(True);self.guide_text.document().setDefaultStyleSheet('a { color: #14dfbb; }')
        self.guide_text.setPlaceholderText('核心干员、替代选择、前期过渡、成型条件、技能装备与操作要点…')
        self.guide_version=label('','muted',True)
        self.guide_delete_button=button('删除攻略线路',self.delete_guide)
        split=QSplitter();split.addWidget(self.guide_list);split.addWidget(column(self.guide_title,self.guide_favorite,self.guide_version,self.guide_text,
            row(button('新建',self.new_guide),button('保存攻略',self.save_guide,True),self.guide_delete_button,button('将本局附为阵容',self.attach_guide_team),button('载入附带阵容',self.load_guide_team))))
        self.fill_guides()
        return column(self.heading('阵容攻略库','已整理攻略按作者与变体保留运营、装备、站位和原链接；自建记录独立保存。'),split)
    def fill_guides(self):
        self.guide_entries=[*self.builtin_guides,*self.storage.guides]
        self.guide_list.clear()
        for g in self.guide_entries:self.guide_list.addItem(('攻略 / ' if g.get('builtin') else '自建 / ')+('★ ' if g['favorite'] else '')+g['name'])
        if self.guide_list.count():self.guide_list.setCurrentRow(0)
        else:self.guide_title.clear();self.guide_text.clear();self.guide_version.clear()
        self.guide_delete_button.setEnabled(bool(self.guide_entries))
    def show_guide(self,i):
        if not 0<=i<len(self.guide_entries):return
        g=self.guide_entries[i];self.guide_title.setText(g['name']);self.guide_favorite.setChecked(g['favorite']);self.guide_version.setText('适用版本 / '+g['version'])
        if g.get('builtin'):
            from .strategy import asset_root
            self.guide_text.document().setBaseUrl(QUrl.fromLocalFile(str(asset_root()/'skill/references/routes')+'/'))
            self.guide_text.setMarkdown(g['text'])
        else:self.guide_text.setPlainText(g['text'])
        self.guide_title.setReadOnly(bool(g.get('builtin')));self.guide_text.setReadOnly(bool(g.get('builtin')));self.guide_favorite.setEnabled(not g.get('builtin'))
    def new_guide(self):
        self.storage.guides.append({'name':'新攻略','text':'','favorite':False,'version':self.db.raw['metadata']['version'],'team':None});self.fill_guides();self.guide_list.setCurrentRow(len(self.guide_entries)-1)
    def delete_guide(self):
        index=self.guide_list.currentRow()
        if not 0<=index<len(self.guide_entries):return
        guide=self.guide_entries[index]
        detail='删除后，该线路不再用于本地或 AI 推荐。已上传的原始攻略文件会保留。' if guide.get('builtin') else '删除后，这份自建攻略及其附带阵容会从攻略库移除。当前对局不受影响。'
        if QMessageBox.question(self,'删除攻略线路','删除「'+guide['name']+'」？\n'+detail)!=QMessageBox.StandardButton.Yes:return
        if guide.get('builtin'):
            self.db.disabled_guide_routes=list(dict.fromkeys([*self.db.disabled_guide_routes,guide['route_id']]))
            self.settings['disabled_guide_routes']=self.db.disabled_guide_routes.copy();self.storage.save_settings()
            self.builtin_guides=[g for g in self.builtin_guides if g['route_id']!=guide['route_id']]
            self.cancel_ai();self.ai_result=None
        else:
            self.storage.guides.pop(index-len(self.builtin_guides));self.storage.save_guides()
        self.fill_guides();self.guide_list.setCurrentRow(min(index,self.guide_list.count()-1));self.refresh_all();self.notify('攻略线路已删除')
    def save_guide(self):
        row_index=self.guide_list.currentRow();i=row_index-len(self.builtin_guides)
        if i<0:return
        self.storage.guides[i].update(name=self.guide_title.text().strip() or '未命名攻略',text=self.guide_text.toPlainText(),favorite=self.guide_favorite.isChecked())
        self.storage.save_guides();self.fill_guides();self.guide_list.setCurrentRow(row_index);self.notify('攻略已保存')
    def attach_guide_team(self):
        i=self.guide_list.currentRow()-len(self.builtin_guides)
        if i>=0:self.storage.guides[i]['team']=copy.deepcopy(self.store.state);self.save_guide()
    def load_guide_team(self):
        i=self.guide_list.currentRow()-len(self.builtin_guides)
        if i>=0 and self.storage.guides[i].get('team'):self.replace_team(self.storage.guides[i]['team'])

    def page_recognition(self):
        self.window_combo=QComboBox();self.window_combo.currentIndexChanged.connect(self.reset_capture)
        self.profile_combo=QComboBox();self.profile_combo.currentIndexChanged.connect(self.select_capture_profile)
        self.recognition_label=label('未连接游戏。建议使用窗口化或无边框窗口。','muted',True)
        self.live_button=button('绑定并同步',self.bind_home_game,True)
        self.auto_apply_check=QCheckBox('连续稳定后自动更新局面');self.auto_apply_check.setChecked(self.settings['auto_apply']);self.auto_apply_check.toggled.connect(self.toggle_auto_apply)
        self.battle_check=QCheckBox('战场小人比对');self.battle_check.setChecked(self.settings['battle_enabled']);self.battle_check.toggled.connect(self.toggle_battle)
        self.canvas=CalibrationCanvas();self.canvas.selected.connect(self.add_region)
        self.recognition_table=table(['区域','识别结果','置信 / 相似度','原文']);self.recognition_table.setMinimumHeight(190)
        self.region_list=QListWidget();self.region_list.setMaximumHeight(150)
        preview=column(self.canvas,row(button('导入截图',self.import_screenshot),button('粘贴截图',self.paste_screenshot),button('截取画面',lambda:self.capture_once(False)),button('识别当前图',self.recognize_current)),self.recognition_label)
        regions=column(label('手动校准','section'),label('默认自动定位，升级后重新寻找卡位。需要修正时可在预览上拖框并保存布局。','muted',True),
            self.region_list,button('移除所选区域',self.remove_region),button('另存布局',self.save_capture_profile),button('解锁全部手动字段',self.unlock_fields),
            button('导出识别诊断',self.export_recognition))
        self.recognition_controls=regions
        regions_scroll=scroll(regions);regions_scroll.setMinimumWidth(250);regions_scroll.setMaximumWidth(330)
        split=QSplitter();split.addWidget(preview);split.addWidget(regions_scroll);split.setSizes([700,300])
        tabs=QTabWidget();tabs.addTab(split,'画面与区域');tabs.addTab(column(self.recognition_table,
            row(button('修正所选结果',self.correct_recognition),button('确认可用结果',self.apply_recognition,True),button('合并已识别装备到库存',self.merge_recognized_inventory)),
            label('置信度是识别模型分数，并非实测准确率。自动更新须达到阈值，并满足对应的连续帧数设置。','muted',True)),'识别结果与校正')
        self.recognition_tabs=tabs
        self.opening_table=table(['盟约图标','状态','识别状态']);self.opening_table.setIconSize(QSize(36,36));self.opening_table.setMinimumWidth(330)
        self.opening_table.cellDoubleClicked.connect(lambda *_:self.correct_opening_icon())
        self.opening_summary=QPlainTextEdit();self.opening_summary.setReadOnly(True);self.opening_summary.setFont(QFont('Microsoft YaHei UI',11))
        self.opening_status=label('等待开局界面','accent',True);self.opening_status.setFixedHeight(32)
        opening_split=QSplitter();opening_split.addWidget(self.opening_table);opening_split.addWidget(self.opening_summary);opening_split.setSizes([360,620])
        self.opening_auto_check=QCheckBox('稳定识别后自动确认开局禁选');self.opening_auto_check.setChecked(self.settings['opening_auto_confirm'])
        self.opening_auto_check.setToolTip('实时识别中生效，独立于“连续稳定后自动更新局面”；不会替你在游戏中选组或准备就绪。')
        self.opening_auto_check.toggled.connect(self.toggle_opening_auto_confirm)
        self.opening_confirm_button=button('确认本局禁选',self.apply_opening,True)
        self.opening_review_button=button('局内重新核对禁选',self.begin_opening_review)
        self.opening_review_cancel=button('返回局面',self.end_opening_review)
        opening_actions=row(button('核对所选图标',self.correct_opening_icon),button('核对当前选组',self.correct_opening_side),self.opening_confirm_button);opening_actions.setFixedHeight(36)
        opening_hint=label('只比对盟约图标与高亮状态。有主核心的干员按主核心判断可用性；无主核心时才按全部附加盟约推算，不比对禁用干员头像。','muted',True);opening_hint.setMaximumHeight(44)
        opening_page=column(self.opening_status,opening_split,row(self.opening_review_button,self.opening_review_cancel),self.opening_auto_check,opening_actions,opening_hint,margin=10);opening_page.layout().setStretch(1,1)
        self.opening_page=opening_page
        self.refresh_windows();self.fill_capture_profiles()
        return column(label('窗口绑定和禁选确认在首页；这里调整布局、核对识别结果。','muted',True),
            row(label('识别布局'),self.profile_combo,button('返回首页绑定',lambda:self.navigate('home'))),row(self.auto_apply_check,self.battle_check),tabs)
    def visible_opening(self):
        track=self.solo_briefing
        def decorate(opening):
            view=copy.deepcopy(opening)
            if not self.review_opening and opening_key(view)==opening_key(self.store.state.get('opening')):
                view['_confirmed']=True;view['_locked']=True
            return view
        if track.result is self.last_recognition and self.last_recognition is not None:
            if track.departed:return None
            if track.opening:
                view=decorate(track.opening)
                if track.locked:
                    view['_locked']=True
                    view['_pending_change']=bool(track.candidate and opening_key(track.candidate)!=opening_key(track.opening))
                elif track.held or track.uncertain:
                    view['_review_message']=track.message or '等待重新核对开局信息'
                    view['_review_blocked']=track.uncertain
                return view
        if (self.last_recognition or {}).get('opening'):return decorate(self.last_recognition['opening'])
        saved=self.store.state.get('opening') if self.store.state['phase']=='开局' else None
        return decorate(saved) if saved else None
    def opening_for_review(self):
        if self.solo_briefing.result is self.last_recognition and self.solo_briefing.opening:return self.solo_briefing.opening
        return (self.last_recognition or {}).get('opening') or self.store.state.get('opening')
    def opening_confirmation(self):
        opening=self.visible_opening();problem=confirmation_problem(self.db,opening)
        if self.review_opening and (not (self.last_recognition or {}).get('opening') or (self.last_recognition['opening'].get('context')!='in_match')):
            return {'visible':True,'enabled':False,'status':'请在游戏内打开本局信息，然后重新读取禁选','bans':'等待完整盟约图标；保留当前对局','button':'等待重新识别'}
        meta=self.store.state['field_meta'].get('opening_snapshot',{})
        confirmed=bool(opening and not self.review_opening and opening_key(opening)==opening_key(self.store.state.get('opening')) and not meta.get('uncertain'))
        side={'left':'左组','right':'右组'}.get((opening or {}).get('selected'),'未选组')
        layout=('单人 · '+side) if (opening or {}).get('mode')=='solo' else '联机 · 固定配置'
        if (opening or {}).get('context')=='in_match':layout='局内信息 · 保留当前对局'
        elif core_unrestricted(opening):layout='核心全部启用 · 无需选组'
        held=bool(opening and opening.get('_review_message'))
        if confirmed:status='已锁定 · '+layout+(' · 新选组核对中' if opening.get('_pending_change') else '')
        elif held:status=opening['_review_message']
        elif opening and opening.get('_locked'):status='预览已锁定 · '+layout+' · 待确认'
        elif problem:status=problem
        elif self.live and self.settings['opening_auto_confirm'] and not (self.last_recognition or {}).get('manual_opening'):status=layout+' · 等待连续稳定，也可直接确认'
        else:status=layout+' · 核对下方禁选后确认'
        bans='\n'.join(title+'：'+ban_summary(opening,kind) for kind,title in (('core','禁选核心'),('additional','禁选附加'))) if opening else ''
        return {'visible':bool(opening),'enabled':bool(opening and not problem and not confirmed and not held),'status':status,'bans':bans,'locked':bool(confirmed or opening and opening.get('_locked')),'button':'本局禁选已锁定' if confirmed else '等待画面稳定' if held else '确认本局禁选'}
    def toggle_opening_auto_confirm(self,on):
        self.settings['opening_auto_confirm']=on;self.storage.save_settings();self.gate.reset();self.solo_briefing.restart_evidence()
        for check in (self.opening_auto_check,self.overlay.opening_auto_check):
            check.blockSignals(True);check.setChecked(on);check.blockSignals(False)
        self.refresh_opening();self.overlay.update_content()
    def refresh_opening(self):
        if not hasattr(self,'opening_table'):return
        self.refresh_home_setup()
        self.opening_review_cancel.setVisible(self.review_opening)
        self.opening_review_button.setText('重新读取禁选' if self.review_opening else '局内重新核对禁选')
        opening=self.opening_for_review();display=copy.deepcopy(opening)
        if display and not self.review_opening and opening_key(display)==opening_key(self.store.state.get('opening')):display['_confirmed']=True
        summary=describe_opening(self.db,display,self.store.state['target'])
        if self.opening_summary.toPlainText()!=summary:self.opening_summary.setPlainText(summary)
        confirmation=self.opening_confirmation();self.opening_confirm_button.setEnabled(confirmation['enabled']);self.opening_confirm_button.setText(confirmation['button'])
        opening_lock_style(self.opening_status,confirmation.get('locked',False))
        if not opening:
            self.opening_status.setText(confirmation['status'] if self.review_opening else '等待开局或局内信息界面');self.opening_table.setRowCount(0);self.opening_table_signature=None;return
        observed={e['name']:e for e in opening['core']+opening['additional']}
        matches={e['name']:e for e in (self.last_recognition or {}).get('icon_matches',[])}
        self.opening_status.setText(f'核心 {len(opening["core"])}/10 · 附加 {len(opening["additional"])}/16 · '+confirmation['status'])
        locked=bool((self.visible_opening() or {}).get('_locked') or (not self.review_opening and opening_key(opening)==opening_key(self.store.state.get('opening'))))
        signature=(opening_key(opening),locked)
        if getattr(self,'opening_table_signature',None)==signature:return
        self.opening_table_signature=signature
        scroll_pos=self.opening_table.verticalScrollBar().value();selected=self.opening_table.currentRow()
        if not hasattr(self,'opening_icon_paths'):
            data=json.loads((opening_assets()/'index.json').read_text('utf8'))
            self.opening_icon_paths={r['name']:r['file'] for r in reversed(data['references']) if r['kind']!='anchor'}
        rows=[]
        for cv in self.db.covenants:
            e=observed.get(cv['name'],{});match=matches.get(cv['name'])
            rows.append([cv['name'],{'lit':'启用 / 亮','grey':'禁选 / 灰','unknown':'待确认'}[e.get('state','unknown')],'已锁定' if locked else f'{match["similarity"]:.1%}' if match else '待核对'])
        fill_table(self.opening_table,rows)
        for i,cv in enumerate(self.db.covenants):
            item=self.opening_table.item(i,0);item.setData(Qt.ItemDataRole.UserRole,cv['name'])
            path=self.opening_icon_paths.get(cv['name'])
            if path:
                item.setIcon(QIcon(QPixmap(str(opening_assets()/path))))
        if selected>=0:self.opening_table.selectRow(selected)
        self.opening_table.verticalScrollBar().setValue(scroll_pos)
    def correct_opening_icon(self):
        opening=self.opening_for_review();index=self.opening_table.currentRow()
        if not opening or index<0:return
        name=self.opening_table.item(index,0).data(Qt.ItemDataRole.UserRole)
        kind='core' if next(c for c in self.db.covenants if c['name']==name)['type']=='核心盟约' else 'additional'
        if kind=='core' and opening['mode']=='solo' and not core_unrestricted(opening):self.correct_opening_side();return
        value,ok=QInputDialog.getItem(self,'核对盟约图标',name+' 的图标状态',['启用 / 亮','禁选 / 灰','待确认'],0,False)
        if not ok:return
        draft=copy.deepcopy(opening);draft[kind]=[e for e in draft[kind] if e['name']!=name]+[{'name':name,'state':{'启用 / 亮':'lit','禁选 / 灰':'grey','待确认':'unknown'}[value]}]
        self.set_opening_draft(draft)
    def correct_opening_side(self):
        opening=self.opening_for_review()
        if not opening or opening['mode']!='solo' or core_unrestricted(opening):self.notify('当前信息无需左右选组，可直接核对盟约图标');return
        value,ok=QInputDialog.getItem(self,'核对游戏当前选择','仅记录游戏中的实际选择，不会点击游戏',['左组','右组'],0,False)
        if not ok:return
        side='left' if value=='左组' else 'right';draft=copy.deepcopy(opening);draft['selected']=side
        draft['core']=[{'name':name,'state':'lit' if group==side else 'grey'} for group,names in draft['groups'].items() for name in names]
        self.set_opening_draft(draft)
    def set_opening_draft(self,draft):
        recompute_opening(self.db,draft)
        self.solo_briefing.reset()
        self.last_recognition={**(self.last_recognition or {}),'opening':draft,'fields':[],'mode':'opening','icon_matches':[],'manual_opening':True}
        self.gate.reset();self.refresh_opening();self.refresh_home();self.overlay.update_content();self.notify('已修正预览，点击“确认本局禁选”后生效')
    def begin_opening_review(self):
        self.review_opening=True;self.capture_generation+=1;self.gate.reset();self.battle_gate.reset();self.solo_briefing.reset();self.last_recognition=None
        self.clear_shop_tracking();self.refresh_opening();self.overlay.update_content()
        self.notify('请在游戏内打开本局信息；此次核对保留阵容、装备、回合与资金')
        self.capture_opening_review()
    def capture_opening_review(self):
        if not self.review_opening:return
        if self.capture_busy:QTimer.singleShot(150,self.capture_opening_review);return
        self.capture_once()
    def end_opening_review(self):
        self.review_opening=False;self.capture_generation+=1;self.gate.reset();self.battle_gate.reset();self.solo_briefing.reset();self.last_recognition=None
        self.refresh_opening();self.refresh_home();self.overlay.update_content()
    def prepare_opening_session(self,opening):
        if opening.get('context')=='in_match':return
        if self.store.state['phase']!='开局' and (self.store.state['units'] or self.store.state['shop'] or self.store.state['round'] is not None):
            result=self.last_recognition;live=self.live;target=self.store.state['target']
            self.new_session();self.store.state['target']=target;self.last_recognition=result;self.live=live
            self.live_button.setText('暂停实时识别' if live else '开始实时识别')
    def apply_opening(self):
        if (self.visible_opening() or {}).get('_review_message'):
            self.notify('当前展示的是保留结果，请等待画面稳定或在主窗口重新核对');return
        opening=self.opening_for_review()
        if not opening:return
        self.confirm_opening(opening,manual=True)
    def confirm_opening(self,opening,manual=False,confidence=.97):
        problem=confirmation_problem(self.db,opening)
        if problem:self.notify(problem);return False
        meta=self.store.state['field_meta'].get('opening_snapshot',{})
        if not self.review_opening and opening_key(opening)==opening_key(self.store.state.get('opening')) and not meta.get('uncertain'):return False
        self.prepare_opening_session(opening)
        opening=recompute_opening(self.db,copy.deepcopy(opening))
        field={'key':'opening_snapshot','value':json.dumps(opening,ensure_ascii=False,sort_keys=True),'confidence':1 if manual else confidence}
        self.cancel_ai();self.ai_result=None;self.auto_keys.clear()
        self.change(lambda s:apply_fields(s,[field],manual),'手动确认本局禁选' if manual else '稳定识别后自动确认本局禁选')
        if opening['mode'] in ('solo','fixed','coop'):self.solo_briefing.seed(opening)
        self.review_opening=False
        self.overlay.update_content();self.refresh_opening()
        self.notify(('本局禁选已确认' if manual else '本局禁选已自动确认')+'；本地推荐已更新')
        return True
    def receive_opening(self,result,stable,before):
        # Briefing confirmation is independent of tactical auto-apply. An old
        # capture cannot override a user edit made while recognition was running.
        if before!=fingerprint(self.store.state):
            self.refresh_opening();self.refresh_home();self.overlay.update_content();return
        opening=result['opening'];field=next((f for f in stable if f['key']=='opening_snapshot'),None)
        if self.live and self.settings['opening_auto_confirm'] and not result.get('manual_opening') and field and not confirmation_problem(self.db,opening):
            if opening_key(json.loads(field['value']))==opening_key(opening) and self.confirm_opening(opening,confidence=field['confidence']):return
        meta=self.store.state['field_meta'].get('opening_snapshot',{})
        tracked=self.solo_briefing.result is self.last_recognition and self.solo_briefing.opening is not None
        uncertain=(self.solo_briefing.conflict and not self.solo_briefing.locked) if tracked else bool(confirmation_problem(self.db,opening) or opening_key(opening)!=opening_key(self.store.state.get('opening')))
        if self.store.state.get('opening') and uncertain:
            self.store.state['field_meta']['opening_snapshot']={**meta,'uncertain':True}
        self.refresh_all()
    def refresh_windows(self):
        if not hasattr(self,'window_combo'):return
        previous=self.window_combo.currentData();selected=0
        self.window_combo.blockSignals(True);self.window_combo.clear();self.window_combo.addItem('选择游戏 / 模拟器窗口',None)
        for w in enum_windows():
            self.window_combo.addItem(f'{w["title"]} · PID {w["pid"]}',w)
            if previous and (w['hwnd'],w['pid'])==(previous['hwnd'],previous['pid']):selected=self.window_combo.count()-1
        self.window_combo.setCurrentIndex(selected)
        self.window_combo.blockSignals(False)
        if previous and not selected:self.reset_capture()
        self.refresh_home_setup()
    def reset_capture(self):
        self.capture_generation+=1;self.gate.reset();self.battle_gate.reset();self.live=False;self.last_recognition=None
        self.review_opening=False
        self.solo_briefing.reset()
        self.clear_shop_tracking()
        stop_capture()
        if hasattr(self,'canvas'):self.canvas.detected_regions=[];self.canvas.update()
        if hasattr(self,'live_button'):self.live_button.setText('开始实时识别')
        self.refresh_home_setup()
    def fill_capture_profiles(self):
        self.profile_combo.blockSignals(True);self.profile_combo.clear();self.profile_combo.addItem('官方 PC · 自动定位','')
        for p in self.settings['capture_profiles']:self.profile_combo.addItem(p['name'],p['id'])
        self.profile_combo.setCurrentIndex(max(0,self.profile_combo.findData(self.settings['capture_profile'])));self.profile_combo.blockSignals(False);self.select_capture_profile()
    def active_profile(self):
        return next((p for p in self.settings['capture_profiles'] if p['id']==self.settings['capture_profile']),{'id':'','name':'未保存','regions':self.canvas.regions})
    def select_capture_profile(self):
        self.reset_capture();self.settings['capture_profile']=self.profile_combo.currentData() or ''
        p=next((p for p in self.settings['capture_profiles'] if p['id']==self.settings['capture_profile']),{'regions':[]})
        self.canvas.regions=copy.deepcopy(p['regions']);self.fill_regions();self.storage.save_settings()
    def fill_regions(self):
        self.region_list.clear();self.region_list.addItems([r['key']+(' [头像]' if r.get('avatar') else '') for r in self.canvas.regions]);self.canvas.update()
    def add_region(self,rect):
        options=['战场比对范围','整备比对范围','商店干员','战场干员','整备区干员','资金','回合','调度中心等级','升级费用','刷新费用','阶段','盟约层数','乌萨斯固定层','乌萨斯临时层','装备名称','策略名称','商店实际价格','精锐状态']
        kind,ok=QInputDialog.getItem(self,'标注识别区域','这块区域显示什么？',options,0,False)
        if not ok:return
        mapping={'商店干员':'shop','战场干员':'field','整备区干员':'bench','商店实际价格':'cost','装备名称':'equipment','策略名称':'strategy'}
        avatar=False
        if kind in ('战场比对范围','整备比对范围'):
            key='battle_field' if kind=='战场比对范围' else 'battle_bench'
        elif kind in mapping:
            index,ok=QInputDialog.getInt(self,'槽位编号','从左到右 / 从上到下编号（1 起始）',1,1,40)
            if not ok:return
            key=f'{mapping[kind]}:{index-1}'
            if kind in ('商店干员','战场干员','整备区干员'):
                mode,ok=QInputDialog.getItem(self,'识别方式','框内主要内容',['名称文字（推荐）','完整方形头像（严格相似度）'],0,False)
                if not ok:return
                avatar=mode.startswith('完整')
        elif kind=='盟约层数':
            name,ok=QInputDialog.getItem(self,'选择盟约','盟约', [c['name'] for c in self.db.covenants],0,False)
            if not ok:return
            key='stack:'+name
        elif kind=='精锐状态':
            zone,ok=QInputDialog.getItem(self,'所属区域','状态属于哪个区域？',['field','bench'],0,False)
            if not ok:return
            index,ok=QInputDialog.getInt(self,'槽位编号','与干员区域保持相同编号',1,1,40)
            if not ok:return
            key=f'elite:{zone}:{index-1}'
        else:key=next(k for k,v in LABELS.items() if v==kind)
        self.canvas.regions=[r for r in self.canvas.regions if r['key']!=key]+[{'key':key,'rect':rect,'avatar':avatar}]
        self.reset_capture();self.fill_regions();self.notify('区域已添加，请另存布局以持久保存')
    def remove_region(self):
        idx=self.region_list.currentRow()
        if idx>=0:self.canvas.regions.pop(idx);self.reset_capture();self.fill_regions()
    def save_capture_profile(self):
        if self.frame is None:self.error('先载入一张游戏画面');return
        name,ok=QInputDialog.getText(self,'保存布局','布局名称（建议包含客户端、分辨率与界面）',text=self.active_profile().get('name','官方 PC 端'))
        if not ok or not name.strip():return
        h,w=self.frame.shape[:2];pid=str(uuid.uuid4());self.settings['capture_profiles'].append({'id':pid,'name':name.strip(),'regions':copy.deepcopy(self.canvas.regions),'aspect':w/h,'reference_size':[w,h]})
        self.settings['capture_profile']=pid;self.storage.save_settings();self.fill_capture_profiles();self.notify('识别布局已保存；同宽高比下按比例适配尺寸')
    def toggle_auto_apply(self,on):self.settings['auto_apply']=on;self.storage.save_settings();self.gate.reset();self.battle_gate.reset();self.refresh_home_setup()
    def toggle_battle(self,on):
        self.settings['battle_enabled']=on;self.storage.save_settings();self.reset_capture()
        if not on:
            mark_missing(self.store.state,set());self.refresh_all()
    def unlock_fields(self):
        for meta in self.store.state['field_meta'].values():meta['locked']=False
        self.storage.save_state(self.store.state);self.notify('已解除手动锁定，后续可靠识别可更新这些字段')
    def set_frame(self,frame,preserve_tracking=False):
        if not preserve_tracking:self.clear_shop_tracking()
        self.frame=frame;rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB);h,w=rgb.shape[:2]
        image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy();self.canvas.set_image(QPixmap.fromImage(image))
    def import_screenshot(self):
        path,_=QFileDialog.getOpenFileName(self,'导入游戏截图','','图片 (*.png *.jpg *.jpeg *.bmp *.webp)')
        if not path:return
        try:
            from PIL import Image
            with Image.open(path) as im:
                if im.width*im.height>36_000_000:raise ValueError('截图过大，请使用单个游戏窗口截图')
                frame=cv2.cvtColor(np.array(im.convert('RGB')),cv2.COLOR_RGB2BGR)
            self.reset_capture();self.set_frame(frame);self.recognize_current()
        except Exception as e:self.error(str(e))
    def paste_screenshot(self):
        img=QApplication.clipboard().image()
        if img.isNull():self.notify('剪贴板没有图片');return
        img=img.convertToFormat(QImage.Format.Format_RGB888);arr=np.frombuffer(img.bits(),np.uint8).reshape(img.height(),img.bytesPerLine())[:,:img.width()*3].reshape(img.height(),img.width(),3)
        self.reset_capture();self.set_frame(cv2.cvtColor(arr,cv2.COLOR_RGB2BGR));self.recognize_current()
    def capture_once(self,recognize=True):
        if self.capture_busy:self.notify('上一帧仍在处理中');return
        if self.battle_busy and not self.live:self.notify('上次战场比对尚未结束，请稍后重试');return
        target=self.window_combo.currentData()
        if not target:self.notify('请先在“画面识别”中选择游戏窗口');return
        self.capture_busy=True;gen=self.capture_generation;before=fingerprint(self.store.state);profile=copy.deepcopy(self.active_profile());profile['regions']=copy.deepcopy(self.canvas.regions);profile['battle_enabled']=self.settings['battle_enabled']
        profile['opening_review']=self.review_opening;profile['in_match']=self.store.state['phase'] in ('整备','作战')
        defer_battle=bool(self.live and recognize and profile['battle_enabled'])
        before_hud=fingerprint({**self.store.state,'units':[]});before_roster=roster_signature(self.store.state)
        def work():
            frame=capture_window(target['hwnd'],target['pid'],keep_alive=self.live);captured=time.monotonic()
            result=self.recognizer.recognize(frame,{**profile,'battle_enabled':False} if defer_battle else profile) if recognize else None
            if result is not None:result['capture_source']={'hwnd':target['hwnd'],'pid':target['pid'],'captured':captured,'size':[frame.shape[1],frame.shape[0]]}
            return frame,result
        def result(payload):
            if gen!=self.capture_generation:return
            frame,res=payload;self.set_frame(frame,preserve_tracking=bool(self.live and res))
            if res:
                if defer_battle:update_roster_status(self.store.state)
                # Concurrent sprite completion changes the roster, not the HUD.
                # Do not discard an otherwise current shop result for that reason.
                hud_only=defer_battle and not any(f['key'].startswith(('field:','bench:','elite:','gear:','sprite:')) for f in res['fields'])
                expected=fingerprint(self.store.state) if hud_only and before_hud==fingerprint({**self.store.state,'units':[]}) else before
                self.receive_recognition(res,expected)
                if defer_battle and before_roster==roster_signature(self.store.state):self.queue_battle_recognition(frame,res,profile)
        def failure(message):
            if gen!=self.capture_generation:return
            self.capture_generation+=1;self.battle_gate.reset()
            self.clear_shop_tracking()
            self.recognition_status=('等待游戏画面恢复 · 自动重试 / ' if self.live else '截取未完成 / ')+message;self.recognition_label.setText(self.recognition_status);self.gate.reset();self.notify(message)
            if self.live and self.solo_briefing.opening:
                gap={'fields':[]};self.solo_briefing.observe(self.db,gap,self.settings['recognition_threshold'],self.settings['opening_stable_frames']);self.last_recognition=gap
            mark_uncertain(self.store.state,[{'key':k,'value':None,'confidence':0} for k in ('gold','round','phase','shop_snapshot')],self.settings['recognition_threshold'])
            if self.settings['battle_enabled']:mark_missing(self.store.state,set());update_roster_status(self.store.state)
            self.refresh_home();self.overlay.update_content()
        self.run_job(work,result,failure,lambda:setattr(self,'capture_busy',False))
    def queue_battle_recognition(self,frame,result,profile):
        # The slow sprite task must neither hold the shop queue nor count the
        # same HUD observation twice. Only one sprite task may be in flight.
        if self.battle_busy or not self.live or not self.settings['battle_enabled'] or result.get('opening') or self.review_opening:return
        self.battle_busy=True;gen=self.capture_generation;session=self.store.state['session_id']
        signature=roster_signature(self.store.state);source_time=result['time'];source_fields={f['key']:f['value'] for f in result['fields']}
        def current():
            return (gen==self.capture_generation and self.live and self.settings['battle_enabled']
                    and session==self.store.state['session_id'] and signature==roster_signature(self.store.state)
                    and time.time()-source_time<10 and not self.review_opening
                    and all(source_fields.get(k) is None or source_fields[k]==self.store.state[k] for k in ('round','phase')))
        def receive(battle):
            if not current():return
            fields=battle['fields'];stable=self.battle_gate.accept(fields,self.settings['recognition_threshold'])
            if self.settings['auto_apply']:
                mark_missing(self.store.state,{f['key'] for f in stable});apply_fields(self.store.state,stable);update_roster_status(self.store.state)
                self.store.state['revision']+=1;self.store.state['updated_at']=time.time();self.refresh_all()
            # Never draw delayed sprite boxes over a newer, unrelated image.
            if self.last_recognition and self.last_recognition['time']==source_time:
                self.last_recognition={**self.last_recognition,'battlefield':battle['battlefield'],
                    'fields':self.last_recognition['fields']+fields,'regions':self.last_recognition['regions']+battle['regions']}
                self.canvas.detected_regions=self.last_recognition['regions'];self.canvas.update()
            self.maybe_auto_analyze()
        def failed(message):
            if not current():return
            self.battle_gate.reset();mark_missing(self.store.state,set());update_roster_status(self.store.state);self.refresh_all()
            self.notify('战场比对暂未完成；商店识别继续，阵容沿用上次记录')
        self.run_job(lambda:self.recognizer.recognize_battle(frame,result,profile),receive,failed,lambda:setattr(self,'battle_busy',False))
    def recognize_current(self):
        if self.frame is None:self.notify('先载入或截取画面');return
        if self.capture_busy:self.notify('上一帧仍在处理中');return
        if self.battle_busy:self.notify('上次战场比对尚未结束，请稍后重试');return
        self.capture_busy=True;gen=self.capture_generation;before=fingerprint(self.store.state);frame=self.frame.copy();profile=copy.deepcopy(self.active_profile());profile['regions']=copy.deepcopy(self.canvas.regions);profile['battle_enabled']=self.settings['battle_enabled']
        profile['opening_review']=self.review_opening;profile['in_match']=self.store.state['phase'] in ('整备','作战')
        self.recognition_label.setText('正在离线识别，首次加载模型需要一些时间…')
        self.run_job(lambda:self.recognizer.recognize(frame,profile),lambda r:self.receive_recognition(r,before) if gen==self.capture_generation else None,
                     lambda msg:(self.recognition_label.setText(msg),self.notify(msg)),lambda:setattr(self,'capture_busy',False))
    def receive_recognition(self,result,before):
        # Tracking follows this capture, independently of edits to tactical state.
        self.shop_watch.accept(self.db,result,self.settings['recognition_threshold'],self.settings['shop_stable_frames'],self.frame)
        self.watch_source=result.get('capture_source');self.tracking_frame=self.frame.copy() if self.frame is not None else None
        self.refresh_shop_matches()
        if before!=fingerprint(self.store.state):return
        entering_opening=bool(result.get('opening')) and not bool(self.visible_opening())
        self.last_recognition=result;fields=result['fields'];threshold=self.settings['recognition_threshold']
        self.canvas.detected_regions=result.get('regions',[]);self.canvas.update()
        fill_table(self.recognition_table,[[field_label(f['key']),f['label'],f'{f["confidence"]:.1%} · {f["method"]}',f['raw']] for f in fields])
        good=sum(f['value'] is not None and f['confidence']>=threshold for f in fields)
        stamp=datetime.datetime.fromtimestamp(result['time']).strftime('%H:%M:%S')
        self.recognition_status=f'{stamp} 更新 · {result["elapsed_ms"]} ms · 可用 {good}/{len(fields)} 区域'
        self.recognition_status+=' · '+('开局图标' if result.get('mode')=='opening' else '自动定位' if result.get('mode')=='auto' else '手动布局')
        if result.get('notes'):self.recognition_status+=' · '+'；'.join(result['notes'])
        self.recognition_label.setText(self.recognition_status)
        stable=self.gate.accept(fields,threshold)
        if self.live:
            prior=self.store.state.get('opening')
            if not self.review_opening and not self.solo_briefing.opening and not self.solo_briefing.departed and prior and prior['mode'] in ('solo','fixed','coop') and self.store.state['phase']=='开局':self.solo_briefing.seed(prior)
            if self.solo_briefing.observe(self.db,result,threshold,self.settings['opening_stable_frames']):
                if entering_opening:self.open_home_tab('bans',False)
                accepted=[self.solo_briefing.ready_field] if self.solo_briefing.ready_field else []
                self.receive_opening({**result,'opening':self.solo_briefing.opening},accepted,before);return
        else:self.solo_briefing.reset()
        if result.get('opening'):
            if entering_opening:self.open_home_tab('bans',False)
            self.receive_opening(result,stable,before);return
        if self.live and self.settings['auto_apply'] and before==fingerprint(self.store.state):
            stable_values={f['key']:f['value'] for f in stable}
            if stable_values.get('round')==1 and stable_values.get('phase')=='整备' and (self.store.state['round'] or 0)>1:
                self.new_session();self.live=True;self.live_button.setText('暂停实时识别');self.last_recognition=result
                self.notify('检测到新对局，上一局已归档并清空')
            s=self.store.state;old=fingerprint(s);mark_uncertain(s,fields,threshold)
            if result.get('battlefield') is not None:mark_missing(s,{f['key'] for f in stable})
            apply_fields(s,applicable_fields(result,stable))
            if result.get('battlefield') is not None:update_roster_status(s)
            # A changed or uncertain required slot immediately prevents automatic online analysis.
            accepted={f['key'] for f in stable}
            for f in fields:
                if f['key'] not in accepted and not s['field_meta'].get(f['key'],{}).get('locked'):
                    s['field_meta'].setdefault(f['key'],{})['uncertain']=True
            if 'shop_snapshot' in {f['key'] for f in fields} and 'shop_snapshot' not in accepted:
                mark_uncertain(s,[{'key':'shop_snapshot','value':None,'confidence':0}],threshold)
            if fingerprint(s)!=old:
                s['revision']+=1;s['updated_at']=time.time();s['events']=(s['events']+[{'time':time.time(),'text':'画面稳定后更新已确认字段'}])[-30:]
                self.refresh_all()
            else:self.storage.save_state(s);self.refresh_home();self.overlay.update_content()
            self.maybe_auto_analyze()
        else:self.refresh_home();self.overlay.update_content()
    def correct_recognition(self):
        i=self.recognition_table.currentRow()
        if not self.last_recognition or i<0 or i>=len(self.last_recognition['fields']):return
        f=self.last_recognition['fields'][i]
        if f['key']=='opening_snapshot':self.open_home_tab('bans');self.notify('请在“开局禁选”核对图标或当前选组');return
        if f['key']=='shop_snapshot':self.notify('请修正具体商品；整体核验由下一帧重新计算');return
        text,ok=QInputDialog.getText(self,'修正识别','输入准确名称、数字或阶段（整备 / 作战 / 结束）',text=str(f['label']))
        if not ok:return
        key=f['key'];value=text.strip()
        try:
            if key.startswith('sprite:'):
                oid=self.db.by_name[value]['operator_id'];f['detection']['op_id']=oid;f['detection']['name']=value;f['detection']['reliable']=True
                value=f'{oid}|{f["detection"]["zone"]}'
            elif key.startswith(('shop:','field:','bench:')):value=self.db.by_name[value]['operator_id']
            elif key.startswith(('equipment:','offer:')):
                if value not in self.db.equipment:raise ValueError()
            elif key.startswith('strategy:'):
                if value not in self.db.commands:raise ValueError()
            elif key.startswith('elite:'):
                if value not in ('精锐','初始'):raise ValueError()
                value=value=='精锐'
            elif key=='phase':
                if value not in ('整备','作战','结束'):raise ValueError()
            else:
                value=int(value)
                if value<0 or value>99999:raise ValueError()
            f.update(value=value,label=text,confidence=1,method='手动修正');self.recognition_table.item(i,1).setText(text);self.recognition_table.item(i,2).setText('手动修正')
            if self.last_recognition.get('mode')=='auto' and key.startswith(('shop:','cost:','offer:')):
                for whole in self.last_recognition['fields']:
                    if whole['key']=='shop_snapshot':whole.update(value=None,label='商品已手动修正，等待重新核验',confidence=0)
            self.change(lambda s:(apply_fields(s,[f],True),s['field_meta'][key].update(locked=True)),'手动校正识别并锁定字段')
        except (KeyError,ValueError):self.error('输入不符合此区域的数据类型')
    def apply_recognition(self):
        if not self.last_recognition:return
        if self.last_recognition.get('opening'):self.apply_opening();return
        fields=[f for f in self.last_recognition['fields'] if f['value'] is not None and f['confidence']>=self.settings['recognition_threshold']]
        fields=applicable_fields(self.last_recognition,fields)
        def apply(s):
            if self.last_recognition.get('battlefield') is not None:mark_missing(s,{f['key'] for f in fields})
            apply_fields(s,fields,True)
            if self.last_recognition.get('battlefield') is not None:update_roster_status(s)
        self.change(apply,'手动确认识别结果');self.notify('已应用可用结果；小人比对可能不完整，请在首页的“阵容核对”中补齐并确认')
    def export_recognition(self):
        if self.frame is None or not self.last_recognition:self.notify('请先识别一帧游戏画面');return
        folder=QFileDialog.getExistingDirectory(self,'选择诊断保存位置')
        if not folder:return
        try:
            dest=Path(folder)/('卫戍识别诊断-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));dest.mkdir()
            cv2.imencode('.png',self.frame)[1].tofile(str(dest/'游戏画面.png'))
            payload={'version':__version__,'result':self.last_recognition,'manual_regions':self.canvas.regions}
            (dest/'识别结果.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            self.notify('诊断已保存：'+str(dest))
        except Exception as e:self.error('诊断保存失败：'+str(e))
    def merge_recognized_inventory(self):
        values=list(self.store.state.get('recognized_inventory',{}).values())
        if not values:self.notify('尚未识别到装备名称');return
        self.change(lambda s:(s.update(inventory=values),s.update(recognized_inventory={})),'以确认的装备区域替换库存记录')
    def toggle_live(self):
        self.capture_generation+=1
        if not self.live:
            if not self.window_combo.currentData():self.error('请先选择官方 PC 端窗口');return
            self.gate.reset();self.battle_gate.reset();self.solo_briefing.reset();self.last_capture=0
        self.live=not self.live;self.live_button.setText('暂停实时识别' if self.live else '开始实时识别');self.overlay.update_content()
        if not self.live:stop_capture();self.clear_shop_tracking()
        self.refresh_home_setup()
    def tick(self):
        self.update_shop_highlight()
        if self.live and not self.capture_busy and time.monotonic()-self.last_capture>=self.settings['capture_interval']:
            self.last_capture=time.monotonic();self.capture_once()

    def page_coach(self):
        self.ai_toggle=QCheckBox('启用 AI 回合教练（独立开关）');self.ai_toggle.toggled.connect(self.toggle_ai)
        self.ai_auto=QCheckBox('整备开始且局面稳定后自动分析');self.ai_auto.setChecked(self.settings['ai_auto'])
        self.ai_change=QCheckBox('局面改变后自动更新（受调用间隔限制）');self.ai_change.setChecked(self.settings['ai_on_change'])
        self.ai_profile_combo=QComboBox();self.ai_profile_combo.currentIndexChanged.connect(self.select_ai_profile)
        self.api_delete_button=button('删除配置',self.delete_api_profile)
        self.api_name=QLineEdit();self.api_url=QLineEdit();self.api_url.setPlaceholderText('https://你的服务地址/v1')
        self.api_model=QLineEdit();self.api_model.setPlaceholderText('服务商提供的模型名称')
        self.api_key=QLineEdit();self.api_key.setEchoMode(QLineEdit.EchoMode.Password);self.api_key.setPlaceholderText('仅保存在本机当前 Windows 账户；留空保留已存密钥')
        self.api_input_price=QDoubleSpinBox();self.api_output_price=QDoubleSpinBox()
        for w in (self.api_input_price,self.api_output_price):w.setRange(0,100000);w.setDecimals(4)
        form=QFormLayout();formbox=QWidget();formbox.setLayout(form)
        for title,w in [('配置名称',self.api_name),('API 地址',self.api_url),('模型名称',self.api_model),('API 密钥',self.api_key),('每百万输入价格（自定币种）',self.api_input_price),('每百万输出价格（同币种）',self.api_output_price)]:form.addRow(title,w)
        self.ai_status=label('AI 关闭 · 本地推荐始终可用','accent',True);self.ai_usage=label('','muted',True)
        self.ai_output=QPlainTextEdit();self.ai_output.setReadOnly(True);self.ai_output.setMinimumHeight(170)
        self.ai_pins=TrackingChoices(self.toggle_tracking,True,self.open_tracking);self.ai_choices=TrackingChoices(self.toggle_tracking,bulk=self.track_recommended_formation)
        self.ai_sources=label('','muted',True);self.ai_sources.setTextFormat(Qt.TextFormat.RichText);self.ai_sources.setOpenExternalLinks(True)
        settings=column(row(self.ai_profile_combo,button('新配置',self.new_api_profile),self.api_delete_button),formbox,row(button('保存配置',self.save_api_profile,True),button('测试连接',lambda:self.analyze(test=True))),self.ai_usage,
            label('启用后只向所配置服务发送当前局面与相关规则。截图与密钥不会进入阵容分享文件。兼容 Chat Completions 接口。','muted',True),None)
        self.ai_route_lock=RouteLockControl(self)
        result=column(self.ai_pins,self.ai_status,self.ai_route_lock,self.ai_output,self.ai_sources,self.ai_choices,row(button('立即分析',self.analyze,True),button('深入分析',lambda:self.analyze(deep=True)),button('取消请求',self.cancel_ai)))
        result.layout().setStretch(3,1)
        self.ai_results_page=result
        self.fill_ai_profiles()
        self.ai_auto.toggled.connect(lambda on:self.set_setting('ai_auto',on));self.ai_change.toggled.connect(lambda on:self.set_setting('ai_on_change',on))
        return settings
    def set_setting(self,key,value):self.settings[key]=value;self.storage.save_settings()
    def fill_ai_profiles(self):
        self.ai_profile_combo.blockSignals(True);self.ai_profile_combo.clear();self.ai_profile_combo.addItem('选择 API 配置','')
        for p in self.settings['ai_profiles']:self.ai_profile_combo.addItem(p['name'],p['id'])
        self.ai_profile_combo.setCurrentIndex(max(0,self.ai_profile_combo.findData(self.settings['ai_profile'])));self.ai_profile_combo.blockSignals(False);self.select_ai_profile()
    def select_ai_profile(self):
        pid=self.ai_profile_combo.currentData() or '';self.settings['ai_profile']=pid
        p=next((p for p in self.settings['ai_profiles'] if p['id']==pid),{})
        self.api_delete_button.setEnabled(bool(p))
        for w,k in [(self.api_name,'name'),(self.api_url,'url'),(self.api_model,'model')]:w.setText(p.get(k,''))
        self.api_key.clear();self.api_input_price.setValue(p.get('input_price',0));self.api_output_price.setValue(p.get('output_price',0))
        self.storage.save_settings()
        self.refresh_home_setup()
    def new_api_profile(self):self.ai_profile_combo.setCurrentIndex(0);self.api_name.setFocus()
    def delete_api_profile(self):
        pid=self.ai_profile_combo.currentData()
        profile=next((p for p in self.settings['ai_profiles'] if p['id']==pid),None)
        if not profile:return
        if QMessageBox.question(self,'删除 API 配置','删除「'+profile['name']+'」及其保存的密钥？\n当前请求将停止，其他配置不受影响。')!=QMessageBox.StandardButton.Yes:return
        self.cancel_ai();self.ai_result=None;self.storage.delete_key(pid)
        self.settings['ai_profiles']=[p for p in self.settings['ai_profiles'] if p['id']!=pid];self.settings['ai_profile']=''
        self.ai_toggle.setChecked(False);self.settings['ai_enabled']=False;self.storage.save_settings();self.fill_ai_profiles()
        self.refresh_all();self.notify('API 配置与保存的密钥已删除；请选择其他配置后再启用 AI')
    def save_api_profile(self):
        try:endpoint(self.api_url.text())
        except ValueError as e:self.error(str(e));return
        if not self.api_model.text().strip():self.error('请填写模型名称');return
        pid=self.ai_profile_combo.currentData() or str(uuid.uuid4())
        p={'id':pid,'name':self.api_name.text().strip() or self.api_model.text().strip(),'url':self.api_url.text().strip(),'model':self.api_model.text().strip(),
           'input_price':self.api_input_price.value(),'output_price':self.api_output_price.value()}
        try:
            if self.api_key.text().strip():self.storage.save_key(pid,self.api_key.text().strip())
        except OSError as e:self.error(str(e));return
        self.settings['ai_profiles']=[x for x in self.settings['ai_profiles'] if x['id']!=pid]+[p];self.settings['ai_profile']=pid
        self.storage.save_settings();self.fill_ai_profiles();self.notify('API 配置已保存，密钥已由 Windows 加密')
    def toggle_ai(self,on):
        self.settings['ai_enabled']=on
        if not on:self.cancel_ai()
        self.storage.save_settings();self.refresh_ai()
        self.refresh_home_setup()
        if hasattr(self,'overlay'):self.overlay.update_content()
    def cancel_ai(self):
        self.ai_generation+=1
        if hasattr(self,'request_cancel'):self.request_cancel.set()
        self.coach.cancel();self.ai_status.setText('已停止 AI 请求 · 本地推荐继续可用')
    def maybe_auto_analyze(self):
        if self.review_opening or self.visible_opening():return
        if self.store.state.get('opening') and self.store.state['field_meta'].get('opening_snapshot',{}).get('uncertain'):return
        s=self.store.state
        if not (self.settings['ai_enabled'] and self.settings['ai_auto'] and s['phase']=='整备' and not self.ai_busy):return
        # Partial sprite observations are covered by the explicit roster
        # confirmation. A rejected candidate is not a required roster slot.
        keys=[f['key'] for f in (self.last_recognition or {}).get('fields',[]) if not f['key'].startswith('sprite:')]
        # A confirmed partial shop can support bounded recommendations. Its
        # explicit pending slots are not required inputs or presumed empty slots.
        keys=[k for k in keys if not pending_shop_field(s,k)]
        if 'battle_roster' in s['field_meta']:
            update_roster_status(s);keys.append('battle_roster')
        essential=['phase','round','gold','level']
        if any(k not in keys for k in essential) or not any(k.startswith('shop:') for k in keys):return
        if ready_for_auto(s,keys):return
        key=(s['session_id'],s['round'],fingerprint(s) if self.settings['ai_on_change'] else '')
        if key in self.auto_keys:return
        if time.monotonic()-self.coach.last_started<self.settings['ai_min_interval']:return
        self.auto_keys.add(key);self.analyze(auto=True)
    def analyze(self,deep=False,test=False,auto=False):
        if not test and self.review_opening:
            self.notify('先重新识别并确认本局禁选，再进行 AI 分析');return
        if not test and self.visible_opening() and self.visible_opening().get('context')!='in_match':
            self.notify('开局建议已由本地规则即时计算；进入整备阶段后可使用 AI 回合教练');return
        if self.ai_busy:self.notify('已有分析请求正在进行');return
        if not self.settings['ai_enabled'] and not test:self.notify('AI 当前关闭，请先打开独立开关');return
        profile=next((p for p in self.settings['ai_profiles'] if p['id']==self.settings['ai_profile']),None)
        if not profile:self.notify('请先保存并选择 API 配置');return
        try:key=self.storage.get_key(profile['id'])
        except OSError as e:self.error(str(e));return
        self.ai_busy=True;gen=self.ai_generation;s=copy.deepcopy(self.store.state);config=copy.deepcopy(self.settings);self.request_cancel=threading.Event();token=self.request_cancel
        tracked=copy.deepcopy(self.tracked)
        self.ai_status.setText('正在测试连接…' if test else '正在分析当前局面… 本地建议已就绪')
        self.overlay.update_content()
        def done(result):
            if gen!=self.ai_generation:return
            if result.get('test'):self.ai_status.setText(f'连接成功 · {result["elapsed_ms"]} ms');return
            if not self.settings['ai_enabled']:return
            self.ai_result=result;self.refresh_ai();self.overlay.update_content()
        def finished():
            self.ai_busy=False;self.overlay.update_content()
        self.run_job(lambda:self.coach.run(self.db,s,config,profile,key,deep,test,token,tracked),done,
            lambda msg:self.ai_status.setText(msg) if gen==self.ai_generation else None,finished)
    def refresh_ai(self):
        self.ai_route_lock.refresh()
        self.fill_tracking(self.ai_pins,self.ai_choices)
        p=next((p for p in self.settings['ai_profiles'] if p['id']==self.settings['ai_profile']),{})
        cost=(self.coach.input_tokens*p.get('input_price',0)+self.coach.output_tokens*p.get('output_price',0))/1_000_000
        self.ai_usage.setText(f'本局调用 {self.coach.calls}/{self.settings["ai_limit"]}  ·  输入 {self.coach.input_tokens} / 输出 {self.coach.output_tokens} tokens'+(f'  ·  估算费用 {cost:.4f}（所填币种）' if p.get('input_price') or p.get('output_price') else '  ·  未配置单价'))
        view=overlay_advice(self.db,self.store.state,self.ai_result,self.visible_opening(),self.settings['ai_enabled'])
        self.ai_sources.setText(sources_html(view.get('source_ids',[]),view.get('source_label','攻略来源')))
        if view['source']!='AI 分析':
            self.ai_output.setPlainText(view['analysis'] if self.visible_opening() else local_plan(self.db,self.store.state)['analysis'])
            self.ai_status.setText('AI 关闭 · 本地攻略推荐' if not self.settings['ai_enabled'] else '当前先按本地攻略建议 · AI '+('分析中' if self.ai_busy else '等待更新'))
            return
        result=self.ai_result;stale=result.get('fingerprint')!=fingerprint(self.store.state)
        self.ai_status.setText('局面已变化 · 请重新分析' if stale else '分析完成 · 优先执行建议，再核对后续条件')
        formatted=analysis_text(self.db,self.store.state,result)
        target=result.get('target_recommendation') or {}
        if not stale and target.get('name') in {c['name'] for c in target_candidates(self.db,self.store.state,5)}:
            formatted+='\n\n目标盟约：'+target['name']+'\n'+target.get('reason','')+'\n'+target.get('transition','')
        self.ai_output.setPlainText(formatted)

    def page_settings(self):return self.build_settings()

    def database_info(self):
        m=self.db.raw['metadata']
        return f'{m["version"]}  /  资料日期 {m["as_of"]}\n干员 {len(self.db.ops)} · 盟约 {len(self.db.covenants)} · 装备 {len(self.db.equipment)} · 策略指令 {len(self.db.commands)} · 技能 {len(self.db.skills)}\n{m["recommendation_note"]}'
    def save_hotkeys(self):
        values={k:w.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for k,w in self.shortcut_edits.items()};old={k:self.settings[k] for k in values}
        self.settings.update(values)
        try:self.configure_hotkeys()
        except ValueError as e:self.settings.update(old);self.error(str(e));return
        self.storage.save_settings();self.notify('四组全局快捷键已注册并保存')
    def save_display(self):
        self.settings.update(overlay_opacity=self.opacity_spin.value()/100,overlay_scale=self.scale_spin.value(),floating_size=self.floating_size_spin.value(),reduce_motion=self.motion_check.isChecked())
        self.floating.setFixedSize(self.settings['floating_size'],self.settings['floating_size'])
        self.storage.save_settings();self.overlay.update_content();self.notify('窗口外观设置已保存')
    def save_runtime(self):
        vision=dict(capture_interval=self.interval_spin.value(),recognition_threshold=self.threshold_spin.value(),stable_frames=self.stability_spin.value(),
                    opening_stable_frames=self.opening_stability_spin.value(),shop_stable_frames=self.shop_stability_spin.value())
        changed=any(self.settings.get(key)!=value for key,value in vision.items())
        self.settings.update(vision,ai_timeout=self.timeout_spin.value(),ai_min_interval=self.rate_spin.value(),ai_limit=self.limit_spin.value())
        if changed:
            # Do not let an in-flight capture or old frame counts satisfy newly saved timing.
            self.capture_generation+=1
            self.gate=StabilityGate.from_settings(self.settings);self.battle_gate=StabilityGate(self.settings['stable_frames'])
            self.solo_briefing.restart_evidence();self.clear_shop_tracking()
        self.storage.save_settings();self.notify('运行参数已保存')
    def import_database(self):
        path,_=QFileDialog.getOpenFileName(self,'导入规程数据库','','JSON (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>30_000_000:raise ValueError('数据库文件过大')
            data=json.loads(Path(path).read_text(encoding='utf-8'));Database.validate(data)
            destination=self.storage.root/'database'/'rules.json';atomic_json(destination,data);self.settings['database_override']=str(destination);self.storage.save_settings()
            self.notify('新版数据库校验并保存成功；重启助手后启用。原始数据库保留。')
        except Exception as e:self.error('数据库未导入：'+str(e))
    def show_sources(self):
        d=QDialog(self);d.setWindowTitle('数据库来源与版本');d.resize(900,650);l=QVBoxLayout(d);text=QPlainTextEdit();text.setReadOnly(True)
        text.setPlainText('\n\n'.join(f'{s["title"]}\n{s["url"]}\n快照：{s.get("snapshot_url") or "未提供"}\n访问日期：{s["accessed_on"]}' for s in self.db.sources.values()));l.addWidget(text);l.addWidget(button('关闭',d.accept));d.exec()
    def save_team(self):
        name=self.team_name.text().strip() or '未命名阵容';self.store.state['name']=name
        snapshot=copy.deepcopy(self.store.state);existing=next((i for i,x in enumerate(self.storage.teams) if x['name']==name),None)
        item={'name':name,'state':snapshot}
        if existing is None:self.storage.teams.append(item)
        else:self.storage.teams[existing]=item
        self.storage.save_teams();self.saved_teams.clear()
        for i,x in enumerate(self.storage.teams):self.saved_teams.addItem(x['name'],i)
        self.storage.save_state(self.store.state);self.notify('阵容已保存')
    def load_team(self):
        i=self.saved_teams.currentData()
        if i is not None:self.replace_team(self.storage.teams[i]['state'])
    def replace_team(self,saved):
        try:clean=validate_state(saved,self.db)
        except ValueError as e:self.error(str(e));return
        keys=('name','units','inventory','target','stacks','ursas_fixed','ursas_temporary','strategies','notes')
        self.change(lambda s:s.update({k:copy.deepcopy(clean[k]) for k in keys}),'载入阵容方案')
        self.team_name.setText(clean['name'])
    def export_team(self):
        path,_=QFileDialog.getSaveFileName(self,'导出阵容',self.store.state['name']+'.json','阵容文件 (*.json)')
        if path:self.storage.export_team(path,self.store.state,self.db.raw['metadata']['version']);self.notify('阵容文件已导出，不包含 API 配置或密钥')
    def import_team(self):
        path,_=QFileDialog.getOpenFileName(self,'导入阵容','','阵容文件 (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>2_000_000:raise ValueError('阵容文件过大')
            data=json.loads(Path(path).read_text(encoding='utf-8'))
            if data.get('format')!='garrison-team':raise ValueError('不是卫戍协议助手阵容文件')
            self.replace_team(data['state'])
        except Exception as e:self.error(str(e))
    def export_image(self,path=None):
        if not path:path,_=QFileDialog.getSaveFileName(self,'保存阵容分享图',self.store.state['name']+'.png','图片 (*.png)')
        if not path:return
        s=self.store.state;units=s['units'];height=max(450,220+((len(units)+3)//4)*150);pix=QPixmap(1200,height);pix.fill(QColor(INK));p=QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(0,0,1200,3,QColor(TEAL));p.setPen(QColor(TEAL));p.setFont(QFont('Microsoft YaHei UI',24,QFont.Weight.Bold));p.drawText(40,65,'卫戍协议 / '+s['name'])
        p.setPen(QColor('#a4b3b5'));p.setFont(QFont('Microsoft YaHei UI',12));p.drawText(40,105,f'{self.db.raw["metadata"]["version"]}  ·  目标 {s["target"] or "未指定"}')
        for i,u in enumerate(units):
            x=40+(i%4)*290;y=140+(i//4)*150
            frame(p,QRectF(x,y,270,126),TEAL,PANEL,8,True);avatar=self.pixmap(u['op_id']);p.drawPixmap(x+8,y+12,80,80,avatar)
            p.setPen(QColor('#eef2df'));p.setFont(QFont('Microsoft YaHei UI',13,QFont.Weight.Bold));p.drawText(x+98,y+34,self.db.ops[u['op_id']]['name'])
            p.setFont(QFont('Microsoft YaHei UI',10));p.drawText(x+98,y+59,('战场' if u['zone']=='field' else '整备')+' / '+('精锐' if u['elite'] else '初始'))
            p.setPen(QColor('#b4c3ba'));p.drawText(x+10,y+112,' · '.join(self.db.ops[u['op_id']]['covenants']))
        p.setFont(QFont('Microsoft YaHei UI',10));p.setPen(QColor('#829193'));p.drawText(40,height-24,'资料来源 PRTS Wiki / SquadPool · 图片版权归鹰角网络及相关权利人 · 助手阵容规划，非胜率保证');p.end()
        if not pix.save(str(path)):self.error('无法保存图片，请检查目标路径')
        else:self.notify('阵容分享图已保存')
    def new_session(self):
        self.storage.archive_session(self.store.state);self.cancel_ai();self.store=StateStore(new_state());self.coach.reset(self.store.state['session_id'])
        self.tracked=[];self.storage.save_tracking(self.tracked)
        self.ai_result=None;self.auto_keys.clear();self.budget_plan=[];self.reset_capture();self.team_name.setText('未命名阵容');self.refresh_all();self.notify('新对局已开始，本局追踪已清空；上一局已保存在本机历史文件')
    def load_example(self):
        self.new_session();ops=sorted([o for o in self.db.ops.values() if '谢拉格' in o['covenants']],key=lambda o:o['tier'])
        self.store.state.update(name='示例 · 谢拉格入门',target='谢拉格',units=[unit(o['operator_id']) for o in ops[:3]],gold=10,round=1,level=2,phase='整备')
        self.store.state['shop']=[{'op_id':o['operator_id'],'cost':o['recruit_cost']} for o in ops[3:6]]
        self.team_name.setText('示例 · 谢拉格入门');self.refresh_all();self.notify('已载入明确标记的示例局面；开始实战前点击“新对局”')
