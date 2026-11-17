from fastapi import APIRouter, Request, Body
from datetime import datetime, timezone
import hashlib, json
from app.engine import evaluate
from app.web import render
from app.errors import BusinessError, require
from app import store
from app.modules.split.rules import build_publication, diff_publications
router=APIRouter()

@router.get('/split')
def page(request:Request):
    from app.main import DB_PATH
    return render(request,'split',{'publications':store.publications(DB_PATH)})

@router.post('/api/split')
def calculate(payload:dict=Body(default={})):
    return evaluate(payload,until=8)

@router.post('/api/split/{ticket}/publish')
def publish(ticket:str,payload:dict=Body(...)):
    from app.main import DB_PATH
    run_id=payload.get('run_id')
    require(isinstance(run_id,str) and bool(run_id),'BAD_RUN','缺少 run_id')
    base=payload.get('base_version')
    require(base is None or (isinstance(base,int) and base>=0),'BAD_REVISION','发布基线须为非负整数')
    result=store.get(DB_PATH,run_id)
    content=build_publication(result,ticket)
    seal=hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    latest=store.latest_publication(DB_PATH,ticket)
    if latest and latest['seal']==seal:
        return {**latest['payload'],'idempotent':True}
    current=latest['version'] if latest else 0
    if base is not None and base!=current:
        raise BusinessError('STALE_VERSION','发布基线已变化，请刷新',409)
    record={**content,'ticket':ticket,'version':current+1,'supersedes':current,
        'impact':diff_publications(latest['payload'] if latest else None,content),
        'seal':seal,'published_at':datetime.now(timezone.utc).isoformat()}
    return store.save_publication(DB_PATH,record)

@router.get('/api/split/publications')
def list_publications(ticket:str=''):
    from app.main import DB_PATH
    return store.publications(DB_PATH,ticket or None)
