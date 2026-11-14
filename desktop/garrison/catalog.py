"""Paged operator reference; browsing never changes the current match."""
from __future__ import annotations
import html,json,re
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QTabWidget,QSizePolicy
from .widgets import label,button,row,column,card,scroll,PortraitView,FlowLayout
from .opening_icons import asset_root


def readable(value,fallback='未记录'):
    if value is None or value=='':return fallback
    if isinstance(value,list):return ' / '.join(str(v) for v in value) or fallback
    return str(value)


def effect_html(value):
    # Tokenize source text before creating markup, so numeric highlighting never
    # rewrites color attributes or HTML entities. <战斗中> remains literal text.
    text=readable(value);parts=[];end=0
    for match in re.finditer(r'【[^】]+】|[+\-]?\d+(?:\.\d+)?%?',text):
        parts.append(html.escape(text[end:match.start()]))
        token=html.escape(match.group());covenant=match.group().startswith('【')
        tag='span' if covenant else 'b';color='#14dfbb' if covenant else '#e7b936'
        parts.append(f'<{tag} style="color:{color}">{token}</{tag}>');end=match.end()
    parts.append(html.escape(text[end:]))
    return ''.join(parts).replace('\n','<br>')


class Metric(QWidget):
    def __init__(self,title):
        super().__init__();self.setMinimumWidth(0)
        self.value=label('—',wrap=True);self.value.setStyleSheet('font-size:22px;color:#14dfbb;font-weight:700;')
        self.caption=label(title,'muted',True)
        panel=card('',self.caption,self.value);panel.layout().setContentsMargins(10,8,10,8);panel.layout().setSpacing(3)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.addWidget(panel)
    def set_value(self,value):self.value.setText(readable(value,'—'))


