"""Player-facing advice shared by the main and floating windows. No diagnostics."""
from __future__ import annotations
import copy
from .core import covenant_status,recommend,fingerprint,validate_actions
from .opening import availability,recommendation as opening_recommendation,recompute,core_unrestricted,snapshot_key


def text(value,limit=600):
    return value.strip()[:limit] if isinstance(value,str) else ''


def ban_context(db,state):
    opening=state.get('opening')
    if not opening:
        return {'status':'unknown','core_banned':[],'additional_banned':[],
                'banned_operators':[],'unknown_operator_ids':[], 'available_operator_ids':[],
                'guidance':'尚未取得本局禁选；不得把空禁选列表解释为全员可用。可见商店可作为当前商品证据，其余路线须注明待确认。'}
    uncertain=state['field_meta'].get('opening_snapshot',{}).get('uncertain',False)
    status='needs_review' if uncertain else 'confirmed' if opening.get('ban_status')=='derived' else 'partial'
    pool=availability(db,opening)
    return {'status':status,'core_banned':[e['name'] for e in opening['core'] if e['state']=='grey'],
            'additional_banned':[e['name'] for e in opening['additional'] if e['state']=='grey'],
            'core_available':[e['name'] for e in opening['core'] if e['state']=='lit'],
            'additional_available':[e['name'] for e in opening['additional'] if e['state']=='lit'],
            'banned_operators':[{'op_id':oid,'name':db.ops[oid]['name'],'reason':v['reason']} for oid,v in pool.items() if v['status']=='banned'],
            'unknown_operator_ids':[oid for oid,v in pool.items() if v['status']=='unknown'],
            'available_operator_ids':[] if uncertain else [oid for oid,v in pool.items() if v['status']=='available'],
            'rule':'有主核心的干员仅按主核心判断可用性，附加盟约禁选不额外排除；无主核心的干员才在全部附加盟约被禁时排除。主核心未知时不得由附加盟约猜测。多核心按主核心归属，独行不参与禁选。',
            'guidance':'禁止以禁选盟约作为主力目标，也不可建议购买或等待被禁干员。变更禁选后必须重新分析。'}


def target_candidates(db,state,limit=3):
    constraints=ban_context(db,state)
    if constraints['status']=='needs_review':return []
    banned=set(constraints['core_banned'])|set(constraints['additional_banned'])
    allowed=set(constraints['available_operator_ids']) if state.get('opening') else set(db.ops)
    present={u['op_id'] for u in state['units'] if not u.get('sprite_missing')}
    shop={x['op_id'] for x in state['shop']};rows=[]
    from .strategy import route_matches
    guides=route_matches(db,state,1);guide=guides[0] if guides else None
    guide_targets=set(guide['targets']) if guide else set()
    for c in covenant_status(db,state):
        if (c['type']!='核心盟约' and state['target']!=c['name'] and c['name'] not in guide_targets) or c['name'] in banned:continue
        pool=[o for oid,o in db.ops.items() if oid in allowed and c['name'] in o['covenants']]
        if len(pool)<c['activation_count']:continue
        if not present and not shop and not state.get('opening') and state['target']!=c['name']:continue
        candidates=sorted([o for o in pool if o['operator_id'] not in c['members_present']],
                          key=lambda o:(o['operator_id'] not in shop,o['tier'],o['recruit_cost'],o['name']))[:3]
        base=sorted(pool,key=lambda o:(o['tier'],o['recruit_cost']))[:c['activation_count']]
        start_cost=sum(o['recruit_cost'] for o in base)
        score=c['effective']*12+sum(o['operator_id'] in shop for o in candidates)*5+(45 if state['target']==c['name'] else 0)-start_cost*.15
        if c['name'] in guide_targets:score+=55
        gap=max(0,(c['next'] or c['activation_count'])-c['effective'])
        progress=f'已激活，当前进度 {c["effective"]} 人' if c['active'] else f'当前 {c["effective"]}/{c["activation_count"]}，还差 {gap} 人'
        if c['active'] and c['next']:progress+=f'；距 {c["next"]} 人档还差 {gap}'
        reason='延续已选目标。' if state['target']==c['name'] else '已有成员和商店更接近成型。' if c['count'] or any(o['operator_id'] in shop for o in candidates) else f'低阶起步池基础费用合计约 {start_cost}。'
        if c['name'] in guide_targets:reason='配合攻略「'+guide['title']+'」。'+reason
        rows.append({'name':c['name'],'reason':reason,'progress':progress,'effect':c['effect'],
                     'candidates':[{'op_id':o['operator_id'],'name':o['name'],'in_shop':o['operator_id'] in shop} for o in candidates],
                     'conditional':constraints['status']!='confirmed','score':score})
    return sorted(rows,key=lambda r:(-r['score'],r['name']))[:limit]


