"""Authenticated case lifecycle on synthetic data; no labels or real predictions."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from fraud_investigation.copilot_api import create_copilot_app
from fraud_investigation.database import APP_SCHEMA, SEARCH_INDEXES
from fraud_investigation.evidence_service import execute_and_record
from fraud_investigation.scoring_service import FINAL_THRESHOLD
from scripts.export_copilot_openapi import CASES_TEMPLATE, export


class SyntheticScorer:
    """Explicitly simulated score, used only to verify persistence and citations."""
    def __init__(self):
        self.calls = 0

    def score_transaction(self, transaction_id):
        self.calls += 1
        return dict(transaction_id=transaction_id, suspicion_score=0.6,
                    threshold=FINAL_THRESHOLD, alert=True,
                    model_version='synthetic_test_model', policy_version='synthetic_test_policy')


class CopilotCasesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'app.sqlite'
        self.key = 'synthetic-only-case-test-key-more-than-32-characters'
        self.auth = {'X-API-Key': self.key}
        self.tx = (5).to_bytes(16, 'big').hex()
        with sqlite3.connect(self.database) as db:
            db.executescript(APP_SCHEMA)
            db.executemany('INSERT INTO accounts VALUES (?)', [('A',), ('B',)])
            for line,step,origin,dest in [(2,1,'A','B'), (3,2,'B','A'),
                                          (4,3,'A','B'), (5,3,'A','B'), (6,4,'B','A')]:
                db.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, 'TRANSFER', "
                           "'10.00', ?, '20.00', '10.00', ?, '0.00', '10.00')",
                           (line,line.to_bytes(16,'big'),b'\0'*32,step,origin,dest))
            db.executescript(SEARCH_INDEXES)
            self.original_rows = db.execute('SELECT * FROM transactions ORDER BY source_line_number').fetchall()

    def tearDown(self):
        self.temp.cleanup()

    def app(self, missing=False):
        return create_copilot_app(self.root/'missing.sqlite' if missing else self.database,
                                  api_key=self.key, model_path=self.root/'missing.joblib',
                                  manifest_path=self.root/'missing.json')

    def headers(self, key):
        return {**self.auth, 'Idempotency-Key':key}

    def create(self, client, key='case'):
        response=client.post('/cases',headers=self.headers(key),json={'transaction_id':self.tx})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def check(self,client,case,operation,key=None,**bounds):
        return client.post(f'/cases/{case}/runs',headers=self.headers(key or operation),
                           json={'operation':operation,**bounds})

    def test_authentication_covers_every_new_operation_before_writes(self):
        identifier='a'*32
        urls=[('post','/cases',{'transaction_id':self.tx}),
              ('get',f'/cases/{identifier}',None),
              ('post',f'/cases/{identifier}/runs',{'operation':'transaction'}),
              ('get',f'/cases/{identifier}/runs',None),
              ('get',f'/cases/{identifier}/runs/{identifier}',None),
              ('post',f'/cases/{identifier}/reports',None),
              ('get',f'/cases/{identifier}/reports',None),
              ('get',f'/cases/{identifier}/reports/1',None)]
        with TestClient(self.app()) as client:
            for method,url,body in urls:
                for headers in ({},{'X-API-Key':'incorrect'}):
                    response=client.request(method,url,headers=headers,json=body)
                    self.assertEqual(response.status_code,401,response.text)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM investigation_cases').fetchone()[0],0)

    def test_recorded_workflow_partial_report_and_retries_survive_restart(self):
        with TestClient(self.app()) as client:
            created=self.create(client);case=created['case_id']
            self.assertEqual(self.create(client),created)
            self.assertEqual(client.get(f'/cases/{case}',headers=self.auth).json()['case_id'],case)
            checks={op:self.check(client,case,op).json() for op in
                    ['transaction','score','sender_history','recipient_history']}
            self.assertEqual(checks['score']['status'],'unavailable')
            self.assertIsNone(checks['score']['result'])
            for op in ['sender_history','recipient_history']:
                self.assertEqual(checks[op]['status'],'succeeded')
                self.assertTrue(all(t['step']<3 for t in checks[op]['result']['transactions']))
            report=client.post(f'/cases/{case}/reports',headers=self.headers('report')).json()
            self.assertEqual(report['version'],1)
            self.assertIsNone(report['body']['score'])
            self.assertEqual(report['body']['errors'][0]['evidence_ref'],checks['score']['run_id'])
            self.assertEqual(set(report['evidence_refs']),{c['run_id'] for c in checks.values()})
            self.assertTrue(all(f['evidence_ref']==checks['transaction']['run_id']
                                for f in report['body']['facts']))
            self.assertIn('# Investigation report',report['markdown'])
            self.assertIn('ML score unavailable or not executed',report['body']['missing'])
            self.assertEqual(self.check(client,case,'transaction').json(),checks['transaction'])
            self.assertEqual(client.get(f'/cases/{case}/runs/{checks["transaction"]["run_id"]}',headers=self.auth).json(),checks['transaction'])
            self.assertTrue(client.get(f'/cases/{case}/runs?limit=1',headers=self.auth).json()['truncated'])
        with TestClient(self.app()) as client:
            self.assertEqual(self.create(client),created)
            self.assertEqual(self.check(client,case,'transaction').json(),checks['transaction'])
            # Add another check, then retry the old report request: old snapshot must remain identical.
            later=self.check(client,case,'transaction',key='deliberate-new-check').json()
            self.assertEqual(client.post(f'/cases/{case}/reports',headers=self.headers('report')).json(),report)
            report2=client.post(f'/cases/{case}/reports',headers=self.headers('report-v2')).json()
            self.assertEqual(report2['version'],2)
            self.assertIn(later['run_id'],report2['evidence_refs'])
            self.assertEqual(client.get(f'/cases/{case}/reports/1',headers=self.auth).json(),report)
            self.assertTrue(client.get(f'/cases/{case}/reports?limit=1',headers=self.auth).json()['truncated'])
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM investigation_cases').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM investigation_reports').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT * FROM transactions ORDER BY source_line_number').fetchall(),self.original_rows)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        for forbidden in ['isFraud','isFlaggedFraud','newbalance_orig','newbalance_dest']:
            self.assertNotIn(forbidden,json.dumps(report))

    def test_gateway_uses_loaded_scorer_and_records_its_exact_result(self):
        app=self.app();scorer=SyntheticScorer()
        with TestClient(app) as client:
            app.state.score_service=scorer;app.state.scoring_available=True
            case=self.create(client)['case_id']
            result=self.check(client,case,'score').json()
            self.assertEqual(result['status'],'succeeded')
            self.assertEqual(result['result']['model_version'],'synthetic_test_model')
            self.assertEqual(result['result']['threshold'],FINAL_THRESHOLD)
            self.assertEqual(self.check(client,case,'score').json(),result)
            self.assertEqual(scorer.calls,1)
            report=client.post(f'/cases/{case}/reports',headers=self.headers('report')).json()
            self.assertEqual(report['body']['score']['evidence_ref'],result['run_id'])
            self.assertIn('not confirmed fraud',report['body']['score']['interpretation'])

    def test_validation_conflicts_and_no_forged_evidence_or_events(self):
        with TestClient(self.app()) as client:
            case=self.create(client)['case_id']
            unknown='f'*32
            self.assertEqual(client.post('/cases',headers=self.headers('other'),json={'transaction_id':unknown}).status_code,404)
            for extra in [{'result':{'score':1}}, {'verification':'backend_executed'},
                          {'sql':'SELECT * FROM transactions'}, {'transaction_id':self.tx}]:
                self.assertEqual(self.check(client,case,'score',key='bad',**extra).status_code,422)
            self.assertEqual(self.check(client,case,'sql').status_code,422)
            self.assertEqual(self.check(client,case,'sender_history',limit=101).status_code,422)
            self.assertEqual(self.check(client,case,'recipient_history',lookback_steps=169).status_code,422)
            self.assertEqual(self.check(client,case,'score',limit=10).status_code,422)
            self.assertEqual(client.post(f'/cases/{case}/runs',headers=self.auth,json={'operation':'score'}).status_code,422)
            self.assertEqual(client.post(f'/cases/{case}/reports',headers=self.auth).status_code,422)
            self.check(client,case,'transaction',key='same')
            self.assertEqual(self.check(client,case,'score',key='same').status_code,409)
            other_tx=(2).to_bytes(16,'big').hex()
            self.assertEqual(client.post('/cases',headers=self.headers('case'),json={'transaction_id':other_tx}).status_code,409)
            for method,url in [('post',f'/cases/{case}/events'),('get',f'/cases/{case}/events'),
                               ('get','/openapi.json'),('post','/sql')]:
                self.assertEqual(client.request(method,url,headers=self.auth).status_code,404)
            self.assertEqual(client.get('/cases/invalid',headers=self.auth).status_code,422)
            self.assertEqual(client.get(f'/cases/{case}/reports/0',headers=self.auth).status_code,422)
            self.assertEqual(client.get(f'/cases/{case}/reports/1',headers=self.auth).status_code,404)
            self.assertEqual(client.get(f'/cases/{unknown}',headers=self.auth).status_code,404)
            self.assertEqual(client.post(f'/cases/{unknown}/reports',headers=self.headers('missing')).status_code,404)
        with TestClient(self.app(missing=True)) as client:
            response=client.post('/cases',headers=self.headers('case'),json={'transaction_id':self.tx})
            self.assertEqual(response.status_code,503)
            self.assertNotIn(str(self.root),response.text)

    def test_interrupted_run_stays_visible_and_other_case_cannot_read_its_evidence(self):
        with TestClient(self.app()) as client:
            case=self.create(client)['case_id']
            other=self.create(client,'other-case')['case_id']
            def stop():raise RuntimeError('synthetic interruption')
            with self.assertRaises(RuntimeError):
                execute_and_record(self.database,case,'interrupted','transaction',{},after_claim=stop)
            self.assertEqual(self.check(client,case,'transaction',key='interrupted').status_code,409)
            record=client.get(f'/cases/{case}/runs',headers=self.auth).json()['runs'][0]
            self.assertEqual(record['verification'],'pending')
            self.assertEqual(client.get(f'/cases/{other}/runs/{record["run_id"]}',headers=self.auth).status_code,404)
            report=client.post(f'/cases/{case}/reports',headers=self.headers('partial')).json()
            self.assertEqual(report['body']['facts'],[])
            self.assertEqual(report['body']['incomplete'][0]['evidence_ref'],record['run_id'])

    def test_report_failure_rolls_back_version_and_retry_cache_together(self):
        with TestClient(self.app()) as client:
            case=self.create(client)['case_id']
            with patch('fraud_investigation.report_service._remember',side_effect=sqlite3.OperationalError('synthetic disk failure')):
                response=client.post(f'/cases/{case}/reports',headers=self.headers('atomic'))
                self.assertEqual(response.status_code,503)
            report=client.post(f'/cases/{case}/reports',headers=self.headers('atomic')).json()
            self.assertEqual(report['version'],1)
            self.assertEqual(client.post(f'/cases/{case}/reports',headers=self.headers('atomic')).json(),report)

    def test_swagger_describes_exact_protected_route_surface_and_valid_references(self):
        p=self.root/'cases.swagger.json';export('https://demo.example.org',p,tool='cases')
        spec=json.loads(p.read_text());app=self.app();paths=app.openapi()['paths']
        ids=[]
        for path,methods in spec['paths'].items():
            for method,op in methods.items():
                ids.append(op['operationId'])
                self.assertIn(path,paths)
                self.assertIn(method,paths[path])
                self.assertEqual(paths[path][method]['operationId'],op['operationId'])
                self.assertEqual(op['security'],[{'ApiKeyAuth':[]}])
                self.assertTrue(op['description'])
                if method=='post':
                    self.assertTrue(any(x['name']=='Idempotency-Key' and x['required'] for x in op['parameters']))
        self.assertEqual(len(ids),9);self.assertEqual(len(set(ids)),9)
        def walk(value):
            if isinstance(value,dict):
                if '$ref' in value:self.assertIn(value['$ref'].split('/')[-1],spec['definitions'])
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        walk(spec)
        self.assertEqual(spec['host'],'demo.example.org')
        self.assertEqual(spec['securityDefinitions']['ApiKeyAuth']['name'],'X-API-Key')
        self.assertNotIn(self.key,p.read_text())
        self.assertIn('.invalid',CASES_TEMPLATE.read_text())


if __name__=='__main__':unittest.main()
