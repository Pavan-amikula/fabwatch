import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS entities(
 entity_id TEXT PRIMARY KEY, event_time TEXT NOT NULL, payload_hash TEXT NOT NULL,
 measurements TEXT NOT NULL, missing_fraction REAL NOT NULL CHECK(missing_fraction BETWEEN 0 AND 1));
CREATE TABLE IF NOT EXISTS predictions(
 entity_id TEXT PRIMARY KEY REFERENCES entities(entity_id), risk REAL NOT NULL CHECK(risk BETWEEN 0 AND 1),
 decision TEXT NOT NULL CHECK(decision IN ('screen','review','abstain')), model_hash TEXT NOT NULL, latency_ms REAL NOT NULL);
CREATE TABLE IF NOT EXISTS outcomes(
 entity_id TEXT PRIMARY KEY REFERENCES entities(entity_id), failed INTEGER NOT NULL CHECK(failed IN (0,1)), revealed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS investigations(
 entity_id TEXT PRIMARY KEY REFERENCES entities(entity_id), reason TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','investigating','resolved')),
 owner TEXT NOT NULL DEFAULT 'Unassigned', note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT NOT NULL, action TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE VIEW IF NOT EXISTS engineering_kpis AS
 SELECT substr(e.event_time,1,10) day, count(*) scored, sum(o.failed IS NOT NULL) outcomes_known,
 avg(CASE WHEN o.failed IS NOT NULL THEN 1.0-o.failed END) observed_pass_yield,
 avg(p.risk) mean_risk, sum(p.decision='review') review_count,
 sum(p.decision='abstain') abstentions, avg(e.missing_fraction) missing_fraction
 FROM entities e JOIN predictions p USING(entity_id) LEFT JOIN outcomes o USING(entity_id)
 GROUP BY substr(e.event_time,1,10);
'''


class Store:
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db: db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    def rows(self, query, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, args)]

    def ingest(self, entity_id, timestamp, digest, values, missing, risk, decision, model_hash, latency, excursion=False):
        with self.connect() as db:
            old = db.execute('SELECT payload_hash FROM entities WHERE entity_id=?', (entity_id,)).fetchone()
            if old:
                if old['payload_hash'] != digest: raise ValueError('Entity ID already exists with a different payload')
                return False
            db.execute('INSERT INTO entities VALUES(?,?,?,?,?)', (entity_id,timestamp,digest,json.dumps(values),missing))
            db.execute('INSERT INTO predictions VALUES(?,?,?,?,?)', (entity_id,risk,decision,model_hash,latency))
            if decision != 'screen' or excursion:
                reason = 'Data quality gate' if decision == 'abstain' else ('Risk threshold' if decision == 'review' else 'Process reference excursion')
                db.execute('INSERT INTO investigations(entity_id,reason) VALUES(?,?)', (entity_id, reason))
            db.execute('INSERT INTO audit(entity_id,action,detail) VALUES(?,?,?)', (entity_id,'scored',decision))
            return True

    def reveal(self, entity_id, failed, event_time):
        with self.connect() as db:
            existing = db.execute('SELECT failed FROM outcomes WHERE entity_id=?', (entity_id,)).fetchone()
            if existing:
                if existing['failed'] != failed: raise ValueError('Outcome conflict')
                return
            db.execute('INSERT INTO outcomes VALUES(?,?,?)', (entity_id,failed,event_time))
            db.execute('INSERT INTO audit(entity_id,action,detail) VALUES(?,?,?)', (entity_id,'outcome',str(failed)))

    def update_case(self, entity_id, status, owner, note):
        with self.connect() as db:
            cursor = db.execute('UPDATE investigations SET status=?,owner=?,note=? WHERE entity_id=?', (status,owner,note,entity_id))
            if cursor.rowcount == 0: return False
            db.execute('INSERT INTO audit(entity_id,action,detail) VALUES(?,?,?)', (entity_id,'case_updated',json.dumps({'status':status,'owner':owner,'note':note})))
            return True

    def open_case(self, entity_id):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM entities WHERE entity_id=?',(entity_id,)).fetchone():
                return None
            created = db.execute("INSERT OR IGNORE INTO investigations(entity_id,reason) VALUES(?,'Engineer review')",(entity_id,)).rowcount == 1
            if created:
                db.execute('INSERT INTO audit(entity_id,action,detail) VALUES(?,?,?)',(entity_id,'review_opened','Engineer review'))
            return created
