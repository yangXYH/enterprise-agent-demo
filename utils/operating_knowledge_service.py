"""Versioned document chunks, BM25/character recall fusion, and auditable citations.

Architecture references are documented in 经营数据分析说明.md; no upstream code is copied.
Only operating/product libraries are eligible. Company documents are evidence, never instructions.
"""
import hashlib
import json
import logging
import math
import os
import re
import threading
import time
from collections import Counter
from pathlib import Path
import jieba
from rank_bm25 import BM25Okapi
from utils import operating_analysis_service as data

ROOT=Path(__file__).resolve().parents[1]
LOCK=threading.RLock()
_cache={}
jieba.setLogLevel(logging.WARNING)
SUPPORTED={'.md','.txt','.csv','.docx','.pdf','.xlsx','.xls'}
ALIASES={'销售额':'成交金额','成交额':'成交金额','gmv':'成交金额','销量':'成交商品件数',
         '流量':'商品访客','浏览':'浏览量','加购率':'加购客户访客比','客单':'客户均成交金额',
         '环比':'上月同期','同比':'去年同期','卖得':'销量 成交金额','下滑':'下降 增长贡献'}

def roots():
    builtin=Path(os.getenv('OPERATING_KNOWLEDGE_DIR',str(ROOT/'knowledge'/'operating')))
    uploaded=Path(os.getenv('KNOWLEDGE_ROOT',str(ROOT/'uploads'/'knowledge')))
    return [('reference',builtin),('operation',uploaded/'operation'),('product',uploaded/'product')]

def schema(c):
    # Tables and additive upgrades are owned by utils.operating_db so the same
    # schema is used by MySQL in production and SQLite in isolated tests.
    return None

def extract(path):
    suffix=path.suffix.lower()
    if suffix in {'.md','.txt','.csv'}:
        raw=path.read_bytes()
        for encoding in ('utf-8-sig','gb18030'):
            try:return [('',raw.decode(encoding))]
            except UnicodeDecodeError:pass
        return []
    if suffix=='.pdf':
        from pypdf import PdfReader
        return [(f'第 {i+1} 页',p.extract_text() or '') for i,p in enumerate(PdfReader(str(path)).pages)]
    if suffix=='.docx':
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        from docx.oxml.ns import qn
        doc=Document(path);lines=[]
        for node in doc.element.body.iterchildren():
            if node.tag==qn('w:p'):
                p=Paragraph(node,doc);lines.append(('## ' if p.style and p.style.name.startswith('Heading') else '')+p.text)
            elif node.tag==qn('w:tbl'):
                lines.extend(' | '.join(cell.text for cell in row.cells) for row in Table(node,doc).rows)
        return [('', '\n'.join(lines))]
    # Reuse the existing knowledge library's spreadsheet text parser, never aggregate sampled rows.
    from utils.ecom_knowledge_service import _qa_extract_text
    return [('',_qa_extract_text(path))]

def chunk(text,location=''):
    heading='正文';buf=[];first=1;size=0
    for line_no,line in enumerate(text.splitlines(),1):
        h=re.match(r'^#{1,6}\s+(.+)',line)
        if (h or size+len(line)>950) and buf:
            yield heading,f'{location} 行 {first}–{line_no-1}'.strip(),'\n'.join(buf)
            buf=[];size=0
        if h:heading=h[1]
        if not buf:first=line_no
        # Long paragraphs retain all content across bounded chunks rather than truncate it.
        while len(line)>950:
            yield heading,f'{location} 行 {line_no}'.strip(),line[:950]
            line=line[950:]
        buf.append(line);size+=len(line)+1
    if buf and ''.join(buf).strip():yield heading,f'{location} 行 {first}–{line_no}'.strip(),'\n'.join(buf)