def action_title(db,state,action):
    kind=action.get('type');op=db.ops.get(action.get('op_id'),{}).get('name','')
    member=next((u for u in state['units'] if u['uid']==action.get('uid')),None)
    member_name=db.ops[member['op_id']]['name'] if member else '待确认干员'
    if kind=='buy':
        slot=action.get('slot');item=state['shop'][slot] if type(slot) is int and 0<=slot<len(state['shop']) else {}
        name=db.ops.get(item.get('op_id'),{}).get('name',op or '待确认商品')
        position=f'（商店第 {item.get("slot",slot)+1} 格）' if item else ''
        return '购买 '+name+position
    if kind=='promote':return '晋升 '+(op or '待确认干员')
    if kind=='equip':return '将 '+text(action.get('equipment'),80)+' 交给 '+member_name
    if kind=='move':return '将 '+member_name+' 移至'+('战场' if action.get('zone')=='field' else '整备区')
    return {'upgrade':'提升调度中心等级','refresh':'刷新当前商店'}.get(kind,'核对待定操作')


def analysis_text(db,state,result,compact=False):
    if result.get('fingerprint')!=fingerprint(state):return '局面已变化，请重新分析；上一份操作建议已收起。'
    if state.get('opening') and state['field_meta'].get('opening_snapshot',{}).get('uncertain'):
        return '先重新确认本局禁选，再分析购买与目标盟约。'
    actions=validate_actions(db,state,result.get('actions',[]));valid=[a for a in actions if a.get('valid')];invalid=[a for a in actions if not a.get('valid')]
    lines=[text(result.get('goal'),180) if not invalid else '优先执行已确认步骤；其余操作先核对条件。']
    assessment=text(result.get('assessment'),350)
    if assessment:lines+=['',assessment]
    for i,a in enumerate(valid[:3 if compact else 5]):
        lines+=['',f'{i+1}. '+action_title(db,state,a)]
        reason=text(a.get('reason'),180 if compact else 500)
        if reason:lines.append('理由：'+reason)
        benefit=text(a.get('expected_gain'),160 if compact else 400)
        if benefit:lines.append('预期：'+benefit)
        condition=text(a.get('condition'),130 if compact else 350)
        if condition:lines.append('条件：'+condition)
        if a.get('type') in ('buy','upgrade','refresh') and a.get('balance_after') is not None:lines.append(f'按当前价格执行后剩余 {a["balance_after"]} 资金')
    if compact and len(valid)>3:lines+=['','其余步骤可在主窗口查看。']
    for a in invalid[:1 if compact else 5]:
        lines+=['','暂缓'+action_title(db,state,a)+'：'+text(a.get('validation'),180)]
    if not compact:
        for key,title in [('economy','资金安排'),('alternative','备选方案'),('next_round','后续目标'),('explanation','判断依据')]:
            value=text(result.get(key),1400)
            if value:lines+=['',title+'：'+value]
        formation=[text(v,450) for v in result.get('formation',[]) if text(v)]
        if formation:lines+=['','站位与装备：',*['• '+v for v in formation]]
    elif not invalid:
        alternative=text(result.get('alternative'),200)
        if alternative:lines+=['','备选：'+alternative]
    warnings=[text(v,200) for v in result.get('warnings',[]) if text(v)]
    if warnings:lines+=['','先确认：'+'；'.join(warnings[:1 if compact else 5])]
    return '\n'.join(lines).strip()


