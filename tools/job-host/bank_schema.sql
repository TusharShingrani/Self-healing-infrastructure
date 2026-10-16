-- Fictional statement projection, not a core banking or payment ledger.
CREATE TABLE IF NOT EXISTS bank_accounts(
 account_id text PRIMARY KEY, opening_balance_cents bigint NOT NULL,
 currency text NOT NULL DEFAULT 'EUR' CHECK(currency='EUR'));
CREATE TABLE IF NOT EXISTS bank_ledger(
 entry_id text PRIMARY KEY,account_id text NOT NULL REFERENCES bank_accounts,
 booked_on date NOT NULL CHECK(booked_on >= DATE '2026-09-01' AND booked_on < DATE '2026-10-01'),
 description text NOT NULL,amount_cents bigint NOT NULL CHECK(amount_cents <> 0));
INSERT INTO bank_accounts VALUES('DEMO-NL-001',250000,'EUR'),('DEMO-NL-002',100000,'EUR') ON CONFLICT DO NOTHING;
INSERT INTO bank_ledger VALUES
 ('T001','DEMO-NL-001','2026-09-01','Fictional salary',325000),
 ('T002','DEMO-NL-001','2026-09-02','Fictional rent',-120000),
 ('T003','DEMO-NL-001','2026-09-03','Fictional groceries',-6543),
 ('T004','DEMO-NL-001','2026-09-06','Fictional refund',2499),
 ('T005','DEMO-NL-001','2026-09-08','Fictional utilities',-8750),
 ('B001','DEMO-NL-002','2026-09-04','Other fictional customer',-1500)
 ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS statement_requests(
 id uuid PRIMARY KEY, account_id text NOT NULL REFERENCES bank_accounts,
 period text NOT NULL CHECK(period='2026-09'), idempotency_key uuid NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done')),
 document jsonb,document_hash text,created_at timestamptz NOT NULL DEFAULT now(),completed_at timestamptz,
 UNIQUE(account_id,idempotency_key),
 CHECK((status='pending' AND document IS NULL AND document_hash IS NULL AND completed_at IS NULL)
 OR (status='done' AND document IS NOT NULL AND document_hash ~ '^[a-f0-9]{64}$' AND completed_at IS NOT NULL)));
CREATE TABLE IF NOT EXISTS bank_audit(
 sequence bigserial PRIMARY KEY,at timestamptz NOT NULL DEFAULT clock_timestamp(),
 event text NOT NULL,request_id uuid NOT NULL,actor text NOT NULL);
CREATE OR REPLACE FUNCTION bank_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Immutable banking record'; END $$;
DROP TRIGGER IF EXISTS ledger_immutable ON bank_ledger;
CREATE TRIGGER ledger_immutable BEFORE UPDATE OR DELETE ON bank_ledger FOR EACH ROW EXECUTE FUNCTION bank_immutable();
DROP TRIGGER IF EXISTS accounts_immutable ON bank_accounts;
CREATE TRIGGER accounts_immutable BEFORE UPDATE OR DELETE ON bank_accounts FOR EACH ROW EXECUTE FUNCTION bank_immutable();
DROP TRIGGER IF EXISTS audit_immutable ON bank_audit;
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON bank_audit FOR EACH ROW EXECUTE FUNCTION bank_immutable();
CREATE OR REPLACE FUNCTION bank_request_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR OLD.status='done' OR NEW.account_id<>OLD.account_id OR NEW.id<>OLD.id
 OR NEW.period<>OLD.period OR NEW.idempotency_key<>OLD.idempotency_key OR NEW.created_at<>OLD.created_at
 OR NEW.status<>'done' THEN RAISE EXCEPTION 'Invalid statement transition'; END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS statement_guard ON statement_requests;
CREATE TRIGGER statement_guard BEFORE UPDATE OR DELETE ON statement_requests FOR EACH ROW EXECUTE FUNCTION bank_request_guard();
CREATE OR REPLACE FUNCTION bank_record_event() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN INSERT INTO public.bank_audit(event,request_id,actor) VALUES(
 CASE WHEN TG_OP='INSERT' THEN 'statement_accepted' ELSE 'statement_completed' END,NEW.id,session_user); RETURN NEW; END $$;
DROP TRIGGER IF EXISTS statement_audit ON statement_requests;
CREATE TRIGGER statement_audit AFTER INSERT OR UPDATE ON statement_requests FOR EACH ROW EXECUTE FUNCTION bank_record_event();
REVOKE ALL ON bank_accounts,bank_ledger,statement_requests,bank_audit FROM PUBLIC,bank_api,bank_worker;
GRANT SELECT ON bank_accounts,statement_requests TO bank_api;
GRANT INSERT(id,account_id,period,idempotency_key) ON statement_requests TO bank_api;
GRANT SELECT ON bank_accounts,bank_ledger,statement_requests TO bank_worker;
GRANT UPDATE(status,document,document_hash,completed_at) ON statement_requests TO bank_worker;
ALTER ROLE bank_api SET statement_timeout='5s';
ALTER ROLE bank_worker SET statement_timeout='5s';

-- The retired hashing role is optional on a fresh deployment.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='jobs_app') THEN
  REVOKE ALL ON bank_accounts,bank_ledger,statement_requests,bank_audit FROM jobs_app;
  ALTER ROLE jobs_app NOLOGIN;
 END IF;
END $$;
