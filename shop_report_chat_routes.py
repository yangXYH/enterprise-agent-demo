import logging
from sqlalchemy.exc import OperationalError
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from utils import shop_report_service as data_service, shop_report_ai, shop_report_chat_service as store

router = APIRouter(prefix='/api/shop-report-chat', tags=['店铺报表 AI 问答'])
LOGGER = logging.getLogger(__name__)
# AI 问答不设独立页面权限：访问权限跟随「店铺报表」(shop-report)，单一控制点。
PAGE_KEY = 'shop-report'


def authorize(request: Request):
    from main import _get_authenticated_user, _get_mysql_engine, _is_admin_user
    from utils.permission_service import allowed_page_keys, legacy_name_if_unique
    user = _get_authenticated_user(request)
    if _is_admin_user(user):
        return user
    engine = _get_mysql_engine()
    allowed = allowed_page_keys(
        engine,
        str(user.get('role') or ''),
        legacy_name_if_unique(engine, str(user.get('real_name') or '')),
        'account:' + str(user.get('username') or ''),
    )
    if PAGE_KEY not in allowed:
        raise HTTPException(403, '无店铺报表问答访问权限')
    return user


@router.on_event('startup')
async def recover():
    try:
        await run_in_threadpool(store.recover_pending)
    except OperationalError as error:
        code = getattr(getattr(error, 'orig', None), 'args', (None,))[0]
        if code not in (1205, 1213):
            raise
        LOGGER.warning('店铺报表问答未完成状态暂未恢复，数据库正在释放迁移锁；服务继续启动')


@router.on_event('shutdown')
async def close_ai_client():
    from utils import operating_analysis_ai
    await operating_analysis_ai.close_client()


def missing(e):
    raise HTTPException(404, str(e))


@router.get('/metadata')
async def metadata(request: Request):
    await run_in_threadpool(authorize, request)
    return await run_in_threadpool(data_service.metadata)


@router.get('/sessions')
async def listing(request: Request, q: str = Query('', max_length=200)):
    u = await run_in_threadpool(authorize, request)
    return {'items': await run_in_threadpool(store.listing, u['id'], q)}


class Create(BaseModel):
    filters: dict = Field(default_factory=dict)


@router.post('/sessions')
async def create(request: Request, body: Create):
    u = await run_in_threadpool(authorize, request)
    try:
        return await run_in_threadpool(store.create, u['id'], body.filters)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get('/sessions/{identifier}')
async def read(request: Request, identifier: str):
    u = await run_in_threadpool(authorize, request)
    try:
        return await run_in_threadpool(store.read, u['id'], identifier)
    except LookupError as e:
        missing(e)


@router.get('/sessions/{identifier}/turns/{turn_id}/progress')
async def progress(request: Request, identifier: str, turn_id: str):
    u = await run_in_threadpool(authorize, request)
    try:
        return await run_in_threadpool(store.progress, u['id'], identifier, turn_id)
    except LookupError as e:
        missing(e)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


@router.patch('/sessions/{identifier}')
async def rename(request: Request, identifier: str, body: Rename):
    u = await run_in_threadpool(authorize, request)
    try:
        await run_in_threadpool(store.rename, u['id'], identifier, body.title.strip() or '未命名对话')
    except LookupError as e:
        missing(e)
    return {'ok': True}


class Turn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=8, max_length=80)
    filters: dict | None = None
    context_ids: list[str] = Field(default_factory=list, max_length=5)


async def generate(owner, session_id, turn_id):
    try:
        turn, history = await run_in_threadpool(store.generation_context, owner, session_id, turn_id)
        filters = turn['filters']

        async def progress(stage, partial_answer=None):
            await run_in_threadpool(store.update_stage, owner, session_id, turn_id, stage, partial_answer)

        result = await shop_report_ai.analyze(turn['question'], filters, history, progress)
        await run_in_threadpool(store.finish, owner, session_id, turn_id, result)
    except Exception as e:
        detail = str(e)
        error = detail if isinstance(e, ValueError) and 'validation error' not in detail.casefold() else 'AI 服务暂时不可用，可重新发送；历史对话已保存'
        LOGGER.warning('Shop-report chat generation failed: %s', type(e).__name__)
        await run_in_threadpool(store.finish, owner, session_id, turn_id, None, error)


@router.post('/sessions/{identifier}/turns', status_code=202)
async def send(request: Request, identifier: str, body: Turn, tasks: BackgroundTasks):
    u = await run_in_threadpool(authorize, request)
    if not body.question.strip():
        raise HTTPException(422, '请输入问题')
    try:
        turn, created = await run_in_threadpool(store.reserve, u['id'], identifier, body.question.strip(), body.request_id, body.filters, body.context_ids)
    except LookupError as e:
        missing(e)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    if created:
        tasks.add_task(generate, u['id'], identifier, turn['id'])
    return turn
