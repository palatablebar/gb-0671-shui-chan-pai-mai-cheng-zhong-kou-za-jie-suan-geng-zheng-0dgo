import sqlite3, json
from pathlib import Path
from app.errors import BusinessError

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(path,timeout=15)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL, result TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT '待复核')")
    con.execute("CREATE TABLE IF NOT EXISTS publications (ticket TEXT NOT NULL, version INTEGER NOT NULL, run_id TEXT NOT NULL, seal TEXT NOT NULL, payload TEXT NOT NULL, published_at TEXT NOT NULL, PRIMARY KEY (ticket,version))")
    return con

def save(path, result):
    run_id=result['manifest']['run_id']
    with connect(path) as con:
        con.execute('INSERT OR IGNORE INTO runs(id,digest,result) VALUES(?,?,?)', (run_id,result['manifest']['sha256'],json.dumps(result,ensure_ascii=False)))
    return get(path,run_id)

def get(path, run_id):
    with connect(path) as con: row=con.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if not row: raise BusinessError('NOT_FOUND','批次不存在',404)
    result=json.loads(row['result']);result.update(revision=row['revision'],status=row['status'])
    return result

def history(path):
    with connect(path) as con:
        return [dict(r) for r in con.execute('SELECT id,revision,status FROM runs ORDER BY rowid DESC LIMIT 100')]

def review(path,run_id,revision):
    with connect(path) as con:
        cur=con.execute('UPDATE runs SET revision=revision+1,status=? WHERE id=? AND revision=?',('已复核',run_id,revision))
        if cur.rowcount!=1:
            if not con.execute('SELECT 1 FROM runs WHERE id=?',(run_id,)).fetchone():
                raise BusinessError('NOT_FOUND','批次不存在',404)
            raise BusinessError('STALE_VERSION','复核版本已更新，请刷新',409)
    return get(path,run_id)

def save_publication(path, record):
    with connect(path) as con:
        try:
            con.execute('INSERT INTO publications(ticket,version,run_id,seal,payload,published_at) VALUES(?,?,?,?,?,?)',
                (record['ticket'],record['version'],record['run_id'],record['seal'],json.dumps(record,ensure_ascii=False),record['published_at']))
        except sqlite3.IntegrityError:
            raise BusinessError('STALE_VERSION','发布版本冲突，请刷新',409)
    return record

def latest_publication(path, ticket):
    with connect(path) as con:
        row=con.execute('SELECT * FROM publications WHERE ticket=? ORDER BY version DESC LIMIT 1',(ticket,)).fetchone()
    return dict(row,payload=json.loads(row['payload'])) if row else None

def publications(path, ticket=None):
    with connect(path) as con:
        if ticket: rows=con.execute('SELECT * FROM publications WHERE ticket=? ORDER BY version',(ticket,)).fetchall()
        else: rows=con.execute('SELECT * FROM publications ORDER BY ticket,version').fetchall()
    return [dict(r,payload=json.loads(r['payload'])) for r in rows]
