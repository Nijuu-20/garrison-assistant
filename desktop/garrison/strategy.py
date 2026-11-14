"""Authored guide retrieval. Library text stays intact; matching is app inference."""
from __future__ import annotations
import copy,hashlib,html,json,re,sys
from functools import lru_cache
from pathlib import Path


def asset_root():
    return (Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])/'assets/strategy'


@lru_cache(maxsize=1)
def library():
    data=json.loads((asset_root()/'knowledge.json').read_text('utf8'))
    if len(data.get('routes',[]))!=11 or len(data.get('sources',[]))!=20:raise ValueError('攻略知识库不完整')
    return data


@lru_cache(maxsize=20)
def skill_text(relative='SKILL.md'):
    # All callers use package-owned names, never model-supplied paths.
    path=asset_root()/'skill'/relative
    return path.read_text('utf8')


# These are conservative retrieval conditions, not source win-rate rankings.
# variant=None denotes a family overview with ALL route authors credited.
PROFILES=[
    dict(id='R01-suzuran',route='R01',variant=0,commands=['御守之力'],required=['炎','灵巧'],essential=['仇白','云迹'],targets=['炎','灵巧'],ops=[0],gear=[]),
    dict(id='R01-du',route='R01',variant=1,commands=['广交豪杰'],required=['炎','灵巧','坚守','聚合'],essential=['风絮','余','仇白'],targets=['炎','灵巧'],ops=[1,2,3],gear=[1]),
    dict(id='R02',route='R02',commands=[],required=['卡西米尔','突袭'],essential=['砾','瑕光','历阵锐枪芬','玛恩纳','远牙'],targets=['卡西米尔','突袭']),
    dict(id='R03',route='R03',commands=['暴躁铁皮'],starter='“暴躁铁皮”',required=['灵巧','奇迹'],essential=['“暴躁铁皮”','云迹','承曦格雷伊'],targets=['灵巧','奇迹']),
    dict(id='R04',route='R04',commands=[],required=['乌萨斯','奥术'],essential=['维伊','霍尔海雅','塔露拉'],targets=['乌萨斯','奥术']),
    dict(id='R05',route='R05',commands=['暴躁铁皮'],starter='“暴躁铁皮”',required=['乌萨斯','卡西米尔','不屈','奇迹','灵巧'],essential=['“暴躁铁皮”','砾','云迹'],targets=['卡西米尔','乌萨斯','不屈']),
    dict(id='R06',route='R06',commands=['暴躁铁皮'],starter='“暴躁铁皮”',required=['精准','灵巧','奥术'],essential=['“暴躁铁皮”','云迹','承曦格雷伊','霍尔海雅'],targets=['精准','灵巧','奥术']),
    dict(id='R07',route='R07',commands=['统御号令'],required=['精准','灵巧'],essential=['空弦','承曦格雷伊','云迹'],targets=['精准','灵巧']),
    dict(id='R08',route='R08',commands=[],required=['莱塔尼亚','精准','奥术'],essential=['黑键','霍尔海雅'],targets=['莱塔尼亚','精准','奥术']),
    dict(id='R09',route='R09',commands=['全场聚焦'],required=['莱塔尼亚','奥术'],essential=['霍尔海雅','黑键'],targets=['莱塔尼亚','奥术']),
    dict(id='R10',route='R10',commands=['变形同构'],required=['莱塔尼亚','精准','奥术'],essential=['空弦','霍尔海雅'],targets=['莱塔尼亚','精准','奥术']),
    dict(id='R11',route='R11',variant=0,commands=['崇高牺牲'],required=['阿戈尔'],essential=['斯卡蒂','深巡'],targets=['阿戈尔'],ops=[0,1,2,3,4]),
]

# Operation indices refer to the original summary, never newly invented steps.
STAGES={
 'R01':[[0,1],[0,2],[0,3]],'R02':[[0],[1,2],[3,4]],'R03':[[0,1,2],[3,4],[3,4]],
 'R04':[[0,1],[1,2],[3,4]],'R05':[[0,1],[2,3],[3,4]],'R06':[[0,1],[2,3],[3,4]],
 'R07':[[0,1],[2],[3]],'R08':[[0,1],[2,3],[3,4]],'R09':[[0,1],[1,2,3],[3,4]],
 'R10':[[0],[2,3],[3,4]],'R11':[[0,1],[2,3],[3,4]],
}


