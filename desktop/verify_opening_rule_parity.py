"""Keep HTML mappings; validate the live-observation correction and record divergence."""
import hashlib,itertools,json,re,subprocess,random
from pathlib import Path
from garrison.core import Database
from garrison.opening import availability,rules
from garrison import __version__
source=Path(__file__).parent/'tests/fixtures/ban-recommendation.html';text=source.read_text('utf8')
assert hashlib.sha256(source.read_bytes()).hexdigest()==rules()['source_sha256']
data=json.loads(re.search(r'<script>const DATA = (.*?);</script>',text,re.S).group(1));db=Database()
big=data['big'];small=[c for c in data['small'] if c!='独行'];rng=random.Random(17)
plans=[{'big':rng.sample(big,5),'small':rng.sample(small,5)} for _ in range(100)]
plans+=[{'big':[],'small':[]},{'big':big,'small':[]},{'big':[],'small':small}]
plans +=[{'big':[c],'small':[]} for c in big]+[{'big':[],'small':[c]} for c in small]
script='const DATA='+json.dumps(data,ensure_ascii=False)+';const plans='+json.dumps(plans,ensure_ascii=False)+';let state={bans:{big:[],small:[]}};\n'
for name in ('bigBanned','smallBanned','excluded'):
    script+=re.search(r'function '+name+r'\([^)]*\)\{.*?\n?\}',text,re.S).group(0)+'\n'
script+='console.log(JSON.stringify(plans.map(b=>{state.bans=b;return DATA.ops.filter(excluded).map(o=>o.name).sort();})));'
out=Path(__file__).parent/'build/opening-recognition';js=out/'source-rule-check.js';js.write_text(script,'utf8')
actual=json.loads(subprocess.run(['node',str(js)],check=True,capture_output=True,encoding='utf8').stdout)
differences=0
for i,plan in enumerate(plans):
    o={'core':[{'name':c,'state':'grey' if c in plan['big'] else 'lit'} for c in big],
       'additional':[{'name':c['name'],'state':'grey' if c['name'] in plan['small'] else 'lit'} for c in db.covenants if c['type']!='核心盟约']}
    result=sorted(db.ops[oid]['name'] for oid,v in availability(db,o).items() if v['status']=='banned' and db.ops[oid]['name'] in rules()['operators'])
    expected=sorted(op['name'] for op in data['ops'] if (op['core'] in plan['big'] if op['core'] else bool(op['add']) and all(c in plan['small'] for c in op['add'])))
    assert result==expected,(i,set(result)^set(expected))
    # The only departure from the old HTML is retaining operators with an
    # enabled primary core whose additional memberships were all disabled.
    retained=set(actual[i])-set(result)
    assert not (set(result)-set(actual[i]))
    assert all(op['core'] and op['core'] not in plan['big'] for op in data['ops'] if op['name'] in retained)
    differences+=len(retained)
report={'version':__version__,'passed':True,'configurations':len(plans),'operators_from_html':141,'comparisons':len(plans)*141,
        'rule':'primary core decides when present; otherwise all additional banned','correction_source':'user live Hellagur observation, 2026-11-13','intentional_differences_from_original_html':differences,
        'source_sha256':rules()['source_sha256'],'additional_desktop_entries':['盟约·辅助干员','“暴躁铁皮”']}
(out/'rule-parity.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8');print(json.dumps(report,ensure_ascii=False))
