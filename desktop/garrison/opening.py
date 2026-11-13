"""Icon-only briefing recognition with the user's corrected primary-core rule.

With a primary core, its state decides availability. Only operators without a
primary core are excluded when their nonempty additional covenants are all banned.
Corrected after the user's Hellagur observation; the HTML still supplies mapping.
Additional core memberships are NOT the primary core. No operator image/OCR
matching, no positional last-five fallback, and no guessing an unseen icon.
"""
from __future__ import annotations
import copy,json,time
from functools import lru_cache
import cv2,numpy as np
from .opening_icons import IconMatcher,asset_root,color_state


@lru_cache(maxsize=1)
def rules():return json.loads((asset_root()/'ban-rules.json').read_text('utf8'))


def memberships(op):
    item=rules()['operators'].get(op['name'])
    if item:return item['core'],item['additional']
    # Two newer database entries absent from the HTML are support-only units.
    return next(iter(op.get('core_covenants',[])),''),op.get('additional_covenants',[])


def core_unrestricted(opening):
    entries=(opening or {}).get('core',[])
    return len(entries)==10 and len({e.get('name') for e in entries})==10 and all(e.get('state')=='lit' for e in entries)


def ban_summary(opening,kind):
    entries=(opening or {}).get(kind,[]);names=[e['name'] for e in entries if e['state']=='grey']
    if names:return '、'.join(names)
    complete=len(entries)==(10 if kind=='core' else 16) and all(e['state']=='lit' for e in entries)
    return '无（全部启用）' if complete else '待识别'


def availability(db,opening,side=None):
    opening=opening or {};core={e['name']:e['state'] for e in opening.get('core',[])}
    extra={e['name']:e['state'] for e in opening.get('additional',[])}
    if side in ('left','right') and opening.get('mode')=='solo' and not core_unrestricted(opening):
        core={name:('lit' if group==side else 'grey') for group,names in opening.get('groups',{}).items() for name in names}
    result={};ban_small=set(rules()['small'])
    for oid,op in db.ops.items():
        primary,adds=memberships(op)
        # 独行 cannot be banned in the supplied tool; 绝技 is not a ban toggle.
        states=[extra.get(c,'unknown') if c in ban_small else 'lit' for c in adds]
        if primary:
            state=core.get(primary,'unknown')
            status={'grey':'banned','lit':'available'}.get(state,'unknown')
            reason='主核心盟约「'+primary+'」'+{'grey':'被禁','lit':'可用；不因附加盟约禁选排除'}.get(state,'尚未确认')
        elif states and all(s=='grey' for s in states):
            status,reason='banned','附加盟约全部被禁：'+'、'.join(adds)
        elif states and 'lit' not in states:
            status,reason='unknown','相关盟约图标未识别完整'
        else:status,reason='available','按已识别盟约推算可用'
        result[oid]={'status':status,'reason':reason}
    return result


def recompute(db,opening):
    opening['core_complete']=len(opening.get('core',[]))==10 and all(e['state']!='unknown' for e in opening['core'])
    opening['additional_complete']=len(opening.get('additional',[]))==16 and all(e['state']!='unknown' for e in opening['additional'])
    statuses=availability(db,opening)
    opening['banned_ids']=sorted(oid for oid,v in statuses.items() if v['status']=='banned')
    opening['unknown_ids']=sorted(oid for oid,v in statuses.items() if v['status']=='unknown')
    opening['ban_status']='derived' if opening['core_complete'] and opening['additional_complete'] else 'partial'
    return opening


def confirmation_problem(db,opening):
    """Validate the observed icons and actual choice, not cached completeness flags."""
    if not opening:return '等待识别开局盟约图标'
    for kind,cv_type in (('core','核心盟约'),('additional','附加盟约')):
        expected={c['name'] for c in db.covenants if (c['type']=='核心盟约')==(kind=='core')}
        entries=opening.get(kind,[])
        if len(entries)!=len(expected) or {e.get('name') for e in entries}!=expected or any(e.get('state') not in ('lit','grey') for e in entries):
            return '请展示完整的'+cv_type+'图标，或在主窗口补齐核对'
    if opening.get('mode') not in ('solo','coop','fixed'):return '开局布局尚未确认，请保持信息界面可见'
    if opening['mode']=='solo' and not core_unrestricted(opening):
        groups=opening.get('groups',{});side=opening.get('selected')
        core={e['name']:e['state'] for e in opening['core']}
        left=groups.get('left',[]);right=groups.get('right',[])
        if len(left)!=5 or len(right)!=5 or set(left)&set(right) or set(left+right)!=set(core):return '左右分组尚未完整识别'
        if side not in ('left','right'):return '请先在游戏中选定左组或右组，等待高亮识别'
        if any(state!=('lit' if name in groups[side] else 'grey') for name,state in core.items()):return '选组与图标亮暗不一致，请等待画面稳定'
    return ''


