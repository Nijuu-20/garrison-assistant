"""Solo briefing presentation and evidence tracking; never merges missing icons."""
import copy,json,time
from .opening import confirmation_problem,snapshot_key


class SoloBriefing:
    def __init__(self):self.reset()
    def reset(self):
        self.opening=None;self.result=None;self.complete=False;self.departed=False
        self.key=None;self.candidate=None;self.count=0;self.gaps=0;self.last_good=0;self.exit_count=0
        self.held=False;self.uncertain=False;self.conflict=False;self.message='';self.ready_field=None
    def seed(self,opening):
        self.opening=copy.deepcopy(opening);self.complete=True;self.departed=False
        self.key=None;self.candidate=None;self.count=0;self.gaps=0;self.last_good=0;self.exit_count=0
        self.held=False;self.uncertain=False;self.conflict=False;self.message='';self.ready_field=None
    def restart_evidence(self):
        self.key=None;self.candidate=None;self.count=0;self.gaps=0;self.last_good=0;self.ready_field=None
    def observe(self,db,result,threshold,repeats=2,now=None):
        now=time.monotonic() if now is None else now;opening=result.get('opening')
        self.result=result;self.ready_field=None
        if opening and opening.get('mode')=='coop':self.reset();return False
        if not self.opening and (not opening or opening.get('mode') not in ('solo','fixed')):return False
        repeats=max(2,repeats)
        field=next((f for f in result.get('fields',[]) if f['key']=='opening_snapshot'),None)
        good=bool(opening and opening.get('mode') in ('solo','fixed') and not confirmation_problem(db,opening)
                  and field and field.get('value') and field['confidence']>=threshold)
        if good:
            try:good=snapshot_key(json.loads(field['value']))==snapshot_key(opening)
            except (ValueError,TypeError,KeyError):good=False
        if good:
            key=snapshot_key(opening)
            self.count=self.count+1 if key==self.key and (not self.last_good or now-self.last_good<=8) else 1
            self.key=key;self.candidate=copy.deepcopy(opening);self.last_good=now;self.gaps=0;self.exit_count=0;self.departed=False
            # Show the first complete observation immediately for manual review,
            # but replace an existing complete view only after repeated agreement.
            if not self.complete or key==snapshot_key(self.opening) or self.count>=repeats:
                self.opening=copy.deepcopy(opening);self.complete=True;self.held=False;self.message=''
                if self.count>=repeats:
                    self.ready_field=field;self.uncertain=False;self.conflict=False
            else:
                self.held=True;self.uncertain=True;self.conflict=True;self.message='选组或盟约出现变化，保留上次结果，等待核对'
            return True
        self.gaps+=1;self.held=True
        if not self.opening:
            self.opening=copy.deepcopy(opening);self.complete=False
        elif not self.complete and opening:
            # Preserve the richest whole observation, not a union of old icons.
            size=lambda o:sum(len(o.get(k,[])) for k in ('core','additional'))
            if size(opening)>size(self.opening):self.opening=copy.deepcopy(opening)
        def contradicts(prior):
            if not opening or not prior:return False
            states={e['name']:e['state'] for k in ('core','additional') for e in prior.get(k,[])}
            return (any(e.get('state') in ('lit','grey') and states.get(e['name'])!=e['state'] for k in ('core','additional') for e in opening.get(k,[])) or
                    (opening.get('selected') in ('left','right') and opening['selected']!=prior.get('selected')) or
                    any(side in prior.get('groups',{}) and set(names)!=set(prior['groups'][side]) for side,names in opening.get('groups',{}).items()))
        contradiction=self.complete and contradicts(self.opening)
        # During a side change the held display is deliberately old. A partial
        # frame agreeing with the NEW candidate must not reset that candidate's
        # evidence just because it differs from the held display.
        if contradicts(self.candidate) or self.gaps>1 or (self.last_good and now-self.last_good>8):
            self.key=None;self.candidate=None;self.count=0
        # A single incomplete, non-contradictory frame does not revoke a known
        # pool; a contradiction or sustained loss requires fresh confirmation.
        self.uncertain|=bool(contradiction or self.gaps>=3 or (self.last_good and now-self.last_good>8))
        self.conflict|=bool(contradiction)
        self.message=('画面发生变化，等待重新核对开局信息' if contradiction else
                      '暂未读全开局信息，保留上次完整结果' if self.complete else '等待完整的开局盟约图标')
        fields={f['key']:f for f in result.get('fields',[])}
        hud=not opening and all(fields.get(k,{}).get('value') is not None and fields[k]['confidence']>=threshold for k in ('phase','round','level','gold'))
        hud=bool(hud and fields['phase']['value'] in ('整备','作战','结束'))
        self.exit_count=self.exit_count+1 if hud else 0
        if self.exit_count>=repeats:
            self.opening=None;self.complete=False;self.departed=True;self.held=False;self.message=''
            return False
        return True
