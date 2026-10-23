import json
import numpy as np
import pandas as pd
import pytest
import joblib
from fastapi.testclient import TestClient
from fabwatch.api import create_app
from fabwatch.data import load, partitions, ART, REPORT, sha
from fabwatch.monitor import ewma
from fabwatch.train import predict


@pytest.fixture(scope='session')
def dataset(): return load()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as c: yield c


def payload(entity='external-1', missing=0):
    return {'entity_id':entity,'timestamp':'2026-10-23T12:00:00','sensors':[None]*missing+[0.]*(590-missing)}


def test_source_shape_and_counts(dataset):
    x,m=dataset
    assert x.shape==(1567,590)
    assert m.failed.sum()==104
    assert m.entity_id.is_unique


def test_chronology_no_shared_timestamps(dataset):
    _,m=dataset;s=partitions(m); previous=None
    assert sum(len(v) for v in s.values())==1567
    assert len(set(np.concatenate(list(s.values()))))==1567
    for ids in s.values():
        assert m.iloc[ids].failed.nunique()==2
        if previous is not None: assert previous < m.iloc[ids].timestamp.min()
        previous=m.iloc[ids].timestamp.max()


def test_imputer_fitted_on_training_only(dataset):
    x,m=dataset;b=joblib.load(ART/'model.joblib');tr=partitions(m)['train']
    np.testing.assert_allclose(b['pipeline']['impute'].statistics_,x.iloc[tr].median(),equal_nan=True)


def test_frozen_prediction_artifact_parity(dataset):
    x,m=dataset;b=joblib.load(ART/'model.joblib');t=partitions(m)['test']
    saved=pd.read_csv(REPORT/'test_predictions.csv')
    np.testing.assert_allclose(predict(b,x.iloc[t]),saved.risk,rtol=0,atol=1e-14)
    assert sha(ART/'model.joblib')==json.loads((REPORT/'metrics.json').read_text())['model_sha256']


def test_baseline_accuracy_would_be_misleading():
    r=json.loads((REPORT/'metrics.json').read_text())
    assert r['all_pass']['recall']==0
    assert r['all_pass']['tn']/r['splits']['test']['n']>.9


def test_health_and_empty_yield(client):
    assert client.get('/api/health').json()['status']=='ready'
    assert client.get('/api/overview').json()['summary']['yield'] is None


@pytest.mark.parametrize('change',[
    {'sensors':[0.]}, {'sensors':[0.]*591}, {'entity_id':'<script>'},
    {'timestamp':'yesterday'}, {'failed':1}, {'extra':'unknown'},
    {'sensors':['1']+[0.]*589}, {'sensors':[True]+[0.]*589},
    {'entity_id':'SECOM-forged'}])
def test_ingress_rejects_invalid_or_label_leakage(client,change):
    p=payload();p.update(change)
    assert client.post('/api/predict',json=p).status_code==422


@pytest.mark.parametrize('number',['NaN','Infinity','-Infinity'])
def test_nonfinite_rejected(client,number):
    raw=json.dumps(payload()).replace('0.0',number,1)
    assert client.post('/api/predict',content=raw,headers={'Content-Type':'application/json'}).status_code==422


def test_idempotency_and_conflict(client):
    p=payload();a=client.post('/api/predict',json=p);b=client.post('/api/predict',json=p)
    assert a.status_code==200 and a.json()['created']
    assert b.status_code==200 and not b.json()['created']
    assert a.json()['latency_ms']==b.json()['latency_ms']
    p['sensors'][0]=1
    assert client.post('/api/predict',json=p).status_code==409
    assert client.get('/api/overview').json()['summary']['scored']==1


def test_missingness_abstention_and_case_audit(client):
    r=client.post('/api/predict',json=payload(missing=590)).json()
    assert r['decision']=='abstain'
    cases=client.get('/api/investigations').json()
    assert cases[0]['reason']=='Data quality gate'
    assert client.patch('/api/investigations/external-1',json={'status':'investigating','owner':'Process Engineering','note':'Check sensor source.'}).status_code==200
    assert client.get('/api/entity/external-1').json()['audit'][-1]['action']=='case_updated'
    assert client.patch('/api/investigations/external-1',json={'status':'invalid','owner':'PE','note':''}).status_code==422


def test_delayed_outcome_no_future_leakage(client):
    client.post('/api/replay/step?count=10')
    d=client.get('/api/overview').json()
    assert d['summary']['scored']==10 and d['summary']['known']==0
    client.post('/api/replay/step?count=1')
    d=client.get('/api/overview').json()
    assert d['summary']['known']==1
    assert sum(r['failed'] is not None for r in d['rows'])==1


def test_persistent_replay_checkpoint(tmp_path):
    path=tmp_path/'restart.db'
    with TestClient(create_app(path)) as c: c.post('/api/replay/step?count=20')
    with TestClient(create_app(path)) as c:
        assert c.get('/api/overview').json()['replay']['cursor']==20
        c.post('/api/replay/step?count=5')
        assert c.get('/api/overview').json()['summary']['scored']==25


@pytest.mark.parametrize('count',[0,-1,51])
def test_invalid_replay_count(client,count):
    assert client.post(f'/api/replay/step?count={count}').status_code==422


def test_sql_exports_and_unknown_routes(client):
    client.post('/api/replay/step?count=15')
    response=client.get('/api/export/kpis')
    assert response.status_code==200 and 'observed_pass_yield' in response.text
    assert client.get('/api/export/secrets').status_code==404
    assert client.get('/api/entity/unknown').status_code==404
    assert client.get('/').status_code==200


def test_csv_formula_notes_are_exported_as_text(client):
    client.post('/api/predict',json=payload(missing=590))
    client.patch('/api/investigations/external-1',json={'status':'open','owner':'=HYPERLINK(1)','note':'+cmd'})
    exported=client.get('/api/export/investigations').text
    assert "'=HYPERLINK" in exported and "'+cmd" in exported


def test_ewma_missing_reading_and_closed_form():
    a=ewma([1,None,1],0,1,lam=.2)
    b=ewma([1,1],0,1,lam=.2)
    assert a==b and len(a)==2
    assert a[0]['value']==pytest.approx(.2)
    assert a[1]['value']==pytest.approx(.36)
    assert a[0]['upper']==pytest.approx(.6)


def test_entire_replay_reconciles_and_stops(client,dataset):
    for _ in range(7): assert client.post('/api/replay/step?count=50').status_code==200
    d=client.get('/api/overview').json()
    assert d['summary']['scored']==314 and d['summary']['known']==304
    assert d['replay']['cursor']==314
    assert all(r['risk']>=0 and r['risk']<=1 for r in d['rows'])
    assert client.post('/api/replay/step?count=50').json()['cursor']==314
    assert len(client.get('/api/quality').json()['sensors'])==590
