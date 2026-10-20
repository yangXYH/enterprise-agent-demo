"""User-owned, durable conversations with turn references and evidence snapshots."""
import json
import uuid
from contextlib import contextmanager
from utils.operating_analysis_service import connect as data_connect, validate_range

@contextmanager
def connect():
    with data_connect() as c:
        yield c

def owned(c,owner,session_id):
    row=c.execute('SELECT * FROM jy_operating_chat_session WHERE id=? AND owner=?',(session_id,str(owner))).fetchone()
    if not row:raise LookupError('会话不存在或无权访问')
    return dict(row)

def validate_filters(filters):
    if not isinstance(filters,dict):raise ValueError('上下文条件格式错误')
    allowed={'start','end','brand','category','keyword','metric','group'}
    result={k:str(v) for k,v in filters.items() if k in allowed and v is not None}
    if result.get('start') or result.get('end'):validate_range(result.get('start',''),result.get('end',''))
    if any(len(v)>250 for v in result.values()):raise ValueError('上下文条件过长')
    return result

def create(owner,filters=None):
    identifier=uuid.uuid4().hex
    with connect() as c:
        c.execute('INSERT INTO jy_operating_chat_session(id,owner,title,filters) VALUES(?,?,?,?)',
                  (identifier,str(owner),'新对话',json.dumps(validate_filters(filters or {}),ensure_ascii=False)))
    return read(owner,identifier)

def listing(owner,query=''):
    with connect() as c:
        return [dict(r) for r in c.execute('''SELECT s.id,s.title,s.created_at,s.updated_at,
          (SELECT COUNT(*) FROM jy_operating_chat_turn t WHERE t.session_id=s.id) turn_count
          FROM jy_operating_chat_session s WHERE owner=? AND (instr(title,?)>0 OR EXISTS(
          SELECT 1 FROM jy_operating_chat_turn t WHERE t.session_id=s.id AND
          (instr(t.question,?)>0 OR instr(COALESCE(t.response,''),?)>0)))
          ORDER BY updated_at DESC,id DESC LIMIT 200''',(str(owner),query,query,query))]

def unpack(row):
    r=dict(row)
    for k in ('response','context_refs','filters'):
        r[k]=json.loads(r[k]) if r[k] else None
    return r

def read(owner,identifier):
    with connect() as c:
        s=owned(c,owner,identifier)
        s['filters']=json.loads(s['filters'])
        s['turns']=[unpack(r) for r in c.execute('SELECT * FROM jy_operating_chat_turn WHERE session_id=? ORDER BY ordinal',(identifier,))]
        return s

