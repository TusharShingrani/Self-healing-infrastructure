"""Repeated real-provider replay study. No lab mutation; reports stay private.

Run with GEMINI_API_KEY in the environment, not a command-line argument.
The comparator and Gemini receive exactly the same sanitised evidence packet.
Manual grades are required; lexical matches are not a correctness oracle.
"""
import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from platform_healer.investigation import GeminiAdvisor,evidence_packet
from platform_healer.model import digest


def sample(metrics):
    return {'kind':'gateway_ports','identity':'replay-target','target':'gateway',
            'time':99,'supported':True,'error':'','metrics':metrics}


def make_cases():
    """Controlled, synthetic numeric cases matching the deployed metric contract."""
    base={'client_transaction_ok':False,'gateway_transaction_ok':False,
          'upstream_healthy':True,'backend_connect_errors':12,'gateway_5xx':12,
          'allocation_probe_errno':99,'memory_available_ratio':.5,
          'memory_available_bytes':1073741824,'reserved_conflict':False,
          'active_connections':32,'range_size':32,'used_ports':32,'time_wait':0}
    definitions=[
        ('port_exhaustion',{},'gateway_outbound_port_exhaustion'),
        ('upstream_outage',{'upstream_healthy':False,'allocation_probe_errno':0,'used_ports':8},'gateway_dependency_unavailable'),
        ('unsafe_headroom',{'memory_available_ratio':.05,'memory_available_bytes':67108864},'gateway_unsafe_headroom'),
        ('reserved_conflict',{'reserved_conflict':True},'gateway_reserved_port_conflict'),
        ('stale_evidence',{},'unknown'),
        ('unexplained_http_failure',{'allocation_probe_errno':0,'used_ports':8},'gateway_investigation_required'),
        ('recovered_old_counters',{'allocation_probe_errno':0,'used_ports':0,'active_connections':0,
                                   'client_transaction_ok':True,'gateway_transaction_ok':True},'healthy')]
    cases=[]
    for name,changes,expected in definitions:
        latest=dict(base,**changes)
        opening=dict(latest,backend_connect_errors=10,gateway_5xx=10)
        if name=='recovered_old_counters':opening=dict(base)
        current=sample(latest)
        if name=='stale_evidence':current['time']=50
        packet=evidence_packet({'before':json.dumps(sample(opening))},{'sample':current},now=100)
        cases.append({'id':name,'origin':'constructed contract case; not a new live fault',
                      'expected':expected,'packet':packet})
    return cases


def classify_packet(packet):
    """Read-only checklist baseline on the *same* allowlisted model input.

    Not the runtime authority: it cannot approve or generate an executable plan.
    """
    latest=packet.get('current',{})
    if latest.get('fresh') is not True or latest.get('telemetry_supported') is not True or latest.get('telemetry_error_present') is not False:
        return 'unknown'
    m=latest.get('metrics',{});old=packet.get('metrics',{})
    flags=('upstream_healthy','client_transaction_ok','gateway_transaction_ok','reserved_conflict')
    nums=('memory_available_ratio','memory_available_bytes','used_ports','range_size','allocation_probe_errno','backend_connect_errors','gateway_5xx')
    if any(type(m.get(k)) is not bool for k in flags) or any(type(m.get(k)) not in (int,float) for k in nums):return 'unknown'
    if not m['upstream_healthy']:return 'gateway_dependency_unavailable'
    if m['memory_available_bytes']<268435456 or m['memory_available_ratio']<.15:return 'gateway_unsafe_headroom'
    if m['reserved_conflict']:return 'gateway_reserved_port_conflict'
    if m['range_size']>0 and m['used_ports']/m['range_size']>=.85 and m['allocation_probe_errno']==99 and all(m[k]>old.get(k,m[k]) for k in ('backend_connect_errors','gateway_5xx')) and not m['client_transaction_ok'] and not m['gateway_transaction_ok']:
        return 'gateway_outbound_port_exhaustion'
    if not m['client_transaction_ok'] or not m['gateway_transaction_ok']:return 'gateway_investigation_required'
    return 'healthy'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',default='gemini-3.1-flash-lite')
    p.add_argument('--repetitions',type=int,default=3)
    p.add_argument('--spacing',type=float,default=4)
    args=p.parse_args()
    if not 3<=args.repetitions<=5 or not 1<=args.spacing<=60:raise ValueError('Bounded repeated study required')
    if args.output.resolve().is_relative_to(ROOT):raise ValueError('Detailed responses must be outside the repository')
    cases=make_cases();advisor=GeminiAdvisor(args.model)
    rubric=(ROOT/'docs/diagnosis-quality-protocol.md').read_bytes()
    study={'started':time.time(),'model':args.model,'repetitions':args.repetitions,
           'advisor_source_sha256':hashlib.sha256((ROOT/'src/platform_healer/investigation.py').read_bytes()).hexdigest(),
           'amendment_sha256':hashlib.sha256((ROOT/'docs/diagnosis-quality-amendment.md').read_bytes()).hexdigest(),
           'rubric_sha256':hashlib.sha256(rubric).hexdigest(),'cases':cases,'runs':[]}
    args.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    def save():
        tmp=args.output.with_suffix('.tmp');tmp.write_text(json.dumps(study,indent=2));tmp.chmod(0o600);tmp.replace(args.output)
    save()
    schedule=[(case,rep) for rep in range(args.repetitions) for case in cases]
    random.Random(20261018).shuffle(schedule)
    for case,rep in schedule:
        start=time.monotonic()
        row={'case':case['id'],'repetition':rep+1,'input_digest':digest(case['packet']),
             'baseline':classify_packet(case['packet'])}
        try:row['result']=advisor.investigate(case['packet']);row['available']=True
        except ValueError:row['available']=False
        row['latency_seconds']=round(time.monotonic()-start,3)
        study['runs'].append(row);save()
        print(len(study['runs']),len(schedule),case['id'],'valid' if row['available'] else 'unavailable',row['latency_seconds'],flush=True)
        if len(study['runs'])<len(schedule):time.sleep(args.spacing)
    study['finished']=time.time();save()
    valid=[r for r in study['runs'] if r['available']]
    print('Completed:',len(valid),'valid reports of',len(schedule),'attempts; manual correctness review still required.',flush=True)


if __name__=='__main__':main()
