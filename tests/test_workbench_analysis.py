import numpy as np
from fastapi.testclient import TestClient
from fabwatch.api import create_app
from fabwatch.data import load,partitions


def test_catalog_is_training_reference_and_analysis_tracks_only_arrivals(tmp_path):
    with TestClient(create_app(tmp_path/'analysis.db')) as client:
        catalog=client.get('/api/signals').json()
        assert len(catalog['signals'])==590 and len(catalog['suggested'])==12
        sensor=catalog['suggested'][0]
        x,m=load(); tr=partitions(m)['train']
        reference=next(row for row in catalog['signals'] if row['sensor']==sensor)
        assert reference['mean']==x.iloc[tr][sensor].mean()
        assert client.get('/api/analysis').json()['rows']==[]
        client.post('/api/replay/step?count=15')
        response=client.get('/api/analysis',params={'signals':sensor}).json()
        assert len(response['rows'])==15
        assert sum(row['failed'] is not None for row in response['rows'])==5
        assert all(set(row['signals'])=={sensor} for row in response['rows'])
        t=partitions(m)['test'][:15]
        for row,i in zip(response['rows'],t):
            actual=x.iloc[i][sensor]
            assert row['signals'][sensor]==(None if np.isnan(actual) else actual)
        # EWMA starts at the frozen train mean, not the first test point.
        row=next(row for row in response['rows'] if row['signals'][sensor] is not None)
        expected=.2*row['signals'][sensor]+.8*reference['mean']
        assert abs(row['ewma'][sensor]['value']-expected)<1e-10


def test_analysis_contract_rejects_invalid_and_bounds_output(tmp_path):
    with TestClient(create_app(tmp_path/'validation.db')) as client:
        for params in [{'signals':'sensor_999'},{'signals':'sensor_001,unknown'},{'limit':0},{'limit':1001},
                       {'signals':','.join(f'sensor_{i:03d}' for i in range(17))}]:
            assert client.get('/api/analysis',params=params).status_code==422
        client.post('/api/replay/step?count=10')
        response=client.get('/api/analysis?limit=3&signals=sensor_001,sensor_001').json()
        assert len(response['rows'])==3 and len(response['signals'])==1
        assert response['latest_event']==response['rows'][-1]['event_time']


def test_new_session_preserves_and_restores_previous_cases(tmp_path):
    original=tmp_path/'original.db'
    with TestClient(create_app(original)) as client:
        client.post('/api/replay/step?count=20')
        entity=client.get('/api/overview').json()['rows'][0]['entity_id']
        assert client.post('/api/investigations/'+entity).status_code==200
        client.patch('/api/investigations/'+entity,json={'status':'investigating','owner':'PE','note':'Preserved evidence'})
        created=client.post('/api/replay/new').json()
        assert created['previous_preserved'] and original.exists()
        assert client.get('/api/overview').json()['summary']['scored']==0
        client.post('/api/replay/step?count=3')
        assert len(client.get('/api/replay/sessions').json())==2
        response=client.post('/api/replay/select',json={'session':'original'})
        assert response.status_code==200 and response.json()['cursor']==20
        assert client.get('/api/entity/'+entity).json()['investigation'][0]['note']=='Preserved evidence'
        assert client.post('/api/replay/select',json={'session':'../private'}).status_code==422
        assert client.post('/api/replay/select',json={'session':'unknown'}).status_code==404
    # Session files can also be discovered after process restart.
    with TestClient(create_app(original)) as client:
        assert len(client.get('/api/replay/sessions').json())==2
        assert client.post('/api/replay/select',json={'session':created['session']}).json()['cursor']==3


def test_manual_review_is_auditable_and_idempotent(tmp_path):
    with TestClient(create_app(tmp_path/'manual.db')) as client:
        assert client.post('/api/investigations/unknown').status_code==404
        client.post('/api/replay/step?count=5')
        rows=client.get('/api/analysis').json()['rows']
        entity=next(row['entity_id'] for row in rows if not row['reason'])
        assert client.post('/api/investigations/'+entity).json()['created']
        assert not client.post('/api/investigations/'+entity).json()['created']
        data=client.get('/api/entity/'+entity).json()
        assert data['investigation'][0]['reason']=='Engineer review'
        assert sum(row['action']=='review_opened' for row in data['audit'])==1
        assert data['prediction']['entity_id']==entity
