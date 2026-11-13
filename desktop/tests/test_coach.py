import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
import httpx
from garrison.core import Database, new_state, fingerprint
from garrison.coach import Coach, api_error
from garrison.storage import DEFAULT_SETTINGS

class Handler(BaseHTTPRequestHandler):
    mode='normal'; requests=[]; received=threading.Event()
    def log_message(self,*args):pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));type(self).requests.append(data);type(self).received.set()
        if self.mode=='slow':time.sleep(2)
        content=json.dumps({'goal':'买入当前商店干员','actions':[{'type':'buy','slot':0,'op_id':'OP001','reason':'补充阵容'},{'type':'buy','slot':0}], 'alternative':'保留本地建议','warnings':[],
            'recommendation_list':[{'kind':'operator','op_id':'OP001','reason':'补齐成员'},{'kind':'equipment','name':'维式重锤','reason':'补充攻击'}]})
        if self.mode=='invalid':content='not json'
        if self.mode=='empty':content=''
        result={'choices':[{'message':{'content':content},'finish_reason':'length' if self.mode=='length' else 'stop'}],'usage':{'prompt_tokens':11,'completion_tokens':9}}
        status=200
        if self.mode=='strict_sol' and ('max_tokens' in data or not data.get('max_completion_tokens')):
            status=400
            result={'error':{'message':"Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead.",'param':'max_tokens','code':'unsupported_parameter'}}
        if self.mode=='error':
            status=400
            result={'error':{'message':"Unsupported parameter: 'max_tokens'; credential test-only",'param':'max_tokens','code':'unsupported_parameter'}}
        if self.mode=='envelope':result={'ok':True}
        body=(b'<html>Not an API</html>' if self.mode=='html' else json.dumps(result).encode())
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (ConnectionAbortedError,BrokenPipeError,ConnectionResetError):pass

@pytest.fixture
def service():
    Handler.mode='normal';Handler.requests=[];Handler.received.clear()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield {'id':'test','url':f'http://127.0.0.1:{server.server_port}/v1','model':'mock'}
    server.shutdown();server.server_close()

def setup():
    d=Database();s=new_state();s.update(gold=6,shop=[{'op_id':'OP001','cost':2}]);settings={**DEFAULT_SETTINGS,'ai_min_interval':0,'ai_timeout':5}
    return d,s,settings

def test_actual_compatible_request_and_sequential_validation(service):
    d,s,cfg=setup();coach=Coach();r=coach.run(d,s,cfg,service,'test-only')
    assert r['fingerprint']==fingerprint(s)
    assert [a['valid'] for a in r['actions']]==[True,False]
    assert coach.calls==1 and coach.input_tokens==11 and coach.output_tokens==9
    payload=Handler.requests[0]
    assert payload['model']=='mock' and payload['messages'][0]['role']=='system'
    assert payload['max_tokens']==2200 and 'max_completion_tokens' not in payload
    assert 'test-only' not in json.dumps(payload)
    assert len(r['recommendation_list'])==2
    context=json.loads(payload['messages'][1]['content'])
    assert len(context['recommendation_catalog']['equipment'])==70 and 'ban_constraints' in context
    from garrison.strategy import skill_text
    assert skill_text() in payload['messages'][0]['content']
    assert 'strategy_guide' in context and context['strategy_guide']['mechanics']==skill_text('references/mechanics.md')

@pytest.mark.parametrize('test,deep,budget,effort',[(True,False,1024,'low'),(False,False,4096,'low'),(False,True,8192,'medium')])
def test_sol_official_parameter_contract(service,test,deep,budget,effort):
    Handler.mode='strict_sol';service['model']='gpt-6.1-sol'
    d,s,cfg=setup();result=Coach().run(d,s,cfg,service,'test-only',test=test,deep=deep)
    payload=Handler.requests[0]
    assert 'max_tokens' not in payload
    assert payload['max_completion_tokens']==budget
    assert payload['reasoning_effort']==effort
    assert payload['response_format']=={'type':'json_object'}
    assert 'JSON' in payload['messages'][0]['content']
    assert result.get('test') if test else isinstance(result['actions'],list)