class CatalogDetails(QWidget):
    def __init__(self,db,pixmap,add,compare):
        super().__init__();self.db=db;self.pixmap=pixmap;self.op=None;self.elite=False;self.skill=None
        self.setMinimumWidth(350);self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
        self.name=label('','title',True);self.state_label=label('普通 · 技能 4 级','accent')
        self.add=button('加入战场',add,True);self.compare=button('加入对比',compare)
        self.add.setToolTip('向助手阵容添加普通干员；晋升状态可在首页的阵容核对中记录。')
        self.mode_buttons={}
        for elite,title in ((False,'◇ 普通'),(True,'◆ 精锐')):
            b=button(title,lambda value=elite:self.set_elite(value));b.setCheckable(True);b.setChecked(elite==self.elite)
            b.setFixedWidth(70);b.setAccessibleName('图鉴状态：'+('精锐' if elite else '普通'));self.mode_buttons[elite]=b
        self.add.setMaximumWidth(96);self.compare.setMaximumWidth(96)
        self.tabs=QTabWidget();self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet('QTabBar::tab { padding:8px 12px; }')
        self.art=PortraitView();self.art.setMinimumWidth(0)
        self.tier=Metric('调度等阶');self.cost=Metric('招募资金')
        stats=column(self.tier,self.cost);stats.layout().setSpacing(6)
        hero=row(self.art,stats);hero.layout().setStretch(0,3);hero.layout().setStretch(1,2)
        self.covenants=QWidget();self.covenant_flow=FlowLayout(self.covenants)
        self.roles=label('','accent',True);self.overview_training=label('',wrap=True)
        self.recommended=label('','section',True);self.reason=label('',wrap=True);self.alternative=label('','muted',True)
        self._page('概览',hero,self.covenants,self.roles,card('培养规格',self.overview_training),card('技能选用',self.recommended,self.reason,self.alternative))

        self.trait_title=label('','section',True);self.trait_effect=self._effect()
        self.trigger=label('','accent',True);self.cap=label('',wrap=True);self.bench=label('','muted',True)
        self.inherited=label('','muted',True)
        self._page('特质',card('',self.trait_title,self.trait_effect,self.inherited),card('触发与生效',self.trigger,self.bench),card('叠层 / 效果限制',self.cap))

        self.skill_buttons={};self.skill_keys=row()
        for number in range(1,4):
            b=button('S'+str(number),lambda n=number:self.select_skill(n));b.setCheckable(True);b.setMinimumWidth(50)
            b.setAccessibleName('查看技能 S'+str(number));self.skill_keys.layout().addWidget(b);self.skill_buttons[number]=b
        self.skill_title=label('','section',True);self.skill_tags=label('','accent',True);self.skill_effect=self._effect()
        self.sp_initial=Metric('初始技力');self.sp_cost=Metric('消耗技力');self.duration=Metric('持续时间')
        self.skill_note=label('','muted',True);self.skill_advice=label('',wrap=True)
        self._page('技能',self.skill_keys,card('',self.skill_title,self.skill_tags,self.skill_effect),row(self.sp_initial,self.sp_cost,self.duration),card('技能选择建议',self.skill_advice,self.skill_note))

        self.training=label('',wrap=True);self.prototype=label('',wrap=True);self.common=label('','muted',True);self.notes=label('',wrap=True)
        self.source_links=label('',wrap=True);self.source_links.setTextFormat(Qt.TextFormat.RichText);self.source_links.setOpenExternalLinks(True)
        self.source_links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._page('资料',card('当前培养与替代',self.training,self.prototype),card('常规参考',self.common),card('条目说明',self.notes),card('资料来源',self.source_links))
        self.empty=label('试着取消部分筛选，或点击“重置筛选”查看全部干员。','muted',True);self.empty.hide()
        layout=QVBoxLayout(self);layout.setContentsMargins(8,8,8,8);layout.setSpacing(7)
        layout.addWidget(row(self.name));layout.addWidget(row(*self.mode_buttons.values(),None,self.add,self.compare))
        layout.addWidget(self.state_label);layout.addWidget(self.empty);layout.addWidget(self.tabs,1)
        self.icons={};index=json.loads((asset_root()/'index.json').read_text('utf8'))
        for entry in index['references']:
            if entry['kind']!='anchor' and entry['name'] not in self.icons:self.icons[entry['name']]=QPixmap(str(asset_root()/entry['file']))

    def _effect(self):
        w=label('',wrap=True);w.setTextFormat(Qt.TextFormat.RichText)
        w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);w.setStyleSheet('font-size:15px;line-height:150%;')
        return w

    def _page(self,title,*widgets):
        body=column(*widgets,None,margin=9);body.layout().setSpacing(8)
        area=scroll(body);area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        area.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
        self.tabs.addTab(area,title)

    def set_elite(self,elite):
        self.elite=elite
        for value,b in self.mode_buttons.items():b.setChecked(value==elite)
        self.refresh_state()

    def set_operator(self,op):
        self.op=op;self.empty.setVisible(op is None);self.tabs.setVisible(op is not None)
        for b in (*self.mode_buttons.values(),self.add,self.compare):b.setEnabled(op is not None)
        while self.covenant_flow.count():
            item=self.covenant_flow.takeAt(0)
            if item.widget():item.widget().deleteLater()
        if op is None:
            self.name.setText('暂无匹配干员');self.art.clear();self.skill=None
            for w in (self.trait_effect,self.cap,self.skill_effect,self.source_links,self.roles,self.reason,self.recommended,self.alternative,self.training,self.prototype,self.common,self.notes):w.clear()
            self.state_label.clear();return
        self.name.setText(op['name']);art=self.pixmap(op['operator_id'],'portrait')
        self.art.setPixmap(art) if not art.isNull() else self.art.setText('此条目暂无立绘')
        self.tier.set_value(('Ⅰ','Ⅱ','Ⅲ','Ⅳ','Ⅴ','Ⅵ')[op['tier']-1]);self.cost.set_value(op['recruit_cost'])
        self.cost.setToolTip(readable(op.get('cost_note'),'局内折扣另计'))
        for name in op['covenants']:
            icon=QLabel();icon.setFixedSize(34,34);pix=self.icons.get(name)
            if pix:
                dpr=self.devicePixelRatioF();scaled=pix.scaled(round(32*dpr),round(32*dpr),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation);scaled.setDevicePixelRatio(dpr);icon.setPixmap(scaled)
            chip=row(icon,label(name,'accent' if name in op['core_covenants'] else 'muted'));chip.layout().setSpacing(4)
            self.covenant_flow.addWidget(chip)
        self.roles.setText(' / '.join(op['categories']) or '综合作战');self.roles.setToolTip(readable(op.get('category_basis')))
        self.recommended.setText(readable(op.get('recommended_skill'),'暂无技能建议'));self.reason.setText(readable(op.get('recommendation_reason')))
        self.alternative.setText('备选 · '+readable(op.get('alternative_skill'),'无其他技能建议'))
        self.skills={s['skill_number']:s for s in self.db.skills.values() if s['operator_id']==op['operator_id']}
        self.skill=next((n for n,s in self.skills.items() if s['skill_id']==op.get('recommended_skill_id')),next(iter(self.skills),None))
        for n,b in self.skill_buttons.items():
            sk=self.skills.get(n);b.setVisible(sk is not None);b.setToolTip(sk['skill_name'] if sk else '')
            b.setText('S'+str(n)+(' · 推荐' if sk and sk['skill_id']==op.get('recommended_skill_id') else ''))
        self.prototype.setText('原型替代 · '+readable(op.get('prototype'),'无记录'))
        self.common.setText('常规部署费用 · '+readable(op.get('regular_deploy_cost'))+'\n常规阻挡数 · '+readable(op.get('regular_block_count'))+'\n仅作常规资料参考，以本模式实际效果为准。')
        self.notes.setText(readable(op.get('notes'),'此条目暂无额外说明。')+'\n'+readable(op.get('version')))
        links=[]
        for sid in op.get('source_ids',[]):
            source=self.db.sources.get(sid,{})
            if source.get('url','').startswith(('https://','http://')):
                links.append('<a style="color:#7bcce7" href="'+html.escape(source['url'],quote=True)+'">'+html.escape(source.get('title',sid))+'</a>')
        self.source_links.setText('<br><br>'.join(links) or '未记录来源链接')
        for i in range(self.tabs.count()):self.tabs.widget(i).verticalScrollBar().setValue(0)
        self.refresh_state()

    def select_skill(self,number):
        if number not in getattr(self,'skills',{}):return
        self.skill=number;self.refresh_skill()

    def refresh_state(self):
        if not self.op:return
        op=self.op;state='elite' if self.elite else 'initial';title='精锐' if self.elite else '普通'
        self.state_label.setText(title+'资料 · 技能 '+('7' if self.elite else '4')+' 级')
        self.trait_title.setText(title+'特质 · '+readable(op.get('trait_type')))
        self.trait_effect.setText(effect_html(op.get('effect_'+state)))
        self.cap.setText(readable(op.get('stack_caps_'+state),'未记录额外上限，以特质原文为准'))
        self.trigger.setText('触发时机 · '+readable(op.get('trigger_timings')))
        self.bench.setText('整备区也可生效，具体条件见特质。' if op.get('bench_effect') else '生效位置与条件以特质原文为准。')
        self.inherited.setText('精锐沿用普通特质。' if self.elite and op.get('elite_effect_inherited') else '')
        self.inherited.setVisible(bool(self.inherited.text()))
        training=readable(op.get('training_'+state));self.training.setText(title+' · '+training);self.overview_training.setText(training)
        self.refresh_skill()

    def refresh_skill(self):
        sk=getattr(self,'skills',{}).get(self.skill)
        for n,b in self.skill_buttons.items():b.setChecked(n==self.skill)
        if not sk:
            self.skill_title.setText('暂无技能记录');self.skill_tags.clear();self.skill_effect.clear()
            for metric in (self.sp_initial,self.sp_cost,self.duration):metric.set_value(None)
            self.skill_advice.setText('此条目未记录技能。');self.skill_note.clear();return
        rank='rank7' if self.elite else 'rank4'
        self.skill_title.setText('S'+str(sk['skill_number'])+' / '+sk['skill_name'])
        self.skill_tags.setText(' · '.join(v for v in (sk.get('recovery_type'),sk.get('activation_type'),'精锐 7 级' if self.elite else '普通 4 级') if v))
        self.skill_effect.setText(effect_html(sk.get('effect_'+rank)))
        self.sp_initial.set_value(sk.get('initial_sp_'+rank));self.sp_cost.set_value(sk.get('sp_cost_'+rank))
        self.duration.set_value(str(sk['duration_'+rank])+' 秒' if sk.get('duration_'+rank) else '—')
        self.skill_advice.setText(readable(self.op.get('recommendation_reason')))
        self.skill_note.setText(readable(self.op.get('recommendation_status')))
