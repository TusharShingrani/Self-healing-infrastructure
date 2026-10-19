"""Measured-state presentation regressions. No browser, credentials or lab effects."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from platform_healer.operator_ui import PAGE


@unittest.skipUnless(shutil.which('node'),'Node is required for operator view-model tests')
class OperatorViewTests(unittest.TestCase):
    def run_js(self,assertions):
        prelude='''const assert=require('node:assert/strict');
const {model,canApprove,qualification,observeDelta}=require(process.argv[1]);
function fixture(at=100,identity='current',extra={}){return {
 policies:{gateway:{mode:'reviewed'}},runtime:{loop_fresh:true},incidents:[],procedures:[],
 observations:{gateway:{cause:'healthy',sample:{target:'gateway',kind:'gateway_ports',identity,
 time:at,supported:true,error:'',metrics:{client_transaction_ok:true,gateway_transaction_ok:true,
 upstream_healthy:true,headroom_safe:true,reserved_conflict:false,active_connections:0,
 used_ports:2,range_size:32,memory_available_bytes:1073741824,memory_available_ratio:.5,
 backend_connect_errors:12,gateway_5xx:12,...extra}}}}}}
'''
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'view.js';source.write_text(PAGE.split('<script>')[1].split('</script>')[0],encoding='utf-8')
            result=subprocess.run(['node','-e',prelude+assertions,str(source)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_stale_missing_and_future_evidence_cannot_render_good_values(self):
        self.run_js("""for(const at of [50,150]){let v=model(fixture(at),100);assert.equal(v.fresh,false);assert.equal(v.client,null);assert.equal(v.used,null);assert.equal(canApprove(v),false)}
let s=fixture();delete s.observations.gateway.sample.metrics.used_ports;assert.equal(model(s,100).used,null);
s=fixture();s.observations.gateway.sample.error='observer missing';assert.equal(model(s,100).client,null);""")

    def test_approval_prechecks_fail_closed_for_unknown_or_unsafe_inputs(self):
        self.run_js("""assert.equal(canApprove(model(fixture(),100)),true);
for(const changes of [{upstream_healthy:false},{headroom_safe:false},{reserved_conflict:true},{active_connections:129},{active_connections:undefined}])assert.equal(canApprove(model(fixture(100,'current',changes),100)),false);
for(const mode of ['observe',undefined]){let s=fixture();s.policies.gateway.mode=mode;assert.equal(canApprove(model(s,100)),false)}
let s=fixture();s.runtime.loop_fresh=false;assert.equal(canApprove(model(s,100)),false);""")

    def test_counter_delta_requires_two_fresh_same_identity_readings(self):
        self.run_js("""assert.equal(observeDelta(model(fixture(),100)).backend,null);
assert.equal(observeDelta(model(fixture(103,'current',{backend_connect_errors:15}),103)).backend,3);
assert.equal(observeDelta(model(fixture(106,'current',{backend_connect_errors:1,gateway_5xx:1}),106)).backend,null);
assert.equal(observeDelta(model(fixture(109,'replacement'),109)).backend,null);
assert.equal(observeDelta(model(fixture(130,'replacement'),130)).backend,null);
assert.equal(observeDelta(model(fixture(100),150)).backend,null);""")

    def test_old_identity_does_not_qualify_the_current_gateway_in_the_view(self):
        self.run_js("""let s=fixture();s.incidents=[{id:1,status:'verified',scope:'old',before:JSON.stringify({target:'gateway',identity:'old'})},{id:2,status:'verified',scope:'current-scope',before:JSON.stringify({target:'gateway',identity:'current'})}];s.procedures=[{scope:'old',status:'validated'},{scope:'current-scope',status:'candidate'}];let v=model(s,100);assert.equal(v.procedures.length,1);assert.equal(v.procedures[0].status,'candidate');""")

    def test_only_verified_occurrences_after_last_failure_count_for_qualification(self):
        self.run_js("""const p={scope:'scope',cause:'fault',action:'action'};let s=fixture();s.incidents=[{...p,id:1,status:'verified'},{...p,id:2,status:'failed'},{...p,id:3,status:'verified'},{...p,id:4,status:'resolved'}];let q=qualification(s,p);assert.equal(q.total,2);assert.equal(q.success,1);assert.equal(q.failed,1);""")


if __name__=='__main__':unittest.main()
