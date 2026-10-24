"""Case rediscovery by transaction: isolated synthetic storage, no model predictions."""

import hashlib
import json
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import test_copilot_cases as fixtures
from fraud_investigation.case_service import find_cases_by_transaction
from scripts.export_copilot_openapi import export


class CaseSearchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CopilotCasesTests()
        self.fixture.setUp()
        self.tx = self.fixture.tx
        self.auth = self.fixture.auth
        self.database = self.fixture.database

    def tearDown(self):
        self.fixture.tearDown()

    def search(self, client, tx=None, limit=10, auth=True):
        return client.get('/cases',params={'transaction_id':tx or self.tx,'limit':limit},
                          headers=self.auth if auth else {})

    def digest(self):
        return hashlib.sha256(self.database.read_bytes()).hexdigest()

    def test_known_transaction_without_cases_is_empty_not_unknown(self):
        before = self.digest()
        with TestClient(self.fixture.app()) as client:
            response = self.search(client)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json(),{'transaction_id':self.tx,'limit':10,
                                              'returned_count':0,'truncated':False,'cases':[]})
            missing = self.search(client,'f'*32)
            self.assertEqual(missing.status_code,404)
            self.assertEqual(missing.json()['detail'],'Transaction not found')
        self.assertEqual(self.digest(),before)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name IN "
                                        "('investigation_idempotency','investigation_reports',"
                                        "'investigation_cases_transaction_created')").fetchall(),[])

    def test_exact_transaction_filter_stable_order_bounds_and_report_metadata(self):
        with TestClient(self.fixture.app()) as client:
            created = [self.fixture.create(client,f'case-{i}') for i in range(3)]
            other_tx = (2).to_bytes(16,'big').hex()
            other = client.post('/cases',headers=self.fixture.headers('other'),
                                json={'transaction_id':other_tx}).json()
            # Equal timestamps must have a stable documented tie-breaker.
            with sqlite3.connect(self.database) as db:
                db.execute("UPDATE investigation_cases SET created_at='2026-01-01T00:00:00Z'")
            ids = sorted([c['case_id'] for c in created],reverse=True)
            first = ids[0]
            report1 = client.post(f'/cases/{first}/reports',headers=self.fixture.headers('v1')).json()
            report2 = client.post(f'/cases/{first}/reports',headers=self.fixture.headers('v2')).json()
            before = self.digest()
            result = self.search(client).json()
            self.assertEqual([c['case_id'] for c in result['cases']],ids)
            self.assertNotIn(other['case_id'],[c['case_id'] for c in result['cases']])
            self.assertEqual(result['cases'][0]['latest_report'],{
                k:report2[k] for k in ('report_id','version','generated_at')})
            self.assertTrue(all(c['latest_report'] is None for c in result['cases'][1:]))
            # A saved partial report does not change the case to closed or imply completeness.
            self.assertEqual(result['cases'][0]['status'],'open')
            self.assertTrue(report2['body']['missing'])
            short = self.search(client,limit=1).json()
            self.assertEqual(short['returned_count'],1)
            self.assertTrue(short['truncated'])
            self.assertEqual(short['cases'][0]['case_id'],first)
            self.assertFalse(self.search(client,limit=3).json()['truncated'])
            self.assertEqual(self.digest(),before)
            for forbidden in ['isFraud','isFlaggedFraud','newbalance_orig','newbalance_dest']:
                self.assertNotIn(forbidden,json.dumps(result))
            # Newest creation time takes precedence over case-ID order.
            last = ids[-1]
            with sqlite3.connect(self.database) as db:
                db.execute("UPDATE investigation_cases SET created_at='2026-02-01T00:00:00Z' "
                           "WHERE case_id=?",(last,))
            self.assertEqual(self.search(client).json()['cases'][0]['case_id'],last)
            self.assertEqual(client.get(f'/cases/{first}/reports/1',headers=self.auth).json(),report1)
        with TestClient(self.fixture.app()) as client:
            self.assertEqual(self.search(client).json()['returned_count'],3)

    def test_authentication_identifier_normalization_and_validation(self):
        with TestClient(self.fixture.app()) as client:
            self.assertEqual(self.search(client,auth=False).status_code,401)
            self.assertEqual(client.get('/cases',headers={'X-API-Key':'wrong'},
                                        params={'transaction_id':self.tx}).status_code,401)
            self.assertEqual(client.get('/cases',headers=self.auth).status_code,422)
            for bad in ['0','g'*32,"' OR 1=1 --"]:
                self.assertEqual(self.search(client,bad).status_code,422)
            for limit in [0,101]:
                self.assertEqual(self.search(client,limit=limit).status_code,422)
            # A known identifier containing alphabetic hex digits verifies case normalization.
            upper = 'abcdef0123456789abcdef0123456789'
            with sqlite3.connect(self.database) as db:
                db.execute("INSERT INTO transactions VALUES (20, ?, ?, 1, 'TRANSFER', '1', "
                           "'A', '2', '1', 'B', '0', '1')",(bytes.fromhex(upper),b'\0'*32))
            created=client.post('/cases',headers=self.fixture.headers('upper'),
                                json={'transaction_id':upper.upper()}).json()
            result=self.search(client,upper.upper()).json()
            self.assertEqual(result['transaction_id'],upper)
            self.assertEqual(result['cases'][0]['case_id'],created['case_id'])
        with self.assertRaises(ValueError):find_cases_by_transaction(self.database,'bad')
        with self.assertRaises(ValueError):find_cases_by_transaction(self.database,self.tx,101)

    def test_database_failure_is_not_empty_and_does_not_create_missing_file(self):
        missing = self.fixture.root/'missing.sqlite'
        with TestClient(self.fixture.app(missing=True)) as client:
            response = self.search(client)
            self.assertEqual(response.status_code,503)
            self.assertNotIn('cases',response.json())
            self.assertNotIn(str(self.fixture.root),response.text)
        self.assertFalse(missing.exists())
        with sqlite3.connect(self.database) as db:
            db.execute('DROP TABLE investigation_events')
            db.execute('DROP TABLE investigation_cases')
        with TestClient(self.fixture.app()) as client:
            response=self.search(client)
            self.assertEqual(response.status_code,503)
            self.assertNotIn('cases',response.json())

    def test_legacy_without_report_table_or_index_and_index_plan_after_write(self):
        with TestClient(self.fixture.app()) as client:
            case=self.fixture.create(client)['case_id']
            with sqlite3.connect(self.database) as db:
                plan=db.execute('EXPLAIN QUERY PLAN SELECT case_id FROM investigation_cases '
                                'WHERE transaction_id=? ORDER BY created_at DESC, case_id DESC LIMIT ?',
                                (bytes.fromhex(self.tx),11)).fetchall()
                self.assertIn('investigation_cases_transaction_created',str(plan))
                self.assertNotIn('TEMP B-TREE',str(plan))
                db.execute('DROP INDEX investigation_cases_transaction_created')
            before=self.digest()
            result=self.search(client).json()
            self.assertEqual(result['cases'][0]['case_id'],case)
            self.assertIsNone(result['cases'][0]['latest_report'])
            self.assertEqual(self.digest(),before)

    def test_export_search_contract_and_no_write_side_effects(self):
        output=self.fixture.root/'search.swagger.json'
        export('https://demo.example.org',output,tool='cases')
        spec=json.loads(output.read_text())
        op=spec['paths']['/cases']['get']
        self.assertEqual(op['operationId'],'findInvestigationCasesByTransactionId')
        self.assertEqual(op['security'],[{'ApiKeyAuth':[]}])
        self.assertEqual([p['name'] for p in op['parameters']],['transaction_id','limit'])
        self.assertTrue(op['parameters'][0]['required'])
        self.assertIn('404',op['responses']);self.assertIn('503',op['responses'])
        self.assertEqual(op['responses']['200']['schema']['$ref'],'#/definitions/CaseSearchResponse')
        with TestClient(self.fixture.app()) as client:
            # Even when a case exists, repeated searches must never execute checks or create reports.
            self.fixture.create(client)
            with patch('fraud_investigation.copilot_case_api.execute_and_record',side_effect=AssertionError), \
                 patch('fraud_investigation.copilot_case_api.generate_report',side_effect=AssertionError):
                for _ in range(3):self.assertEqual(self.search(client).status_code,200)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM investigation_cases').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name IN "
                                        "('investigation_tool_runs','investigation_reports')").fetchall(),[])


if __name__=='__main__':unittest.main()
