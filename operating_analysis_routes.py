from pathlib import Path
import tempfile
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from utils import operating_analysis_service as service, operating_analysis_ai

router=APIRouter(prefix='/api/operating-analysis',tags=['经营数据分析'])

def authorize(request,write=False,page='operating-analysis'):
    from main import _get_authenticated_user, _get_mysql_engine, _is_admin_user
    from utils.permission_service import allowed_page_keys
    user=_get_authenticated_user(request)
    if not _is_admin_user(user) and page not in allowed_page_keys(_get_mysql_engine(),user['role'],str(user.get('real_name') or '')):
        raise HTTPException(403,'无该经营页面访问权限')
    if write and not _is_admin_user(user) and user['role'] not in ('operator','boss'):
        raise HTTPException(403,'仅管理员、运营或总经理角色可导入数据')
    return user

@router.get('/metadata')
async def metadata(request:Request):
    await run_in_threadpool(authorize,request)
    return await run_in_threadpool(service.metadata)

@router.get('/insights')
async def insights(request:Request,start:str,end:str,brand:str='',category:str=''):
    await run_in_threadpool(authorize,request)
    try:return await run_in_threadpool(service.executive_insights,start,end,brand,category)
    except ValueError as e:raise HTTPException(422,str(e))

@router.get('')
async def dashboard(request:Request,start:str,end:str,keyword:str='',category:str='',brand:str='',page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=200),metric:str='revenue',group:str='sku'):
    await run_in_threadpool(authorize,request)
    try:return await run_in_threadpool(service.dashboard,start,end,keyword,category,page,page_size,metric,group,brand)
    except ValueError as e:raise HTTPException(422,str(e))

@router.post('/import')
async def upload(request:Request,file:UploadFile=File(...)):
    await run_in_threadpool(authorize,request,True)
    if not (file.filename or '').lower().endswith('.xlsx'):raise HTTPException(422,'仅支持 .xlsx')
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'report.xlsx'
        total=0
        with path.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                total+=len(chunk)
                if total>40*1024*1024:raise HTTPException(413,'报表不能超过40MB')
                out.write(chunk)
        try:return await run_in_threadpool(service.import_excel,path,file.filename)
        except (ValueError,KeyError) as e:raise HTTPException(422,str(e))

@router.get('/model-mapping/template')
async def download_model_mapping_template(request:Request):
    await run_in_threadpool(authorize,request)
    try:
        content = await run_in_threadpool(service.build_model_mapping_template)
    except (ValueError,KeyError) as e:
        raise HTTPException(422,str(e))
    filename = quote('型号货号匹配模板.xlsx')
    return StreamingResponse(
        iter([content]),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"},
    )

@router.post('/model-mapping/import')
async def import_model_mapping(request:Request,file:UploadFile=File(...)):
    await run_in_threadpool(authorize,request,True)
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(422,'仅支持 .xlsx')
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'model-mapping.xlsx'
        total = 0
        with path.open('wb') as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 10 * 1024 * 1024:
                    raise HTTPException(413,'型号匹配模板不能超过10MB')
                out.write(chunk)
        try:
            return await run_in_threadpool(service.import_model_mapping,path)
        except (ValueError,KeyError) as e:
            raise HTTPException(422,str(e))

class Chat(BaseModel):
    question:str=Field(min_length=1,max_length=2000)
    filters:dict=Field(default_factory=dict)
    history:list[dict]=Field(default_factory=list,max_length=6)

@router.post('/chat')
async def chat(request:Request,body:Chat):
    await run_in_threadpool(authorize,request)
    try:return await operating_analysis_ai.analyze(body.question,body.filters,body.history)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))
    except Exception:raise HTTPException(502,'AI 服务暂时不可用，请稍后重试；看板数据仍可查询')