def pool(db,state):
    from .opening import availability
    if state.get('opening'):
        if state['field_meta'].get('opening_snapshot',{}).get('uncertain'):return set(),set(),True
        status=availability(db,state['opening']);allowed={oid for oid,v in status.items() if v['status']=='available'}
        banned={e['name'] for group in ('core','additional') for e in state['opening'][group] if e['state']=='grey'}
        return allowed,banned,state['opening'].get('ban_status')!='derived'
    return set(db.ops),set(),True


def mentioned(db,text):
    """Longest exact names first, so pure/alter names cannot contaminate bans."""
    aliases={n:n for n in db.by_name}
    for alias,name in library()['aliases'].items():
        if name in db.by_name:
            for short in alias.split('/'):aliases[short]=name
    found=set();rest=text
    for name in sorted(db.equipment,key=len,reverse=True):rest=rest.replace(name,' ')
    for alias in sorted(aliases,key=len,reverse=True):
        if len(alias)<2:continue
        if alias in rest:found.add(aliases[alias]);rest=rest.replace(alias,' ')
    return found


def safe_excerpt(db,state,text):
    allowed,banned,_=pool(db,state)
    covenant_text=text
    for name in sorted(db.equipment,key=len,reverse=True):covenant_text=covenant_text.replace(name,' ')
    if any(n in covenant_text for n in banned):return False
    if any(len(n)==1 and n in covenant_text and op['operator_id'] not in allowed for n,op in db.by_name.items()):return False
    return all(db.by_name[n]['operator_id'] in allowed for n in mentioned(db,text))


def route_identity(profile_id):
    profile=next((p for p in PROFILES if p['id']==profile_id),None)
    if not profile:return None
    route=next(r for r in library()['routes'] if r['id']==profile['route'])
    variant=route['variants'][profile['variant']] if 'variant' in profile else None
    return {'id':profile['id'],'route_id':route['id'],'title':variant['name'] if variant else route['title']}


def lineup_planning_ready(state):
    return (state.get('round') or 0)>=3 and state.get('phase') in ('整备','作战')


