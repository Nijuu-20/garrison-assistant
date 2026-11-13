from pathlib import Path
import hashlib,json,re
from garrison.core import Database
source=Path(__file__).parent/'tests/fixtures/ban-recommendation.html'
text=source.read_text('utf8');data=json.loads(re.search(r'<script>const DATA = (.*?);</script>',text,re.S).group(1))
db=Database();mapping={o['name']:{'core':o['core'],'additional':o['add']} for o in data['ops']}
missing=[o for o in db.ops.values() if o['name'] not in mapping]
print('Source mapping',len(mapping),'Desktop extra:',[(o['name'],o['core_covenants'],o['additional_covenants']) for o in missing])
out=Path(__file__).parent/'assets/opening/ban-rules.json'
out.write_text(json.dumps({'source_name':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'rule':'if primary core exists: primary core decides; otherwise: nonempty additional covenants all banned',
 'correction':{'source':'user live-game observation, 2026-11-13','case':'乌萨斯可用、突袭被禁时仍可获取赫拉格','scope':'主核心优先，替代原网页 excluded() 的 OR 判断；保留原盟约归属映射'},
 'big':data['big'],'small':[c for c in data['small'] if c!='独行'],'operators':mapping},ensure_ascii=False,indent=2),'utf8')
