from importlib import import_module
from pathlib import Path
from copy import deepcopy
import json, time, base64
from app.config import ROOT, MODULES, MAX_BYTES
from app.errors import BusinessError
from app.manifest import digest, make_manifest

def resolve_split(payload, snapshot, dataset):
    if snapshot is not None:
        encoded=snapshot.get('split_bytes_b64')
        return base64.b64decode(encoded,validate=True) if encoded else None
    if 'split_csv_text' in payload: return str(payload['split_csv_text']).encode()
    if 'csv_text' in payload: return None
    path=ROOT/'sample_data'/f'{dataset}.split.csv'
    return path.read_bytes() if path.exists() else None

def evaluate(payload=None, until=None, snapshot=None):
    payload=payload or {}
    dataset=payload.get('dataset','dirty')
    if dataset not in {'dirty','clean','legacy'}: raise BusinessError('BAD_DATASET','样例名称无效')
    if not isinstance(payload.get('overrides',{}),dict): raise BusinessError('BAD_CONTEXT','参数须为对象')
    raw=(base64.b64decode(snapshot['bytes_b64'],validate=True) if snapshot is not None else (str(payload['csv_text']).encode() if 'csv_text' in payload else (ROOT/'sample_data'/f'{dataset}.csv').read_bytes()))
    if len(raw)>MAX_BYTES: raise BusinessError('TOO_LARGE','文件超过2MB',413)
    split_raw=resolve_split(payload,snapshot,dataset)
    if split_raw is not None and len(split_raw)>MAX_BYTES: raise BusinessError('TOO_LARGE','拼车货包文件超过2MB',413)
    context=deepcopy(snapshot['context']) if snapshot is not None else json.loads((ROOT/'sample_data/context.json').read_text())
    context.update(deepcopy(payload.get('overrides',{})))
    start=time.perf_counter()
    state={'raw_bytes':raw,'split_raw':split_raw,'context':context,'records':[],'quarantine':[], 'counts':{},'views':{},'source':dataset}
    for index,key in enumerate(MODULES,1):
        if index>(until or len(MODULES)): break
        import_module(f'app.modules.{key}.rules').apply(state)
    state['input_snapshot']={'bytes_b64':base64.b64encode(raw).decode(),'split_bytes_b64':base64.b64encode(split_raw).decode() if split_raw is not None else None,'context':deepcopy(context)}
    state.pop('raw_bytes',None);state.pop('split_raw',None)
    state['manifest']=make_manifest(digest(raw,context,split_raw or b''),dataset,time.perf_counter()-start)
    return state