def overlay_advice(db,state,result=None,opening=None,ai_enabled=False):
    """Only actionable advice, never recognition_status, timestamps or raw fields."""
    if opening:
        if opening.get('context')=='in_match' and not opening.get('_review_message') and snapshot_key(opening)==snapshot_key(state.get('opening')) and not state['field_meta'].get('opening_snapshot',{}).get('uncertain'):
            return overlay_advice(db,state,result,None,ai_enabled)
        if opening.get('_review_blocked'):
            return {'source':'开局核对','analysis':opening['_review_message']+'。\n先保留当前选择，待重新核验完整盟约后再决定路线。',
                    'targets':[],'source_ids':[],'recommendation_list':[]}
        preview=copy.deepcopy(state);preview['opening']=opening
        if opening.get('context')!='in_match':preview['units']=[];preview['shop']=[]
        rec=opening_recommendation(db,opening,state['target']);lines=[]
        if opening['mode']=='solo' and rec:
            side=rec['side'];names={'left':'左组','right':'右组'}
            lines=['起步推荐：'+('优先选择'+names[side] if side else '两组接近，优先保留目标盟约')]
            chosen=next((r for r in rec['groups'] if r['side']==side),rec['groups'][0])
            lines.extend(chosen['reasons'][:1])
            lines.extend(r for r in chosen['reasons'] if r.startswith('可参考攻略'))
            if chosen['route']:lines+=['起步留意：'+'、'.join(chosen['route']['operators'])+'。是否购买以商店和资金为准。']
            if side:
                preview['opening']=copy.deepcopy(opening);preview['opening']['selected']=side
                for e in preview['opening']['core']:e['state']='lit' if e['name'] in opening['groups'][side] else 'grey'
                recompute(db,preview['opening'])
                lines.append('下方目标按'+names[side]+'规划；实际选组后重新确认。')
            if rec['provisional']:lines.append('先补齐盟约信息，再确认选组。')
        elif opening.get('context')=='in_match':
            lines=['核对本局禁选，确认后按当前阵容、装备与资金重新规划。','本次只更新禁选，不重置当前对局。']
        elif core_unrestricted(opening):lines=['本局核心盟约全部启用，无需左右选组。','按目标盟约和当前商店选路线；附加盟约按实际禁选判断。']
        elif opening['mode']=='coop':lines=['联机固定配置，无需选组。','围绕可用盟约准备开局，优先凑齐低阶成员；商店出现前不预设购买。']
        else:lines=['先确认开局盟约，再决定起步路线。']
        from .strategy import route_matches
        guides=route_matches(db,preview,1)
        if opening.get('_review_message'):lines.insert(0,opening['_review_message']+'；以下沿用上次完整结果。')
        return {'source':'局内禁选核对' if opening.get('context')=='in_match' else '开局攻略','analysis':'\n'.join(lines),'targets':target_candidates(db,preview,2),
                'source_ids':guides[0]['source_ids'] if guides else [],'recommendation_list':[]}
    targets=target_candidates(db,state,2)
    fresh=bool(ai_enabled and result and result.get('fingerprint')==fingerprint(state)
               and not any(v.get('uncertain') for k,v in state['field_meta'].items() if k in ('opening_snapshot','gold','phase','shop_snapshot') or k.startswith(('shop:','cost:'))))
    if fresh:
        target=result.get('target_recommendation') or {}
        if target.get('name'):
            choices=target_candidates(db,state,10)
            match=next((c for c in choices if c['name']==target['name']),None)
            if match:targets=[{**match,'reason':text(target.get('reason')) or match['reason']},*[c for c in targets if c['name']!=match['name']]][:2]
        return {'source':'AI 分析','analysis':analysis_text(db,state,result,True),'targets':targets,
                'source_ids':result.get('guide_source_ids',[]),'source_label':result.get('guide_source_label','攻略来源'),
                'recommendation_list':result.get('recommendation_list',[])}
    from .strategy import local_plan
    plan=local_plan(db,state,True)
    if ai_enabled and result:plan['analysis']='局面已变化，先参考当前本地攻略。\n'+plan['analysis']
    return {**plan,'targets':targets}