def snapshot_key(opening):
    if not opening:return None
    return (opening.get('mode'),opening.get('context','briefing'),opening.get('selected'),
            tuple((k,tuple(sorted(v))) for k,v in sorted(opening.get('groups',{}).items())),
            tuple(sorted((e['name'],e['state']) for e in opening.get('core',[]))),
            tuple(sorted((e['name'],e['state']) for e in opening.get('additional',[]))))


class OpeningRecognizer:
    def __init__(self,db):self.db=db;self.icons=IconMatcher()

    def recognize(self,frame,review=False,in_match=False):
        start=time.perf_counter();matches=self.icons.detect(frame,review=review);h,w=frame.shape[:2]
        anchors={e['name']:e for e in matches if e['kind']=='anchor'}
        core_header=anchors.get('核心盟约');extra_header=anchors.get('附加盟约')
        entries=[e for e in matches if e['kind']!='anchor']
        if (not review and not (core_header or extra_header)) or len(entries)<5:return None
        core=[e for e in entries if e['kind']=='core' and (review or (core_header and e['y']>core_header['y']+.045 and (not extra_header or e['y']<extra_header['y'])))]
        additional=[e for e in entries if e['kind']=='additional' and (review or (extra_header and e['y']>extra_header['y']+.045))]
        if len(core)+len(additional)<5:return None
        for e in core+additional:e['state']=color_state(frame,e)
        # Row ordering uses icon centres, independent of labels and OCR boxes.
        order=lambda e:(round(e['y']/.045),e['x'])
        core.sort(key=order);additional.sort(key=order)
        mode='unknown';groups={};selected=None
        if len(core)==10 and extra_header:
            horizontal=sorted(core,key=lambda e:e['x']);gap=horizontal[5]['x']-horizontal[4]['x']
            if gap>.08 and max(e['y'] for e in core)-min(e['y'] for e in core)>.10:
                middle=(horizontal[4]['x']+horizontal[5]['x'])/2
                groups={side:[e['name'] for e in core if (e['x']<middle)==(side=='left')] for side in ('left','right')}
                if all(len(names)==5 for names in groups.values()):mode='solo'
                lower=max(e['y']+e['rect'][3]/2 for e in core);upper=extra_header['y']-.035
                roi=frame[int(lower*h):int(upper*h),:int(.68*w)]
                if roi.size:
                    b,g,r=cv2.split(roi.astype(np.int16));mask=((g>140)&(g>r*2)&(b>r*2)).astype(np.uint8)
                    _,_,stats,_=cv2.connectedComponentsWithStats(mask)
                    lines=[s for s in stats[1:] if s[2]>.22*w and s[3]<.025*h]
                    sides={('left' if (s[0]+s[2]/2)/w<middle else 'right') for s in lines}
                    if len(sides)==1:selected=sides.pop()
                # Underline and all five icon lights must agree.
                if selected and any(e['state']!=('lit' if e['name'] in groups[selected] else 'grey') for e in core):selected=None
            elif max(e['y'] for e in core)-min(e['y'] for e in core)<.025 and horizontal[-1]['x']-horizontal[0]['x']>.47:
                mode='coop'
        context='in_match' if review or (in_match and not anchors.get('准备入口')) else 'briefing'
        if context=='in_match' or (len(core)==10 and all(e['state']=='lit' for e in core)):
            mode='fixed';groups={};selected=None
        payload={'mode':mode,'context':context,'groups':groups if mode=='solo' else {},'selected':selected,
                 'core':[{k:e[k] for k in ('name','state')} for e in core],
                 'additional':[{k:e[k] for k in ('name','state')} for e in additional]}
        recompute(self.db,payload)
        valid=not confirmation_problem(self.db,payload)
        notes=['PRTS 原始盟约图标轮廓比对；禁用干员按修正后的主核心优先规则推算']
        if not valid:notes.append('图标或选择状态未核验完整，暂不自动写入；可在“开局禁选”核对')
        field={'key':'opening_snapshot','value':json.dumps(payload,ensure_ascii=False,sort_keys=True) if valid else None,
               'label':{'solo':'单人 · 左右两组选一','coop':'联机 · 固定配置','fixed':'局内禁选核对' if context=='in_match' else '核心全部启用 · 无需选组','unknown':'开局信息 · 布局待补全'}[mode],
               'confidence':.97 if valid else 0,'method':'盟约图标 + 高亮框核验','raw':'不使用文字或干员头像比对','time':time.time()}
        regions=[{'key':'opening:'+e['name'],'rect':e['rect'],'label':e['name']+' / '+{'lit':'亮','grey':'灰','unknown':'待确认'}[e['state']],
                  'pending':e['state']=='unknown'} for e in core+additional]
        return {'opening':payload,'icon_matches':core+additional,'fields':[field],'words':[],'candidates':[],
                'regions':regions,'notes':notes,'mode':'opening','layout_valid':valid,'shop_slots':[],
                'battlefield':None,'elapsed_ms':round((time.perf_counter()-start)*1000),'time':time.time(),
                'size':[w,h],'complete':valid}