def route_matches(db,state,limit=3):
    from .core import fingerprint
    disabled=set(getattr(db,'disabled_guide_routes',[]))
    key=(fingerprint(state),bool(state['field_meta'].get('opening_snapshot',{}).get('uncertain')),tuple(sorted(disabled)))
    cached=getattr(db,'_strategy_matches',None)
    if cached and cached[0]==key:return copy.deepcopy(cached[1][:limit])
    allowed,banned,conditional=pool(db,state);present={u['op_id'] for u in state['units']}
    shop={x['op_id'] for x in state['shop']};commands=set(state['strategies']);routes={r['id']:r for r in library()['routes']};ranked=[]
    if not allowed:return []
    for profile in PROFILES:
        if state.get('route_lock') and profile['id']!=state['route_lock']:continue
        if profile['route'] in disabled:continue
        route=routes[profile['route']]
        if set(profile['required'])&banned:continue
        if any(n not in db.by_name or db.by_name[n]['operator_id'] not in allowed for n in profile['essential']):continue
        starter=db.by_name.get(profile.get('starter'),{}).get('operator_id')
        command_hit=bool(commands&set(profile['commands']))
        if profile['commands'] and not (command_hit or starter in present):continue
        # The two Yan variants have different lineups, even though they share R01.
        names=(['仇白','云迹'] if profile['id']=='R01-suzuran' else
               ['风絮','余','仇白','华法琳'] if profile['id']=='R01-du' else route['core_operators'])
        core=[db.by_name[n]['operator_id'] for n in names if n in db.by_name and db.by_name[n]['operator_id'] in allowed]
        target=state['target'] in profile['targets'];hits=present&set(core);offers=shop&set(core)
        opening_only=bool(state.get('opening')) and not (state['target'] or present or shop or commands)
        proactive=lineup_planning_ready(state)
        if not (state.get('route_lock') or target or hits or offers or command_hit or opening_only or proactive):continue
        score=70*target+45*command_hit+14*len(hits)+6*len(offers)
        # Round-three planning does not waive strategy or ban requirements.
        operations=[route['operation'][i] for i in profile.get('ops',range(len(route['operation'])))]
        transition_names=set().union(*(mentioned(db,t) for t in operations if safe_excerpt(db,state,t))) if proactive else set()
        transition_ids=({db.by_name[n]['operator_id'] for n in transition_names}&allowed)-set(core)
        support=present&transition_ids
        if proactive:score+=4*len(support)
        if not hits and not target and not command_hit:
            # Opening comparison only: cheap accessible pieces, no assumed shop.
            score+=max(0,15-sum(sorted(db.ops[o]['recruit_cost'] for o in core)[:3]))
        variant=route['variants'][profile['variant']] if 'variant' in profile else None
        sources=variant['sources'] if variant else route['source_ids']
        authors=variant['authors'] if variant else route['authors']
        phase=0 if state['level'] is None or state['level']<=2 else 1 if state['level']<=4 else 2
        indices=STAGES[route['id']][phase]
        phase_operations=[route['operation'][i] for i in indices if i in profile.get('ops',range(len(route['operation'])))]
        equipment=[route['equipment'][i] for i in profile.get('gear',range(len(route['equipment'])))]
        ranked.append({'id':profile['id'],'route_id':route['id'],'title':variant['name'] if variant else route['title'],
            'variant':variant['name'] if variant else None,'authors':authors,'source_ids':sources,'score':score,
            'core_ids':core,'targets':[n for n in profile['targets'] if n not in banned],
            'conditional':conditional,'present_ids':sorted(hits),'shop_ids':sorted(offers),
            'lineup_planning':proactive,'transition_ids':sorted(support),
            'needs_review':any(u.get('sprite_missing') for u in state['units']),
            'operation':[t for t in operations if safe_excerpt(db,state,t)],
            'phase_operation':[t for t in phase_operations if safe_excerpt(db,state,t)],
            'equipment':[t for t in equipment if safe_excerpt(db,state,t)],
            'positioning':[t for t in route['positioning'] if safe_excerpt(db,state,t)],
            'limits':route['limits'],'variants':[variant] if variant else route['variants'],
            'match_reason':'延续已锁定路线' if state.get('route_lock') else '延续目标盟约' if target else '匹配已选策略' if command_hit else '匹配已有成员与可购牌' if hits or offers else '根据已有过渡成员选择起步路线' if support else '第 3 回合起按可用盟约与低阶起步成本规划' if proactive else '按本组可用核心比较起步条件'})
    ranked.sort(key=lambda r:(-r['score'],r['id']));db._strategy_matches=(key,copy.deepcopy(ranked))
    return ranked[:limit]


def member_roles(db,state,match):
    allowed,_,_=pool(db,state);route=next(r for r in library()['routes'] if r['id']==match['route_id'])
    extra=set().union(*(mentioned(db,t) for t in match['operation'])) if match['operation'] else set()
    core=set(match['core_ids']);owned={u['op_id'] for u in state['units']}
    ids=core|{db.by_name[n]['operator_id'] for n in extra}
    level=state['level'];rows=[]
    for oid in ids&allowed:
        op=db.ops[oid];is_core=oid in core
        role='核心' if is_core else '可选终端' if op['tier']>=5 else '过渡 / 可选补位'
        # A known late terminal is not promoted to an early shop refresh target.
        path='当前商店' if any(i['op_id']==oid for i in state['shop']) else '等级待确认' if level is None else '当前等级常规招募范围' if op['tier']<=level else '需晋升奖励等特殊获取；不保证出现' if op['tier']==level+1 else '后续升本或已确认的特殊获取途径'
        priority=(30 if is_core else 10)+(12 if oid not in owned else 0)+(8 if path=='当前商店' else 0)-op['tier']
        rows.append({'kind':'operator','op_id':oid,'name':op['name'],'role':role,'acquisition':path,'priority':priority,
                     'reason':f'{match["title"]} / {role}；{path}'+('；已记录持有，待核对' if any(u['op_id']==oid and u.get('sprite_missing') for u in state['units']) else '')+('；本局可用性待确认' if match['conditional'] else '')})
    return sorted(rows,key=lambda i:(-i['priority'],i['name']))


