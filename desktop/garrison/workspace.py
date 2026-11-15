"""Task-oriented page composition; all controls share the existing application state."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget,QGridLayout,QTabWidget,QPlainTextEdit,QListWidget,QSplitter,QSizePolicy,QFormLayout,QKeySequenceEdit,QDoubleSpinBox,QCheckBox
from PySide6.QtGui import QKeySequence
from .widgets import label,button,row,column,card,scroll,DashboardScroll
from .terminal import HudRail,CovenantStrip,RecommendationSlot
from .tracking_view import TrackingChoices
from .battle import roster_signature
from .opening import snapshot_key


class WorkspaceMixin:
    def build_home(self):
        from .ui import RouteLockControl
        self.home_connection=label('选择游戏窗口后开始识别','muted',True)
        self.home_api_status=label('AI 可选，关闭时仍有本地攻略','muted',True)
        self.home_ban_status=label('等待开局信息','accent',True)
        self.home_ban_brief=label('尚未确认本局禁选','muted',True)
        self.home_roster_status=label('等待识别当前阵容','accent',True)
        self.home_roster_brief=label('检查战场和整备区后确认','muted',True)
        self.home_bind_host=column();self.home_ai_host=column()
        self.home_ban_confirm=button('确认禁选',self.apply_opening,True)
        self.home_ban_details=button('查看详情',lambda:self.open_home_tab('bans'))
        self.home_roster_confirm=button('确认阵容',self.confirm_home_roster,True)
        self.home_roster_details=button('调整阵容',lambda:self.open_home_tab('roster'))
        self.home_api_button=button('配置 API',lambda:self.navigate('api'))
        grid=QWidget();layout=QGridLayout(grid);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.home_step_cards=[]
        for i,(title,items) in enumerate([
            ('01  绑定游戏',[self.home_connection,self.home_bind_host]),
            ('02  开关 AI',[self.home_api_status,self.home_ai_host,self.home_api_button]),
            ('03  确认禁选',[self.home_ban_status,self.home_ban_brief,row(self.home_ban_confirm,self.home_ban_details)]),
            ('04  确认阵容',[self.home_roster_status,self.home_roster_brief,row(self.home_roster_confirm,self.home_roster_details)])]):
            panel=card(title,*items);panel.layout().setContentsMargins(10,10,10,10);panel.layout().setSpacing(6)
            layout.addWidget(panel,0,i);layout.setColumnStretch(i,1);self.home_step_cards.append(panel)
        self.home_flow=grid
        self.home_hud=HudRail();self.home_links=CovenantStrip()
        self.home_goal=label('','accent',True);self.home_status=label('','muted',True)
        self.local_advice=QPlainTextEdit();self.local_advice.setReadOnly(True);self.local_advice.setMinimumHeight(145)
        self.home_roster=QListWidget();self.home_roster.setIconSize(QSize(40,40));self.home_roster.setMinimumHeight(100)
        self.home_roster.itemDoubleClicked.connect(self.open_home_member)
        self.home_sources=label('','muted',True)
        from PySide6.QtCore import Qt
        self.home_sources.setTextFormat(Qt.TextFormat.RichText);self.home_sources.setOpenExternalLinks(True)
        self.home_route_lock=RouteLockControl(self)
        self.home_pins=TrackingChoices(self.toggle_tracking,True,self.open_tracking)
        self.home_choices=TrackingChoices(self.toggle_tracking,bulk=self.track_recommended_formation)
        advice=column(self.home_goal,self.home_route_lock,self.local_advice,self.home_sources)
        roster=card('当前成员',self.home_roster,button('核对 / 调整',lambda:self.open_home_tab('roster')))
        split=QSplitter();split.addWidget(advice);split.addWidget(roster);split.setSizes([650,300])
        overview=column(self.home_pins,split,self.home_choices);overview.layout().setStretch(1,1)
        self.home_slots=[RecommendationSlot() for _ in range(5)];self.home_level=label('—','number')
        shop=column(self.home_links,row(label('调度等级','muted'),self.home_level,None),row(*self.home_slots),
                    button('调整商店与资金',lambda:self.navigate('tools')),None)
        self.home_tabs=QTabWidget();self.home_tab_ids={}
        for key,title,page in [('overview','建议与追踪',overview),('shop','商店与盟约',shop)]:
            self.home_tab_ids[key]=self.home_tabs.addTab(scroll(page),title)
        self.home_content=column(self.heading('首页','绑定游戏 → 选择 AI → 核对禁选 → 核对阵容'),grid,self.home_hud,self.home_tabs,
            row(self.home_status,button('新对局',self.new_session)))
        self.home_content.layout().setStretch(3,1);self.home_content.layout().setSpacing(8)
        self.home_content.setMinimumHeight(780)
        return DashboardScroll(self.home_content)

    def compose_workspace(self,parts):
        # Reparent each existing control once; no mirrored settings or duplicate models.
        self.window_combo.setMinimumWidth(0)
        self.window_combo.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.home_bind_host.layout().addWidget(self.window_combo)
        self.home_refresh_windows=button('刷新',self.refresh_windows)
        self.home_refresh_windows.setMaximumWidth(58)
        self.live_button.setToolTip('绑定后开始识别，并将连续核验通过的结果同步到本局。自动同步可在设置的画面识别中调整。')
        self.home_bind_host.layout().addWidget(row(self.home_refresh_windows,self.live_button))
        self.ai_toggle.setText('启用 AI 教练');self.home_ai_host.layout().addWidget(self.ai_toggle)
        for key,title,page in [('bans','禁选核对',self.opening_page),('roster','阵容核对',parts['roster']),('analysis','AI 详细建议',self.ai_results_page)]:
            self.home_tab_ids[key]=self.home_tabs.addTab(scroll(page),title)
        self.catalog_tabs.insertTab(1,parts['covenants'],'盟约')
        self.catalog_tabs.insertTab(2,parts['equipment'],'装备')
        self.catalog_tabs.insertTab(3,self.command_catalog_page,'策略 / 指令')
        self.catalog_tab_ids={'operators':0,'covenants':1,'equipment':2,'commands':3,'compare':4}
        self.tools_tabs.addTab(self.inventory_page,'库存与合成')
        self.settings_tabs.insertTab(1,parts['recognition'],'画面识别')
        self.settings_tabs.insertTab(2,scroll(column(parts['api'],self.ai_runtime_page,None)),'AI / API')
        self.settings_tab_ids={'appearance':0,'recognition':1,'api':2,'data':3}
        self.recognition_controls.layout().insertWidget(0,self.recognition_runtime_page)
        return [('home','01   首页',parts['home']),('catalog','02   资料图鉴',parts['catalog']),
                ('guides','03   阵容攻略',parts['guides']),('tools','04   对局工具',parts['tools']),('settings','05   设置',parts['settings'])]

    def resolve_destination(self,destination):
        # Named routes also open the relevant nested tab. Numeric indices refer
        # only to the five visible main pages.
        if isinstance(destination,int):return destination
        if destination in ('roster','bans','analysis','shop'):
            self.open_home_tab(destination,False);destination='home'
        elif destination in ('recognition','api','appearance','data'):
            self.settings_tabs.setCurrentIndex(self.settings_tab_ids[destination]);destination='settings'
        elif destination in ('operators','covenants','equipment','commands','compare'):
            self.catalog_tabs.setCurrentIndex(self.catalog_tab_ids[destination]);destination='catalog'
        elif destination=='inventory':
            self.tools_tabs.setCurrentIndex(1);destination='tools'
        return self.page_ids[destination]

    def open_home_tab(self,name,focus=True):
        self.home_tabs.setCurrentIndex(self.home_tab_ids[name])
        if focus:self.navigate('home')

    def open_home_member(self,item):
        from PySide6.QtCore import Qt
        self.open_home_tab('roster');self.select_unit(item.data(Qt.ItemDataRole.UserRole))

    def confirm_home_roster(self):
        if not self.store.state['units']:
            self.open_home_tab('roster');self.notify('先添加或识别当前成员，再确认阵容');return
        if any(u.get('sprite_missing') for u in self.store.state['units']):self.open_home_tab('roster')
        self.confirm_battle_roster()

    def bind_home_game(self):
        if not self.live and self.window_combo.currentData():
            # The home action explicitly starts synchronization, including on
            # legacy profiles where capture-only review was the default.
            self.auto_apply_check.setChecked(True)
        self.toggle_live()

    def refresh_home_setup(self):
        if not getattr(self,'workspace_ready',False):return
        s=self.store.state;target=self.window_combo.currentData()
        self.home_connection.setText(('已绑定 · 自动同步局面' if self.settings['auto_apply'] else '已绑定 · 仅识别，等待手动确认') if self.live and target else '已选择窗口 · 识别已暂停' if target else '先打开游戏，再选择窗口')
        self.live_button.setEnabled(bool(target));self.live_button.setText('暂停识别' if self.live else '绑定并同步')
        profile=next((p for p in self.settings['ai_profiles'] if p['id']==self.settings['ai_profile']),None)
        self.home_api_status.setText(('已开启 · '+profile['name']) if self.settings['ai_enabled'] and profile else
            '已开启，需配置 API；暂用本地攻略' if self.settings['ai_enabled'] else '已关闭 · 使用本地攻略')
        self.home_api_button.setText('调整 API' if profile else '配置 API')
        visible=self.visible_opening();saved=s.get('opening');meta=s['field_meta'].get('opening_snapshot',{})
        confirmed=bool(saved and not meta.get('uncertain') and not self.review_opening and (not visible or snapshot_key(visible)==snapshot_key(saved)))
        confirmation=self.opening_confirmation()
        self.home_ban_status.setText('已确认 · 本局禁选' if confirmed else '正在重新核对' if self.review_opening else '待确认 · 本局禁选')
        shown=visible or saved
        if shown:
            grey=[e['name'] for group in ('core','additional') for e in shown[group] if e['state']=='grey']
            detail='禁选：'+'、'.join(grey) if grey else '本局盟约全部启用' if confirmed else '当前图标未显示禁选，核对后可确认'
            self.home_ban_brief.setText('禁选：'+'、'.join(grey[:3])+f' 等 {len(grey)} 项' if len(grey)>3 else detail)
            self.home_ban_brief.setToolTip(detail)
        else:self.home_ban_brief.setText('在游戏中展开开局信息，或局内重新读取')
        self.home_ban_confirm.setEnabled(confirmation['enabled']);self.home_ban_confirm.setText('已确认' if confirmed else '确认禁选')
        units=s['units'];pending=sum(bool(u.get('sprite_missing')) for u in units)
        roster=s['field_meta'].get('battle_roster',{})
        roster_ok=bool(units and not pending and not roster.get('uncertain') and roster.get('signature')==roster_signature(s))
        self.home_roster_status.setText('已确认 · 当前阵容' if roster_ok else '待核对 · 当前阵容' if units else '等待识别 / 添加成员')
        self.home_roster_brief.setText(f'战场 {sum(u["zone"]=="field" for u in units)} 人 · 整备 {sum(u["zone"]=="bench" for u in units)} 人'+(f'\n{pending} 人暂不可见，沿用最后记录' if pending else '\n检查人数、位置与精锐状态'))
        self.home_roster_confirm.setEnabled(bool(units) and not roster_ok);self.home_roster_confirm.setText('已确认' if roster_ok else '确认阵容')
        self.ai_toggle.blockSignals(True);self.ai_toggle.setChecked(self.settings['ai_enabled']);self.ai_toggle.blockSignals(False)

    def build_settings(self):
        from .ui import spin
        import os
        self.shortcut_edits={};hotkeys=QWidget();form=QFormLayout(hotkeys)
        for key,title in [('main_hotkey','主窗口最小化 / 恢复'),('overlay_hotkey','悬浮窗最小化 / 恢复'),('capture_hotkey','重新截取识别'),('coach_hotkey','手动 AI 分析')]:
            edit=QKeySequenceEdit(QKeySequence(self.settings[key]));edit.setMaximumSequenceLength(1)
            self.shortcut_edits[key]=edit;form.addRow(title,edit)
        form.addRow(button('保存快捷键',self.save_hotkeys,True))
        self.opacity_spin=spin(round(self.settings['overlay_opacity']*100),40,100)
        self.scale_spin=spin(self.settings['overlay_scale'],80,150);self.floating_size_spin=spin(self.settings['floating_size'],40,80)
        self.motion_check=QCheckBox('减少动效');self.motion_check.setChecked(self.settings['reduce_motion'])
        display=QWidget();df=QFormLayout(display)
        for title,w in [('悬浮透明度 %',self.opacity_spin),('悬浮文字缩放 %',self.scale_spin),('悬浮图标尺寸',self.floating_size_spin)]:df.addRow(title,w)
        df.addRow(self.motion_check)
        self.interval_spin=QDoubleSpinBox();self.interval_spin.setRange(.5,10);self.interval_spin.setSingleStep(.5);self.interval_spin.setValue(self.settings['capture_interval'])
        self.threshold_spin=QDoubleSpinBox();self.threshold_spin.setRange(.80,.99);self.threshold_spin.setDecimals(2);self.threshold_spin.setSingleStep(.01);self.threshold_spin.setValue(self.settings['recognition_threshold'])
        self.stability_spin=spin(self.settings['stable_frames'],2,6)
        self.opening_stability_spin=spin(self.settings['opening_stable_frames'],1,6)
        self.shop_stability_spin=spin(self.settings['shop_stable_frames'],1,6)
        for widget in (self.opening_stability_spin,self.shop_stability_spin):
            widget.setSuffix(' 帧');widget.setSpecialValueText('1 帧（关闭）')
            widget.setToolTip('1 帧：关闭连续帧等待；仍检查单帧可信度和信息完整性。')
        self.timeout_spin=spin(self.settings['ai_timeout'],5,120);self.rate_spin=spin(self.settings['ai_min_interval'],5,120);self.limit_spin=spin(self.settings['ai_limit'],1,999)
        vision=QWidget();vf=QFormLayout(vision)
        vf.setRowWrapPolicy(QFormLayout.WrapAllRows)
        for title,w in [('识别间隔（秒）',self.interval_spin),('最低识别分数',self.threshold_spin),
                        ('禁选连续一致帧数',self.opening_stability_spin),('商店连续一致帧数',self.shop_stability_spin),
                        ('其他数值与阵容连续帧数',self.stability_spin)]:vf.addRow(title,w)
        self.recognition_runtime_page=card('稳定性与频率',vision,
            label('禁选和商店可分别设为 1 帧，关闭连续帧等待。商店追踪标记沿用商店帧数；单帧可信度和完整性检查仍生效。','muted',True),
            button('保存识别参数',self.save_runtime))
        ai=QWidget();af=QFormLayout(ai)
        for title,w in [('请求超时（秒）',self.timeout_spin),('最小请求间隔（秒）',self.rate_spin),('每局请求上限',self.limit_spin)]:af.addRow(title,w)
        self.ai_runtime_page=card('自动分析与请求频率',self.ai_auto,self.ai_change,ai,button('保存请求参数',self.save_runtime))
        self.data_info=label(self.database_info(),'muted',True)
        appearance=scroll(column(row(card('窗口与动效',display,button('保存外观',self.save_display)),card('快捷键',hotkeys)),None))
        data=scroll(column(card('数据库与来源',self.data_info,row(button('导入新版规则',self.import_database),button('查看全部来源',self.show_sources))),
            card('本机数据',label('对局、收藏、追踪和 API 配置保存在本机。导出阵容不会包含 API 密钥。','muted',True),button('打开数据目录',lambda:os.startfile(self.storage.root))),
            card('素材与许可',label('资料与图像来源保留在数据库中；PRTS 文字按来源许可保留署名，游戏素材版权归原权利人。','muted',True)),None))
        self.settings_tabs=QTabWidget();self.settings_tabs.addTab(appearance,'外观与快捷键');self.settings_tabs.addTab(data,'数据与来源')
        return column(self.heading('设置','外观、识别和 AI 参数集中调整；日常开关和确认在首页完成。'),self.settings_tabs,button('完全退出助手',self.quit_app))