def test_http_error_preserves_reason_without_key(service):
    Handler.mode='error';d,s,cfg=setup()
    with pytest.raises(ValueError) as caught:Coach().run(d,s,cfg,service,'test-only',test=True)
    message=str(caught.value)
    assert 'HTTP 400' in message and 'max_tokens' in message and 'unsupported_parameter' in message
    assert 'test-only' not in message and '[已隐藏密钥]' in message

@pytest.mark.parametrize('mode,expected',[('empty','有效文本'),('length','输出上限'),('envelope','Chat Completions'),('html','JSON')])
def test_connection_test_rejects_unusable_response(service,mode,expected):
    Handler.mode=mode;d,s,cfg=setup()
    with pytest.raises(ValueError,match=expected):Coach().run(d,s,cfg,service,'',test=True)

def test_api_error_redacts_other_credentials_and_limits_length():
    response=httpx.Response(401,json={'error':{'message':'key actual-secret Bearer other-token sk-example-key\n'+('x'*2000)}})
    message=api_error(response,'actual-secret')
    assert all(secret not in message for secret in ('actual-secret','other-token','sk-example-key'))
    assert '\n' not in message and len(message)<850

def test_api_error_ignores_html_body():
    message=api_error(httpx.Response(502,text='<html>private proxy content</html>'),'')
    assert 'HTTP 502' in message and '<html>' not in message and 'private' not in message

def test_cancel_closes_running_request(service):
    Handler.mode='slow';d,s,cfg=setup();coach=Coach();out=[]
    def work():
        try:coach.run(d,s,cfg,service,'')
        except ValueError as e:out.append(str(e))
    t=threading.Thread(target=work);t.start();assert Handler.received.wait(3);coach.cancel();t.join(1)
    assert not t.is_alive() and out

def test_invalid_response_and_limit(service):
    Handler.mode='invalid';d,s,cfg=setup();cfg['ai_limit']=1;coach=Coach()
    with pytest.raises(ValueError,match='结构化'):coach.run(d,s,cfg,service,'')
    with pytest.raises(ValueError,match='上限'):coach.run(d,s,cfg,service,'')
    assert len(Handler.requests)==1

def test_total_timeout(service):
    Handler.mode='slow';d,s,cfg=setup();cfg['ai_timeout']=.2;coach=Coach()
    with pytest.raises(ValueError,match='超时'):coach.run(d,s,cfg,service,'')

def test_cancel_before_worker_starts(service):
    d,s,cfg=setup();coach=Coach();token=threading.Event();token.set()
    with pytest.raises(ValueError,match='取消'):coach.run(d,s,cfg,service,'',cancel_token=token)
    assert Handler.requests==[]

def test_outbound_payload_explicitly_includes_this_games_bans(service):
    from garrison.opening import recompute
    d,s,cfg=setup()
    s['opening']=recompute(d,{'mode':'coop','groups':{},'selected':None,
      'core':[{'name':c['name'],'state':'grey' if c['name']=='乌萨斯' else 'lit'} for c in d.covenants if c['type']=='核心盟约'],
      'additional':[{'name':c['name'],'state':'grey' if c['name']=='坚守' else 'lit'} for c in d.covenants if c['type']!='核心盟约']})
    result=Coach().run(d,s,cfg,service,'')
    sent=json.loads(Handler.requests[0]['messages'][1]['content'])
    assert sent['ban_constraints']['core_banned']==['乌萨斯']
    assert sent['ban_constraints']['additional_banned']==['坚守']
    assert any(o['op_id']=='OP001' for o in sent['ban_constraints']['banned_operators'])
    assert all(t['name']!='乌萨斯' for t in sent['target_candidates'])
    assert not result['actions'][0]['valid']