def guide_boosts(db,state):
    matches=route_matches(db,state,1)
    if not matches:return {},None
    match=matches[0];return {i['op_id']:(80 if i['role']=='核心' else 24) for i in member_roles(db,state,match)},match


def source_records(ids):
    allowed=set(ids);return [copy.deepcopy(s) for s in library()['sources'] if s['id'] in allowed]


def local_plan(db,state,compact=False,profile_id=None):
    from .core import recommend,validate_actions,roster_review_note,shop_review_note
    from .tracking import normalize_items
    matches=route_matches(db,state,20 if profile_id else 3)
    if profile_id:
        selected=next((m for m in matches if m['id']==profile_id),None)
        if selected:matches=[selected,*[m for m in matches if m['id']!=profile_id]][:3]
    if not matches:
        foundation=next((f for f in library()['foundations'] if f['name']==state['target'] and safe_excerpt(db,state,f['summary'])),None)
        message=('机制参考：'+foundation['summary']+'\n尚无满足策略与禁选条件的完整路线，先核对策略和当前商店。') if foundation else '先确认本局禁选、策略、现有成员和商店，再从已整理攻略中选择路线。'
        if state.get('opening') and state['field_meta'].get('opening_snapshot',{}).get('uncertain'):message='先重新确认本局禁选，再按攻略决定购买与路线。'
        locked=route_identity(state.get('route_lock'))
        if locked:message='已锁定路线：'+locked['title']+'。\n当前禁选、策略或路线启用条件不满足，暂停该路线的购买名单。请核对条件，或手动解锁后重新选择；不会自动换线。'
        if roster_review_note(state):message+='\n'+roster_review_note(state)
        if shop_review_note(state):message+='\n'+shop_review_note(state)
        return {'source':'本地攻略','analysis':message,'recommendation_list':[],'source_ids':['S03'] if foundation else [],'routes':[]}
    chosen=matches[0];ranked=recommend(db,state,True)
    feasible=[r for r in ranked if validate_actions(db,state,[{'type':'buy','slot':r['slot']}])[0]['valid']]
    lines=[('已锁定路线：' if state.get('route_lock') else '参考路线：')+chosen['title']+'。',chosen['match_reason']+'；先按当前可行步骤推进。']
    if lineup_planning_ready(state) and not state.get('route_lock'):
        lines.append('目标阵容已列在下方，可点选或一键追踪；认可方向后可锁定路线。高阶成员是后续目标，当前购买仍看商店与获取条件。')
    if roster_review_note(state):lines.append(roster_review_note(state))
    if shop_review_note(state):lines.append(shop_review_note(state))
    if chosen['conditional']:lines.append('本局禁选尚未确认，路线和候选只作待确认参考。')
    if feasible:
        best=feasible[0];lines+=['',f'当前优先：购买 {best["name"]}，花费 {best["cost"]}，余 {state["gold"]-best["cost"]} 资金。',
            '理由：'+'；'.join(best['reasons'][:2])+'。购买后先进入整备区，部署后才按规则计算盟约。']
    elif state['shop']:lines+=['','当前先核对商品、实际资金与购买条件，不照抄攻略的固定花费。']
    else:lines+=['','先展开当前商店；下方为值得寻找的候选，并不表示当前可买。']
    operations=chosen['phase_operation']
    if operations:
        lines+=['','阶段参考（条件满足后）：',*operations[:1 if compact else 2]]
    if chosen['equipment']:lines+=['','装备方向：'+chosen['equipment'][0]]
    if any('变形同构体' in t for t in chosen['equipment']):lines.append('转职需变形同构体与对应装备同时满足，未取得组件前不计作已经转职。')
    if not compact and chosen['positioning']:lines+=['','站位条件：'+chosen['positioning'][0]]
    if len(chosen['variants'])>1:
        lines+=['','作者的升本与转型变体分开参考，未录入血量与下波敌人时不强制套用速本时间表。']
    if not compact and len(chosen['variants'])==1:
        for variant in chosen['variants'][:3]:
            if safe_excerpt(db,state,variant['detail']):lines+=['\n'+variant['name']+'（'+'、'.join(variant['authors'])+'）：'+variant['detail']]
    alternative=next((m for m in matches[1:] if m['route_id']!=chosen['route_id']),None)
    lines+=['','备选条件：'+('核心迟迟不到时，可重新核对「'+alternative['title']+'」的策略与禁选要求；不要直接混用两套终局。' if alternative else '核心未到先补现有阵容质量；按已知资金与实际来牌重新评估，不假设刷新必出。')]
    if state['field_meta'].get('battle_roster',{}).get('uncertain'):lines.append('当前仅按已确认成员规划；晋升前先核对完整阵容与精锐。')
    members=member_roles(db,state,chosen)[:8]
    gear_text='\n'.join(chosen['equipment']);equipment=[]
    for name in sorted(db.equipment,key=lambda n:(gear_text.find(n) if n in gear_text else 10**6,-len(n))):
        if name in gear_text:equipment.append({'kind':'equipment','name':name,'reason':chosen['title']+' / 装备方向；以实际持有、组件与携带条件为准'})
    choices=normalize_items(db,[*members,*equipment[:4]],state,12)
    sources=list(dict.fromkeys(chosen['source_ids']+(alternative['source_ids'] if alternative else [])))
    return {'source':'本地攻略','analysis':'\n'.join(lines),'recommendation_list':choices,'source_ids':sources,'routes':matches}


