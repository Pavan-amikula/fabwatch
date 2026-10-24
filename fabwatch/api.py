import csv
import hashlib
import io
import json
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Literal
import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .data import ROOT, ART, REPORT, load, partitions, sha
from .train import predict
from .monitor import explain, ewma
from .store import Store


class Measurement(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    entity_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,64}$')
    timestamp: datetime
    sensors: list[float | None] = Field(min_length=590, max_length=590)

    @field_validator('sensors', mode='before')
    @classmethod
    def reject_boolean_and_strings(cls, values):
        if isinstance(values, list) and any(v is not None and (isinstance(v, bool) or not isinstance(v, (int,float))) for v in values):
            raise ValueError('Measurements must be JSON numbers or null')
        return values


class CaseUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['open','investigating','resolved']
    owner: str = Field(min_length=1,max_length=80)
    note: str = Field(max_length=2000)


class SessionSelect(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')


def create_app(db_path=None):
    app = FastAPI(title='FabWatch', version='1.0.0', description='Local manufacturing analytics demonstration. Replay is historical, not a factory connection.')

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo NaN/Inf inputs into a JSON error body: strict serializers
        # would raise and turn a validation rejection into an HTTP 500.
        return JSONResponse(status_code=422, content={'detail':[
            {key: error[key] for key in ('type','loc','msg')} for error in exc.errors()]})

    metrics = json.loads((REPORT / 'metrics.json').read_text())
    if sha(ART / 'model.joblib') != metrics['model_sha256']: raise RuntimeError('Model fingerprint mismatch')
    bundle = joblib.load(ART / 'model.joblib')
    x, meta = load(); test_ids = partitions(meta)['test']
    store = Store(db_path or os.environ.get('FABWATCH_DB', ROOT / 'runtime' / 'fabwatch.db'))
    lock = threading.RLock()
    seen = {r['entity_id'] for r in store.rows('SELECT entity_id FROM entities')}
    cursor = sum(meta.iloc[i].entity_id in seen for i in test_ids)
    # Only a contiguous prefix is accepted as a replay checkpoint.
    if any(meta.iloc[i].entity_id not in seen for i in test_ids[:cursor]):
        raise RuntimeError('Replay checkpoint is not contiguous; use a fresh database')
    state = {'cursor': cursor, 'delay': 10, 'session':store.path.stem}
    sessions = {store.path.stem:store.path}
    sessions.update({path.stem:path for path in store.path.parent.glob('session-*.db')})
    training = x.iloc[partitions(meta)['train']]
    quality_frame = pd.read_csv(REPORT / 'sensor_quality.csv')
    signal_catalog = []
    for i, sensor in enumerate(x.columns):
        record = quality_frame.iloc[i].to_dict()
        mean = training[sensor].mean()
        record.update({'mean':None if pd.isna(mean) else float(mean),
                       'median':float(bundle['train_median'][i]), 'sd':float(bundle['train_std'][i]),
                       'reference_signal':sensor in bundle['investigation_sensors']})
        signal_catalog.append(record)
    # Recover any delayed outcomes interrupted between scoring and revelation.
    for offset in range(max(0,cursor-state['delay'])):
        record = meta.iloc[test_ids[offset]]
        reveal_time = meta.iloc[test_ids[offset+state['delay']]].timestamp.isoformat()
        store.reveal(record.entity_id,int(record.failed),reveal_time)
    app.state.store = store

    def score(payload):
        values = payload.sensors
        normalized = {'timestamp': payload.timestamp.isoformat(), 'sensors': values}
        digest = hashlib.sha256(json.dumps(normalized,sort_keys=True,allow_nan=False).encode()).hexdigest()
        missing = sum(v is None for v in values)/590
        start = time.perf_counter()
        row = pd.DataFrame([values], columns=bundle['columns'], dtype=float)
        risk = float(predict(bundle, row)[0])
        latency = (time.perf_counter()-start)*1000
        decision = 'abstain' if missing > bundle['missing_limit'] else ('review' if risk >= bundle['threshold'] else 'screen')
        evidence = explain(bundle, values)
        excursion = any(abs(r['z'] or 0) > 3 for r in evidence)
        try:
            created = store.ingest(payload.entity_id,payload.timestamp.isoformat(),digest,values,missing,risk,decision,metrics['model_sha256'],latency,excursion)
        except ValueError as exc: raise HTTPException(409,str(exc))
        saved = store.rows('SELECT * FROM predictions WHERE entity_id=?',(payload.entity_id,))[0]
        return {**saved, 'created': created, 'missing_fraction': missing,
                'evidence': evidence, 'reference_excursion':excursion, 'interpretation': 'Training associations and standardized deviations; no causal attribution.'}

    @app.get('/api/health')
    def health(): return {'status':'ready','model_sha256':metrics['model_sha256'],'mode':'historical replay + local JSON ingress','session':state['session']}

    @app.get('/api/signals')
    def signals():
        return {'signals':signal_catalog,'suggested':bundle['investigation_sensors'],
                'reference_scope':'training partition only; anonymous signals, no physical units'}

    @app.get('/api/analysis')
    def analysis(signals: str = '', limit: int = 1000):
        chosen = list(dict.fromkeys(signals.split(','))) if signals else bundle['investigation_sensors'][:3]
        if len(chosen)>16 or any(sensor not in bundle['columns'] for sensor in chosen):
            raise HTTPException(422,'Select 1 to 16 known sensor IDs')
        if not 1 <= limit <= 1000: raise HTTPException(422,'limit must be between 1 and 1000')
        indexes = [bundle['columns'].index(sensor) for sensor in chosen]
        with lock:
            rows = store.rows('''SELECT e.entity_id,e.event_time,e.measurements,e.missing_fraction,
                p.risk,p.decision,p.latency_ms,o.failed,i.reason,i.status,i.owner
                FROM entities e JOIN predictions p USING(entity_id) LEFT JOIN outcomes o USING(entity_id)
                LEFT JOIN investigations i USING(entity_id) ORDER BY e.event_time DESC,e.entity_id DESC LIMIT ?''',(limit,))
            for row in rows:
                values = json.loads(row.pop('measurements'))
                row['signals'] = {sensor:values[index] for sensor,index in zip(chosen,indexes)}
            rows.reverse()
            for sensor,index in zip(chosen,indexes):
                mean = signal_catalog[index]['mean']
                mean = signal_catalog[index]['median'] if mean is None else mean
                points = iter(ewma([row['signals'][sensor] for row in rows],mean,signal_catalog[index]['sd']))
                for row in rows:
                    row.setdefault('ewma',{})[sensor] = None if row['signals'][sensor] is None else next(points)
            return {'rows':rows,'signals':[signal_catalog[index] for index in indexes],
                    'session':state['session'],'model_risk_alerts_enabled':bundle['threshold']<=1,
                    'latest_event':rows[-1]['event_time'] if rows else None,
                    'served_at':datetime.now().astimezone().isoformat(),
                    'reference_scope':'training median and SD; excursions are investigation clues'}

    @app.post('/api/replay/new')
    def new_replay():
        nonlocal store
        with lock:
            previous = state['session']
            name = 'session-'+uuid.uuid4().hex[:12]
            # Preserve every prior warehouse; a new session never deletes its predecessor.
            store = Store(store.path.parent / (name+'.db'))
            sessions[name] = store.path
            state.update({'cursor':0,'session':name})
            app.state.store = store
            return {'session':name,'previous_session':previous,'previous_preserved':True,'cursor':0}

    @app.get('/api/replay/sessions')
    def replay_sessions():
        with lock:
            return [{'session':name,'current':name==state['session']} for name in sessions]

    @app.post('/api/replay/select')
    def select_session(body: SessionSelect):
        nonlocal store
        with lock:
            if body.session not in sessions: raise HTTPException(404,'Unknown replay session')
            restored = Store(sessions[body.session])
            restored_ids = {row['entity_id'] for row in restored.rows('SELECT entity_id FROM entities')}
            restored_cursor = sum(meta.iloc[i].entity_id in restored_ids for i in test_ids)
            if any(meta.iloc[i].entity_id not in restored_ids for i in test_ids[:restored_cursor]):
                raise HTTPException(409,'Non-contiguous replay checkpoint')
            store = restored; app.state.store = store
            state.update({'cursor':restored_cursor,'session':body.session})
            for offset in range(max(0,restored_cursor-state['delay'])):
                record = meta.iloc[test_ids[offset]]
                reveal_time = meta.iloc[test_ids[offset+state['delay']]].timestamp.isoformat()
                store.reveal(record.entity_id,int(record.failed),reveal_time)
            return {'session':body.session,'cursor':restored_cursor}

    @app.get('/api/model')
    def model(): return metrics

    @app.post('/api/predict')
    def infer(payload: Measurement):
        if payload.entity_id.startswith('SECOM-'):
            raise HTTPException(422,'SECOM- prefix is reserved for verified dataset replay')
        with lock: return score(payload)

    @app.post('/api/replay/step')
    def step(count: int = 1):
        if count < 1 or count > 50: raise HTTPException(422,'count must be between 1 and 50')
        with lock:
            for _ in range(count):
                if state['cursor'] >= len(test_ids): break
                idx = test_ids[state['cursor']]; record = meta.iloc[idx]
                values = [None if pd.isna(v) else float(v) for v in x.iloc[idx]]
                score(Measurement(entity_id=record.entity_id,timestamp=record.timestamp.to_pydatetime(),sensors=values))
                state['cursor'] += 1
                # Synthetic 10-entity delay; dataset timestamps represent test points,
                # not verified sensor availability times. Never claim pre-test lead time.
                reveal_index = state['cursor']-state['delay']-1
                if reveal_index >= 0:
                    old = meta.iloc[test_ids[reveal_index]]
                    store.reveal(old.entity_id,int(old.failed),record.timestamp.isoformat())
            return {'cursor':state['cursor'],'total':len(test_ids),'pending_outcomes':min(state['cursor'],state['delay'])}

    @app.get('/api/overview')
    def overview():
        with lock:
            return overview_snapshot()

    def overview_snapshot():
        rows = store.rows('''SELECT e.entity_id,e.event_time,e.missing_fraction,p.risk,p.decision,p.latency_ms,o.failed
                             FROM entities e JOIN predictions p USING(entity_id) LEFT JOIN outcomes o USING(entity_id)
                             ORDER BY e.event_time,e.entity_id''')
        known = [r for r in rows if r['failed'] is not None]
        return {'rows':rows,'daily':store.rows('SELECT * FROM engineering_kpis ORDER BY day'),
                'summary': {'scored':len(rows),'known':len(known),'yield':sum(1-r['failed'] for r in known)/len(known) if known else None,
                            'reviews':sum(r['decision']=='review' for r in rows), 'abstentions':sum(r['decision']=='abstain' for r in rows),
                            'missing':float(np.mean([r['missing_fraction'] for r in rows])) if rows else 0},
                'replay':{'cursor':state['cursor'],'total':len(test_ids),'delay':state['delay'],'session':state['session']},
                'threshold':bundle['threshold']}

    @app.get('/api/investigations')
    def cases(): return store.rows('''SELECT i.*,p.risk,e.event_time,o.failed FROM investigations i JOIN entities e USING(entity_id)
                                    JOIN predictions p USING(entity_id) LEFT JOIN outcomes o USING(entity_id) ORDER BY e.event_time DESC''')

    @app.get('/api/entity/{entity_id}')
    def entity(entity_id: str):
        rows = store.rows('SELECT * FROM entities WHERE entity_id=?',(entity_id,))
        if not rows: raise HTTPException(404,'Unknown entity')
        row = rows[0]; values = json.loads(row.pop('measurements'))
        return {**row,'evidence':explain(bundle,values),
                'prediction':store.rows('SELECT * FROM predictions WHERE entity_id=?',(entity_id,))[0],
                'outcome':store.rows('SELECT * FROM outcomes WHERE entity_id=?',(entity_id,)),
                'investigation':store.rows('SELECT * FROM investigations WHERE entity_id=?',(entity_id,)),
                'audit':store.rows('SELECT action,detail,created_at FROM audit WHERE entity_id=? ORDER BY id',(entity_id,))}

    @app.patch('/api/investigations/{entity_id}')
    def update(entity_id: str, body: CaseUpdate):
        if not store.update_case(entity_id,body.status,body.owner,body.note): raise HTTPException(404,'Unknown investigation')
        return {'saved':True}

    @app.post('/api/investigations/{entity_id}')
    def open_review(entity_id: str):
        with lock:
            created = store.open_case(entity_id)
            if created is None: raise HTTPException(404,'Unknown entity')
            return {'created':created}

    @app.get('/api/quality')
    def quality():
        frame = pd.read_csv(REPORT / 'sensor_quality.csv')
        sensor = bundle['investigation_sensors'][0]; i = bundle['columns'].index(sensor)
        rows = store.rows('SELECT measurements,event_time FROM entities ORDER BY event_time,entity_id')
        values = [json.loads(r['measurements'])[i] for r in rows]
        train_mean = float(x.iloc[partitions(meta)['train']][sensor].mean())
        return {'sensors':json.loads(frame.to_json(orient='records')),'missing_limit':bundle['missing_limit'],
                'spc':{'sensor':sensor,'reference':train_mean,'points':ewma(values,train_mean,float(bundle['train_std'][i]))},
                'note':'EWMA exploratory reference: training mean and SD; stability and independence unverified. No specification limits or Cp/Cpk.'}

    @app.get('/api/export/{kind}')
    def export(kind: str):
        queries = {'kpis':'SELECT * FROM engineering_kpis ORDER BY day',
                   'investigations':'SELECT * FROM investigations', 'audit':'SELECT * FROM audit ORDER BY id'}
        if kind not in queries: raise HTTPException(404,'Unknown export')
        rows = store.rows(queries[kind]); buffer = io.StringIO()
        if rows:
            # Preserve notes as text when opened in spreadsheet/statistical tools.
            safe = [{key: ("'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value)
                     for key,value in row.items()} for row in rows]
            writer = csv.DictWriter(buffer,fieldnames=rows[0]); writer.writeheader(); writer.writerows(safe)
        return Response(buffer.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="fabwatch_{kind}.csv"'})

    @app.get('/')
    def index(): return FileResponse(ROOT / 'web' / 'index.html')

    app.mount('/static',StaticFiles(directory=ROOT / 'web'),name='static')
    return app
