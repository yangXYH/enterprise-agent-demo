import logging
from sqlalchemy.exc import OperationalError
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from operating_analysis_routes import authorize
from utils import operating_analysis_service as data_service, operating_analysis_ai, operating_chat_service as store
from utils import operating_knowledge_service as knowledge_store

router=APIRouter(prefix='/api/operating-chat',tags=['AI 经营问答'])
LOGGER=logging.getLogger(__name__)

async def user(request):
    return await run_in_threadpool(authorize,request,False,'operating-chat')

@router.on_event('startup')
async def recover():
    try:
        await run_in_threadpool(store.recover_pending)
    except OperationalError as error:
        code=getattr(getattr(error,'orig',None),'args',(None,))[0]
        if code not in (1205,1213):raise
        LOGGER.warning('经营问答未完成状态暂未恢复，数据库正在释放迁移锁；服务继续启动')

@router.on_event('shutdown')
async def close_ai_client():
    await operating_analysis_ai.close_client()

def missing(e):raise HTTPException(404,str(e))

@router.get('/metadata')
async def metadata(request:Request):
    await user(request)
    return await run_in_threadpool(data_service.metadata)

@router.get('/knowledge/status')
async def knowledge_status(request:Request):
    await user(request)
    return await run_in_threadpool(knowledge_store.status)

@router.get('/knowledge/chunks/{identifier}',response_class=PlainTextResponse)
async def knowledge_chunk(request:Request,identifier:str):
    await user(request)
    try:chunk=await run_in_threadpool(knowledge_store.read_chunk,identifier)
    except LookupError as e:missing(e)
    return f"{chunk['title']}\n{chunk['heading']} · {chunk['location']}\n\n{chunk['text']}"

@router.get('/sessions')
async def listing(request:Request,q:str=Query('',max_length=200)):
    u=await user(request)
    return {'items':await run_in_threadpool(store.listing,u['id'],q)}

class Create(BaseModel):
    filters:dict=Field(default_factory=dict)

@router.post('/sessions')
async def create(request:Request,body:Create):
    u=await user(request)
    try:return await run_in_threadpool(store.create,u['id'],body.filters)
    except ValueError as e:raise HTTPException(422,str(e))

@router.get('/sessions/{identifier}')
async def read(request:Request,identifier:str):
    u=await user(request)
    try:return await run_in_threadpool(store.read,u['id'],identifier)
    except LookupError as e:missing(e)

@router.get('/sessions/{identifier}/turns/{turn_id}/progress')
async def progress(request:Request,identifier:str,turn_id:str):
    u=await user(request)
    try:return await run_in_threadpool(store.progress,u['id'],identifier,turn_id)
    except LookupError as e:missing(e)

class Rename(BaseModel):
    title:str=Field(min_length=1,max_length=120)

@router.patch('/sessions/{identifier}')
async def rename(request:Request,identifier:str,body:Rename):
    u=await user(request)
    try:await run_in_threadpool(store.rename,u['id'],identifier,body.title.strip() or '未命名对话')
    except LookupError as e:missing(e)
    return {'ok':True}

class Turn(BaseModel):
    question:str=Field(min_length=1,max_length=2000)
    request_id:str=Field(min_length=8,max_length=80)
    filters:dict|None=None
    context_ids:list[str]=Field(default_factory=list,max_length=5)

async def generate(owner,session_id,turn_id):
    try:
        turn,history=await run_in_threadpool(store.generation_context,owner,session_id,turn_id)
        filters=turn['filters']
        async def progress(stage,partial_answer=None):
            await run_in_threadpool(store.update_stage,owner,session_id,turn_id,stage,partial_answer)
        result=await operating_analysis_ai.analyze(turn['question'],filters,history,progress)
        await run_in_threadpool(store.finish,owner,session_id,turn_id,result)
    except Exception as e:
        detail=str(e)
        error=detail if isinstance(e,ValueError) and 'validation error' not in detail.casefold() else 'AI 服务暂时不可用，可重新发送；历史对话已保存'
        LOGGER.warning('Operating chat generation failed: %s',type(e).__name__)
        await run_in_threadpool(store.finish,owner,session_id,turn_id,None,error)

@router.post('/sessions/{identifier}/turns',status_code=202)
async def send(request:Request,identifier:str,body:Turn,tasks:BackgroundTasks):
    u=await user(request)
    if not body.question.strip():raise HTTPException(422,'请输入问题')
    try:
        turn,created=await run_in_threadpool(store.reserve,u['id'],identifier,body.question.strip(),body.request_id,body.filters,body.context_ids)
    except LookupError as e:missing(e)
    except ValueError as e:raise HTTPException(422,str(e))
    except RuntimeError as e:raise HTTPException(409,str(e))
    if created:tasks.add_task(generate,u['id'],identifier,turn['id'])
    return turn