def rename(owner,identifier,title):
    with connect() as c:
        owned(c,owner,identifier)
        c.execute('UPDATE jy_operating_chat_session SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(title,identifier))

def select_context(turns,question,context_ids):
    completed=[t for t in turns if t['status']=='completed']
    available={t['id']:t for t in completed}
    if any(i not in available for i in context_ids):raise ValueError('引用的上下文不属于此会话，或该轮尚未完成')
    selected={t['id']:t for t in completed[-3:]}
    selected.update({i:available[i] for i in context_ids})
    tokens=lambda s:{s[i:i+2].casefold() for i in range(max(0,len(s)-1))}
    q=tokens(question)
    scored=sorted(completed,key=lambda t:(len(q & tokens(t['question']+' '+(t['response'] or {}).get('answer',''))),t['ordinal']),reverse=True)
    for t in scored:
        if len(selected)>=8:break
        if len(q & tokens(t['question']+' '+(t['response'] or {}).get('answer',''))):selected[t['id']]=t
    return sorted(selected.values(),key=lambda t:t['ordinal'])

def reserve(owner,identifier,question,request_id,filters=None,context_ids=None):
    with connect() as c:
        # Serialize reservations per conversation. MySQL uses the row lock;
        # the compatibility adapter removes FOR UPDATE in SQLite-only tests.
        c.execute('SELECT id FROM jy_operating_chat_session WHERE id=? AND owner=? FOR UPDATE',(identifier,str(owner)))
        s=owned(c,owner,identifier)
        duplicate=c.execute('SELECT * FROM jy_operating_chat_turn WHERE session_id=? AND request_id=?',(identifier,request_id)).fetchone()
        if duplicate:return unpack(duplicate),False
        turns=[unpack(r) for r in c.execute('SELECT * FROM jy_operating_chat_turn WHERE session_id=? ORDER BY ordinal',(identifier,))]
        if any(t['status']=='pending' for t in turns):raise RuntimeError('该会话正在回答，请等待完成后再提问')
        chosen=select_context(turns,question,context_ids or [])
        resolved={}  # Only completed answers provide conversational context.
        completed=[t for t in turns if t['status']=='completed']
        if completed:
            evidence=(completed[-1]['response'] or {}).get('evidence')
            if evidence:resolved.update(evidence['filters'])
        if filters is not None:resolved.update(validate_filters(filters))
        ordinal=len(turns)+1
        turn_id=uuid.uuid4().hex
        refs=[{'id':t['id'],'ordinal':t['ordinal'],'question':t['question'],
               'explicit':t['id'] in (context_ids or []),
               'filters':((t['response'] or {}).get('evidence') or {}).get('filters',t['filters'])} for t in chosen]
        c.execute('INSERT INTO jy_operating_chat_turn(id,session_id,ordinal,request_id,question,status,context_refs,filters) VALUES(?,?,?,?,?,?,?,?)',
                  (turn_id,identifier,ordinal,request_id,question,'pending',json.dumps(refs,ensure_ascii=False),json.dumps(resolved,ensure_ascii=False)))
        title=question[:42] if s['title']=='新对话' else s['title']
        c.execute('UPDATE jy_operating_chat_session SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(title,identifier))
        row=unpack(c.execute('SELECT * FROM jy_operating_chat_turn WHERE id=?',(turn_id,)).fetchone())
        return row,True

def generation_context(owner,session_id,turn_id):
    s=read(owner,session_id)
    turn=next(t for t in s['turns'] if t['id']==turn_id)
    refs={r['id']:r for r in turn['context_refs']}
    history=[]
    for t in s['turns']:
        if t['id'] not in refs:continue
        response=t['response'] or {}
        e=response.get('evidence') or {}
        report=response.get('report') or {}
        query_results=((response.get('evidence') or {}).get('query_results') or [])[:6]
        history.extend([
            {'role':'user','content':t['question'],'ordinal':t['ordinal'],'turn_id':t['id'],'explicit_reference':refs[t['id']].get('explicit',False)},
            {'role':'assistant','content':response.get('answer','')[:2200],'ordinal':t['ordinal'],'turn_id':t['id'],
             'data_context':{'understood_as':report.get('understood_as'),'filters':e.get('filters',t['filters']),
               'queries':[{'id':q.get('id'),'title':q.get('title'),'spec':q.get('spec'),'value':q.get('value'),
                           'top_products':q.get('rows',[])[:3]} for q in query_results],
               'top_products':e.get('ranking',[])[:5]}}])
    return turn,history

def update_stage(owner,session_id,turn_id,stage,partial_answer=None):
    with connect() as c:
        owned(c,owner,session_id)
        if partial_answer is None:
            c.execute('UPDATE jy_operating_chat_turn SET stage=? WHERE id=? AND session_id=? AND status=?',
                      (str(stage)[:120],turn_id,session_id,'pending'))
        else:
            c.execute('UPDATE jy_operating_chat_turn SET stage=?,partial_answer=? WHERE id=? AND session_id=? AND status=?',
                      (str(stage)[:120],str(partial_answer)[:12000],turn_id,session_id,'pending'))

def progress(owner,session_id,turn_id):
    with connect() as c:
        owned(c,owner,session_id)
        row=c.execute('SELECT id,status,stage,partial_answer,error FROM jy_operating_chat_turn WHERE id=? AND session_id=?',
                      (turn_id,session_id)).fetchone()
        if not row:raise LookupError('问答记录不存在')
        return dict(row)

def finish(owner,session_id,turn_id,response=None,error=None):
    with connect() as c:
        owned(c,owner,session_id)
        updated=c.execute('UPDATE jy_operating_chat_turn SET status=?,response=?,error=?,stage=?,completed_at=CURRENT_TIMESTAMP WHERE id=? AND session_id=? AND status=?',
                  ('error' if error else 'completed',json.dumps(response,ensure_ascii=False) if response else None,error,
                   '生成失败' if error else '回答已完成',turn_id,session_id,'pending'))
        if not updated.rowcount:return
        if response and response.get('evidence'):
            c.execute('UPDATE jy_operating_chat_session SET filters=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',
                      (json.dumps(response['evidence']['filters'],ensure_ascii=False),session_id))
        else:c.execute('UPDATE jy_operating_chat_session SET updated_at=CURRENT_TIMESTAMP WHERE id=?',(session_id,))

def recover_pending():
    # Single-host backend startup: unfinished work from a stopped process cannot resume.
    with connect() as c:
        if c.dialect=='mysql':c.execute('SET innodb_lock_wait_timeout=2')
        c.execute("UPDATE jy_operating_chat_turn SET status='error',stage='生成中断',error='服务已重启，本轮未完成，可重新发送',completed_at=CURRENT_TIMESTAMP WHERE status='pending'")