def sync(force=False):
    key=str(os.getenv('DB_URL') or os.getenv('DATABASE_URL') or os.getenv('DB_NAME','enterprise_agent_db'))+repr(roots())
    with LOCK:
        if not force and _cache.get(key,{}).get('expires',0)>time.monotonic():return _cache[key]
        current={};errors=[]
        with data.connect() as c:
            schema(c)
            saved={r['id']:dict(r) for r in c.execute('SELECT * FROM jy_operating_knowledge_document')}
            for library,root in roots():
                if not root.exists():continue
                base=root.resolve()
                for p in sorted(root.rglob('*')):
                    if not p.is_file() or p.suffix.lower() not in SUPPORTED:continue
                    absolute=p.resolve()
                    if not absolute.is_relative_to(base):continue
                    relative=p.relative_to(root).as_posix()
                    doc_id=hashlib.sha256(f'{library}:{relative}'.encode()).hexdigest()[:24]
                    current[doc_id]=True
                    try:
                        stat=p.stat()
                        if stat.st_size>10*1024*1024:raise ValueError('文档超过10MB解析上限')
                        if doc_id in saved and saved[doc_id].get('modified_ns')==stat.st_mtime_ns and saved[doc_id].get('size')==stat.st_size:
                            if saved[doc_id]['error']:errors.append({'title':p.name,'error':saved[doc_id]['error']})
                            continue
                        digest=hashlib.sha256(p.read_bytes()).hexdigest()
                        if doc_id in saved and saved[doc_id]['digest']==digest:
                            if saved[doc_id]['error']:errors.append({'title':p.name,'error':saved[doc_id]['error']})
                            continue
                        sections=list(extract(p));parts=[]
                        for loc,text in sections:parts.extend(chunk(text,loc))
                        if not parts:raise ValueError('未提取到文字；扫描文档需提供可读文本')
                        error='';status='ready'
                    except Exception as e:
                        parts=[];digest='';status='unreadable'
                        error=str(e) if isinstance(e,ValueError) else '文档解析失败'
                        errors.append({'title':p.name,'error':error})
                    c.execute('DELETE FROM jy_operating_knowledge_chunk WHERE document_id=?',(doc_id,))
                    stat=p.stat()
                    c.upsert_many('jy_operating_knowledge_document',[{
                        'id':doc_id,'library':library,'path':relative,'title':p.name,'digest':digest,
                        'status':status,'error':error,'modified_ns':stat.st_mtime_ns,'size':stat.st_size
                    }],('id',))
                    for i,(heading,location,text) in enumerate(parts):
                        cid=hashlib.sha256(f'{doc_id}:{digest}:{i}'.encode()).hexdigest()[:24]
                        c.execute('INSERT INTO jy_operating_knowledge_chunk VALUES(?,?,?,?,?)',(cid,doc_id,heading,location,text))
            for did in saved.keys()-current.keys():
                c.execute('DELETE FROM jy_operating_knowledge_chunk WHERE document_id=?',(did,))
                c.execute('DELETE FROM jy_operating_knowledge_document WHERE id=?',(did,))
            documents=[dict(r) for r in c.execute('SELECT id,library,title,digest,status,error,indexed_at FROM jy_operating_knowledge_document')]
            chunks=[dict(r) for r in c.execute('''SELECT k.*,d.title,d.library,d.digest FROM jy_operating_knowledge_chunk k
              JOIN jy_operating_knowledge_document d ON k.document_id=d.id WHERE d.status='ready' ORDER BY d.id,k.id''')]
        tokenized=[tokens(d['title']+' '+d['heading']+' '+d['text']) or ['_empty_'] for d in chunks]
        result={'documents':documents,'chunks':chunks,'errors':errors,'expires':time.monotonic()+15,
                'bm25':BM25Okapi(tokenized) if tokenized else None,'tokenized':tokenized}
        _cache[key]=result
        return result

def tokens(text):
    text=text.casefold()
    for a,b in ALIASES.items():
        if a in text:text+=' '+b
    return [t.strip() for t in jieba.lcut(text) if len(t.strip())>1 and re.search(r'[\w\u4e00-\u9fff]',t)]

def grams(text):
    s=re.sub(r'\s+','',text.casefold())
    return Counter(s[i:i+2] for i in range(len(s)-1))

def retrieve(question,top_k=12):
    index=sync();chunks=index['chunks']
    if not chunks:return []
    qt=tokens(question);qset=set(qt);qg=grams(question);rankings=[]
    # BM25 scores can be negative for frequent terms in small corpora. Gate on real overlap.
    lexical=[(i,float(s)) for i,s in enumerate(index['bm25'].get_scores(qt)) if qset & set(index['tokenized'][i])]
    rankings.append([i for i,_ in sorted(lexical,key=lambda x:x[1],reverse=True)])
    character=[]
    for i,d in enumerate(chunks):
        g=grams(d['heading']+' '+d['text']);overlap=sum(qg[t]*g.get(t,0) for t in qg)
        if overlap:character.append((i,overlap/math.sqrt(sum(v*v for v in g.values())*max(1,sum(v*v for v in qg.values())))))
    rankings.append([i for i,_ in sorted(character,key=lambda x:x[1],reverse=True)])
    scores={}
    for ranking in rankings:
        for rank,i in enumerate(ranking):scores[i]=scores.get(i,0)+1/(60+rank+1)
    picked=sorted(scores,key=lambda i:(-scores[i],chunks[i]['id']))[:top_k]
    return [{**chunks[i],'score':round(scores[i],6),'citation_id':'K'+chunks[i]['id'][:8],
             'url':'/api/operating-chat/knowledge/chunks/'+chunks[i]['id']} for i in picked]

def status():
    s=sync()
    return {'documents':s['documents'],'chunk_count':len(s['chunks']),'errors':s['errors'],
            'retrieval':'BM25 + 字符相似度融合；模型选择相关片段',
            'libraries':['经营分析方法参考','运营知识库','产品知识库']}

def read_chunk(identifier):
    index=sync()
    found=next((d for d in index['chunks'] if d['id']==identifier),None)
    if not found:raise LookupError('引用片段不存在或文档已更新')
    return found