def apply_snapshot(state,opening):
    # Each full observation replaces prior restrictions, including bans which
    # disappear after a solo side change. No cumulative stale ban list.
    state['opening']=copy.deepcopy(opening)
    if opening.get('context')!='in_match':state['phase']='开局'


def unavailable_reason(db,state,oid):
    opening=state.get('opening')
    if not opening:return ''
    result=availability(db,opening)[oid]
    return result['reason'] if result['status']!='available' else ''


def recommendation(db,opening,target=''):
    if not opening or opening.get('mode')!='solo' or not opening.get('core_complete') or core_unrestricted(opening):return None
    groups=opening.get('groups',{})
    if set(groups)!= {'left','right'} or any(len(v)!=5 for v in groups.values()):return None
    rows=[]
    for side,names in groups.items():
        statuses=availability(db,opening,side)
        pool=[o for oid,o in db.ops.items() if statuses[oid]['status']=='available']
        early=[o for o in pool if o['tier']<=2];routes=[]
        for name in names:
            members=sorted([o for o in early if name in o['covenants']],key=lambda o:(o['recruit_cost'],o['tier'],o['name']))
            threshold=next(c['activation_count'] for c in db.covenants if c['name']==name)
            if len(members)>=threshold:
                starters=members[:threshold];cost=sum(o['recruit_cost'] for o in starters)
                stackers=sum('叠层' in o['categories'] for o in starters)
                routes.append({'name':name,'cost':cost,'operators':[o['name'] for o in starters],
                               'score':max(0,24-cost*2)+stackers*3+(40 if target==name else 0)})
        routes.sort(key=lambda r:(-r['score'],r['cost'],r['name']));best=routes[0] if routes else None
        score=(best['score'] if best else 0)+min(len(early),24)/4+(60 if target in names else 0)
        reasons=[]
        if target in names:reasons.append('包含目标盟约「'+target+'」')
        if best:reasons.append(f'{best["name"]} {len(best["operators"])} 人起步，基础合计 {best["cost"]} 资金')
        else:reasons.append('低阶池暂不足以组成 3 人核心，需要后续阶级补齐')
        from .core import new_state
        from .strategy import route_matches
        preview=new_state();preview['target']=target;preview['opening']=copy.deepcopy(opening);preview['opening']['selected']=side
        for entry in preview['opening']['core']:entry['state']='lit' if entry['name'] in names else 'grey'
        recompute(db,preview['opening']);guides=route_matches(db,preview,1)
        if guides:
            guide=guides[0];score+=20
            reasons.append('可参考攻略「'+guide['title']+'」；作者：'+'、'.join(guide['authors']))
        reasons.append(f'推算可用 {len(pool)} 人，其中Ⅰ–Ⅱ阶 {len(early)} 人')
        rows.append({'side':side,'score':round(score,2),'covenants':names,'route':best,'reasons':reasons,'available_count':len(pool),
                     'guide_source_ids':guides[0]['source_ids'] if guides else []})
    rows.sort(key=lambda r:(-r['score'],r['side']));tie=abs(rows[0]['score']-rows[1]['score'])<1
    return {'side':None if tie else rows[0]['side'],'groups':rows,'provisional':opening.get('ban_status')!='derived',
            'basis':'按目标盟约、低阶成型费用、叠层能力与已整理攻略的可用条件排序；两组分别重算禁用池。匹配排序为助手推断，不代表作者排名、胜率或敌方克制。'}


