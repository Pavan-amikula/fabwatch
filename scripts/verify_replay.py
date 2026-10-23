"""Reconcile a complete historical replay; export BI-ready sample evidence."""
import json
import platform
import tempfile
from pathlib import Path
import sklearn
from fastapi.testclient import TestClient
from fabwatch.api import create_app
from fabwatch.data import REPORT


def main():
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(create_app(Path(directory)/'warehouse.db')) as client:
            for _ in range(7):
                client.post('/api/replay/step?count=50').raise_for_status()
            overview=client.get('/api/overview').json()
            cases=client.get('/api/investigations').json()
            assert overview['summary']['scored']==314
            assert overview['summary']['known']==304
            assert overview['summary']['abstentions']==3
            assert len(cases)==8
            counts={reason:sum(r['reason']==reason for r in cases) for reason in sorted({r['reason'] for r in cases})}
            for kind in ['kpis','investigations','audit']:
                (REPORT/f'sample_{kind}.csv').write_text(client.get('/api/export/'+kind).text,encoding='utf-8')
            for row in overview['rows']:
                response=client.get('/api/entity/'+row['entity_id'])
                assert response.status_code==200
            result={'python':platform.python_version(),'sklearn':sklearn.__version__,
                    'platform':platform.platform(),'replayed':314,'revealed_outcomes':304,
                    'pending_outcomes':10,'queue_reasons':counts,'entity_evidence_checks':314,
                    'model_risk_reviews':overview['summary']['reviews'],
                    'observed_pass_yield':overview['summary']['yield'],
                    'docker_executed':False,'power_bi_jmp_minitab_executed':False,
                    'scope':'Local CPU replay; source and frozen-artifact checks; no fab connection'}
            (REPORT/'verification.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result,indent=2))


if __name__=='__main__': main()
