"""Banking business invariants and production HTTP boundaries; no cloud calls."""
import copy,json,os,sys,threading,http.client,unittest,uuid
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parent/'job-host'))
from banking import statement,digest,request_fields
import app

ORACLE=json.loads((Path(__file__).parent/'job-host/bank-oracle.json').read_text())

class BankingTests(unittest.TestCase):
    def test_exact_statement_reconciles_to_approved_fixture(self):
        rows=[(t['id'],t['date'],t['description'],t['amount_cents']) for t in ORACLE['transactions']]
        self.assertEqual(statement('DEMO-NL-001',250000,rows),ORACLE)
        self.assertEqual(ORACLE['closing_balance_cents'],442206)

    def test_no_float_money(self):
        for opening,rows in [(1.2,[]),(1,[('T','2026-09-01','test',.1)]),(True,[])]:
            with self.assertRaises(ValueError):statement('A',opening,rows)

    def test_digest_detects_changed_transaction(self):
        changed=copy.deepcopy(ORACLE);changed['transactions'][0]['amount_cents']+=1
        self.assertNotEqual(digest(changed),digest(ORACLE))

    def test_digest_detects_missing_transaction(self):
        changed=copy.deepcopy(ORACLE);changed['transactions'].pop()
        self.assertNotEqual(digest(changed),digest(ORACLE))

    def test_canonical_document_order_not_relevant(self):
        self.assertEqual(digest(ORACLE),digest(dict(reversed(list(ORACLE.items())))))

    def test_valid_request_has_normalized_uuid(self):
        key=str(uuid.uuid4());self.assertEqual(request_fields({'period':'2026-09','idempotency_key':key}),('2026-09',key))

    def test_caller_cannot_select_another_account(self):
        with self.assertRaises(ValueError):request_fields({'period':'2026-09','idempotency_key':str(uuid.uuid4()),'account_id':'DEMO-NL-002'})

    def test_bad_period_or_key_refused(self):
        for value in [{},[],{'period':'2026-08','idempotency_key':str(uuid.uuid4())},{'period':'2026-09','idempotency_key':'not-a-uuid'},{'period':'2026-09','idempotency_key':True}]:
            with self.assertRaises(ValueError):request_fields(value)

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'ROLE':'api','API_TOKEN':'test-a','SECOND_API_TOKEN':'test-b'});self.env.start()
        self.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def tearDown(self):self.server.shutdown();self.server.server_close();self.env.stop()

    def get(self,path,token=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        c.request('GET',path,headers={} if token is None else {'Authorization':'Bearer '+token})
        r=c.getresponse();value=(r.status,json.loads(r.read()));c.close();return value

    def test_authentication_precedes_database_access(self):
        with patch.object(app,'connect') as connect:
            self.assertEqual(self.get('/statements')[0],401);connect.assert_not_called()

    def test_wrong_token_refused(self):
        self.assertEqual(self.get('/statements','invalid')[0],401)

    def test_account_scope_is_in_the_production_query(self):
        db=MagicMock();cursor=db.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value=None
        with patch.object(app,'connect',return_value=db):
            self.assertEqual(self.get('/statements/'+str(uuid.uuid4()),'test-b')[0],404)
        self.assertEqual(cursor.execute.call_args.args[1][1],'DEMO-NL-002')

    def test_monitor_listener_never_serves_financial_endpoints(self):
        old=self.server.server_port;self.server.server_port=8081
        try:
            with patch.object(app,'connect') as connect:
                # The actual socket remains the original port.
                c=http.client.HTTPConnection('127.0.0.1',old);c.request('GET','/statements',headers={'Authorization':'Bearer test-a'});r=c.getresponse();self.assertEqual(r.status,404);r.read();c.close();connect.assert_not_called()
        finally:self.server.server_port=old

    def test_legacy_hash_endpoint_removed(self):
        self.assertEqual(self.get('/jobs','test-a')[0],404)

    def test_tls_database_identity_verification_is_required(self):
        with patch.object(app.psycopg2,'connect') as connect,patch.dict(os.environ,{'DB_HOST':'db.invalid','DB_PASSWORD':'test'}):
            app.connect();self.assertEqual(connect.call_args.kwargs['sslmode'],'verify-full')
            self.assertEqual(connect.call_args.kwargs['user'],'bank_api')

if __name__=='__main__':unittest.main()