def describe(db,opening,target='',compact_view=False):
    if not opening:return '截取“确认本局信息”界面后，按盟约图标推算禁用名单。'
    mode=opening.get('mode');side={'left':'左组','right':'右组'}
    lines=[{'solo':'单人开局 / 左右两组选一','coop':'联机开局 / 固定配置，无需选择','fixed':'局内信息 / 本局禁选核对' if opening.get('context')=='in_match' else '核心全部启用 / 无需选择','unknown':'开局信息 / 布局未完整显示'}[mode]]
    if mode=='solo' and not core_unrestricted(opening):lines.append('当前高亮：'+side.get(opening.get('selected'),'待确认'))
    rec=recommendation(db,opening,target)
    if rec:
        lines+=['起步推荐：'+(side[rec['side']] if rec['side'] else '两组接近，按目标盟约选择')+('（图标未齐，暂定）' if rec['provisional'] else '')]
        for item in rec['groups']:
            if compact_view and rec['side'] and item['side']!=rec['side']:continue
            lines+=['\n'+side[item['side']]+' / '+' · '.join(item['covenants']),*item['reasons']]
            if item['route']:lines.append('起步候选：'+'、'.join(item['route']['operators']))
        if not compact_view:lines+=['',rec['basis']]
    core=[e['name'] for e in opening['core'] if e['state']=='grey']
    extra=[e['name'] for e in opening['additional'] if e['state']=='grey' and e['name'] in rules()['small']]
    lines+=['\n禁核心 / '+ban_summary(opening,'core'),'禁附加 / '+ban_summary(opening,'additional')]
    statuses=availability(db,opening);banned=[db.ops[oid]['name'] for oid,v in statuses.items() if v['status']=='banned'];unknown=sum(v['status']=='unknown' for v in statuses.values())
    lines.append(f'推算禁用 {len(banned)} 人 · 待确认 {unknown} 人')
    if not compact_view:
        lines+=['、'.join(banned),'规则：有主核心的干员按主核心判断，附加盟约禁选不额外排除；无主核心时，全部附加盟约均被禁才排除。多核心按原主核心归属；独行不参与禁选。']
    if opening['ban_status']!='derived':lines.append('图标未齐，只列确定禁用者，其余保留待确认。')
    return '\n'.join(lines)


def validate(opening,db):
    if opening is None:return
    if not isinstance(opening,dict) or opening.get('mode') not in ('solo','coop','fixed','unknown'):raise ValueError('开局信息格式无效')
    if opening.get('context','briefing') not in ('briefing','in_match'):raise ValueError('禁选信息来源格式无效')
    if opening.get('selected') not in (None,'left','right'):raise ValueError('开局选择无效')
    groups=opening.get('groups')
    if not isinstance(groups,dict) or set(groups)-{'left','right'}:raise ValueError('开局分组无效')
    allcore={c['name'] for c in db.covenants if c['type']=='核心盟约'}
    for names in groups.values():
        if not isinstance(names,list) or len(names)!=5 or len(set(names))!=5 or set(names)-allcore:raise ValueError('核心盟约分组无效')
    if opening['mode']=='solo' and not core_unrestricted(opening) and (set(groups)!={'left','right'} or set(groups['left'])&set(groups['right'])):raise ValueError('核心盟约分组不完整')
    for kind in ('core','additional'):
        entries=opening.get(kind);valid_names={c['name'] for c in db.covenants if (c['type']=='核心盟约')==(kind=='core')}
        if not isinstance(entries,list) or len(entries)>len(valid_names):raise ValueError('盟约观察记录无效')
        if any(not isinstance(e,dict) or e.get('name') not in valid_names or e.get('state') not in ('lit','grey','unknown') for e in entries):raise ValueError('盟约观察记录无效')
        if len({e['name'] for e in entries})!=len(entries):raise ValueError('盟约记录重复')
    recompute(db,opening)
