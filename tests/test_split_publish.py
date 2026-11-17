from fastapi.testclient import TestClient
from app import main
import json, zipfile, io

def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',str(tmp_path/'test.sqlite'))
    return TestClient(main.app)

def run_id(c,**payload):
    return c.post('/api/runs',json=payload).json()['manifest']['run_id']

def test_publish_idempotent_no_new_results(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);rid=run_id(c)
    first=c.post('/api/split/00016/publish',json={'run_id':rid})
    assert first.status_code==200 and first.json()['version']==1
    again=c.post('/api/split/00016/publish',json={'run_id':rid})
    assert again.json()['version']==1 and again.json()['idempotent'] is True
    assert len(c.get('/api/split/publications?ticket=00016').json())==1

def test_rerun_adds_no_household_results(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch)
    a=c.post('/api/runs',json={}).json();b=c.post('/api/runs/'+a['manifest']['run_id']+'/rerun',json={}).json()
    assert a['manifest']['run_id']==b['manifest']['run_id']
    assert a['split']['summary']==b['split']['summary']
    assert len(c.get('/api/runs').json())==1

def test_publish_blocked_keeps_old_version(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);rid=run_id(c)
    assert c.post('/api/split/00016/publish',json={'run_id':rid}).status_code==200
    blocked=c.post('/api/split/00018/publish',json={'run_id':rid})
    assert blocked.status_code==422 and blocked.json()['code']=='SPLIT_BLOCKED'
    unknown=c.post('/api/split/00999/publish',json={'run_id':rid})
    assert unknown.status_code==422
    kept=c.get('/api/split/publications?ticket=00016').json()
    assert [p['version'] for p in kept]==[1]

def test_publish_stale_base_conflict(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);rid=run_id(c)
    c.post('/api/split/00016/publish',json={'run_id':rid})
    changed=open('sample_data/dirty.split.csv').read().replace('P1604,00016,李河,1,5.0','P1604,00016,李河,2,15.0')
    rid2=run_id(c,split_csv_text=changed)
    assert rid2!=rid
    stale=c.post('/api/split/00016/publish',json={'run_id':rid2,'base_version':0})
    assert stale.status_code==409
    assert [p['version'] for p in c.get('/api/split/publications?ticket=00016').json()]==[1]
    ok=c.post('/api/split/00016/publish',json={'run_id':rid2,'base_version':1})
    assert ok.status_code==200 and ok.json()['version']==2

def test_publish_impact_traceable(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);rid=run_id(c)
    c.post('/api/split/00016/publish',json={'run_id':rid})
    changed=open('sample_data/dirty.split.csv').read().replace('P1604,00016,李河,1,5.0','P1604,00016,李河,2,15.0')
    rid2=run_id(c,split_csv_text=changed)
    v2=c.post('/api/split/00016/publish',json={'run_id':rid2}).json()
    assert v2['supersedes']==1
    deltas={h['household']:h['delta'] for h in v2['impact']['households']}
    assert deltas=={'张海':'-73.05','李河':'+73.05'}
    pubs=c.get('/api/split/publications?ticket=00016').json()
    assert [p['version'] for p in pubs]==[1,2]
    assert pubs[0]['payload']['households'][0]['final']=='807.25'

def test_split_csv_changes_run_digest(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch)
    base=run_id(c)
    other=run_id(c,split_csv_text=open('sample_data/dirty.split.csv').read().replace('40.0','40.5',1))
    assert base!=other

def test_custom_main_csv_without_split_has_empty_view(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch)
    result=c.post('/api/runs',json={'csv_text':open('sample_data/clean.csv').read()}).json()
    assert result['split']['tickets']==[] and result['views']['split']['rows']==[]

def test_split_page_and_publish_button(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);rid=run_id(c)
    html=c.get('/split?run_id='+rid).text
    assert '拼车票 00016' in html and 'data-publish="00016"' in html and '807.25' in html
    assert 'MISSING_EST' in html and 'ATTRIBUTION_CONFLICT' in html and 'UNKNOWN_TICKET' in html
    c.post('/api/split/00016/publish',json={'run_id':rid})
    assert 'v1' in c.get('/split?run_id='+rid).text

def test_export_contains_split_evidence(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch);rid=run_id(c)
    z=zipfile.ZipFile(io.BytesIO(c.get('/api/export/'+rid).content))
    data=json.loads(z.read('evidence.json'))
    assert 'split' in data['views'] and len(data['views']['split']['rows'])==5

def test_split_snapshot_kept_for_rerun(tmp_path,monkeypatch):
    c=client(tmp_path,monkeypatch)
    result=c.post('/api/runs',json={}).json()
    assert result['input_snapshot']['split_bytes_b64']
    rid=result['manifest']['run_id']
    repeated=c.post('/api/runs/'+rid+'/rerun',json={}).json()
    assert repeated['manifest']['run_id']==rid
    assert repeated['split']['summary']['households']==8