def ai_material(db,state):
    matches=route_matches(db,state,3);route_ids=list(dict.fromkeys(m['route_id'] for m in matches))
    routes={r['id']:r for r in library()['routes']}
    # Full selected route documents retain variant boundaries and source warnings.
    ids=list(dict.fromkeys(['S03',*[sid for rid in route_ids for sid in routes[rid]['source_ids']]]))
    return {'name':'garrison-strategy-guide','version':library()['version'],'game_version':library()['game_version'],
        'instructions_file':'SKILL.md','index':skill_text('references/index.md'),
        'mechanics':skill_text('references/mechanics.md'),
        'routes':[{'route_id':rid,'path':f'references/routes/{rid}.md','content':skill_text(f'references/routes/{rid}.md')} for rid in route_ids],
        'matches':matches,'sources':source_records(ids),'constraints':library()['ai_constraints'],
        'disabled_routes':sorted(getattr(db,'disabled_guide_routes',[])),
        'locked_route':route_identity(state.get('route_lock')),
        'lineup_planning':{'ready':lineup_planning_ready(state),'starts_at_round':3,
            'guidance':'第 3 回合起先给出可追踪的目标阵容与装备，区分过渡成员、核心和后期目标；不用等核心已持有或商店齐全。购买建议仍需实际商品、费用与获取条件。'},
        'route_lock_satisfied':not state.get('route_lock') or bool(matches),
        'retrieval_note':'匹配排序是助手根据局面作出的推断，不是作者排名或胜率。只采用满足本局禁选与策略条件的分支；完整文件中的其他作者变体是比较资料，不代表当前可执行。'}


def resolve_ai_sources(db,state,values):
    allowed={s['id'] for s in ai_material(db,state)['sources']}
    selected=[v for v in values if isinstance(v,str) and v in allowed] if isinstance(values,list) else []
    return list(dict.fromkeys(selected))


def sources_html(ids,prefix='攻略来源'):
    links=[]
    for source in source_records(ids):
        # Preserve all actual author roles, excluding acknowledgements.
        authors='、'.join(a['name'] for a in source['authors'] if '不列为' not in a['role'])
        role='；'.join(a['name']+'：'+a['role'] for a in source['authors'])
        links.append(f'<a href="{html.escape(source["url"],quote=True)}" title="{html.escape(role,quote=True)}" style="color:#8caaa8">{html.escape(authors)} / {html.escape(source["id"])}</a>')
    return prefix+'：'+' · '.join(links) if links else ''


def bundled_guides():
    return [{'name':r['title'],'text':skill_text(f'references/routes/{r["id"]}.md'),
             'version':library()['game_version']+' / '+library()['version'],'source_ids':r['source_ids'],
             'favorite':False,'team':None,'builtin':True,'route_id':r['id']} for r in library()['routes']]


def verify_bundle():
    manifest=json.loads((asset_root()/'manifest.json').read_text('utf8'))
    return all(hashlib.sha256((asset_root()/path).read_bytes()).hexdigest()==digest for path,digest in manifest['sha256'].items())
