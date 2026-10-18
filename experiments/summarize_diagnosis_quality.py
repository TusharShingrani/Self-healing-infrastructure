"""Export aggregate grades only; never copy model reports into the repository."""
import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from diagnosis_quality import make_cases,classify_packet

FLAGS=('interpretation_correct','unsupported_claim','useful_checks','unsafe_advice',
       'command_violation','limitations_acknowledged')


def report_hash(report):
    return hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()


def summarise(study,review):
    if review['rubric_sha256']!=study['rubric_sha256']:raise ValueError('Review protocol mismatch')
    expected={case['id']:case for case in make_cases()}
    if {c['id'] for c in study['cases']}!=set(expected):raise ValueError('Unexpected case corpus')
    output={'model':study['model'],'attempts':len(study['runs']),
            'valid_reports':sum(row['available'] for row in study['runs']),
            'rubric_sha256':study['rubric_sha256'],'cases':[]}
    grades=[]
    for name,case in expected.items():
        rows=[row for row in study['runs'] if row['case']==name]
        if len(rows)!=study['repetitions']:raise ValueError('Missing repetitions')
        grade=review['cases'][name]
        if any(type(grade.get(flag)) is not bool for flag in FLAGS):raise ValueError('Explicit manual grades required')
        valid=[r for r in rows if r['available']]
        for row in valid:
            if row['result']['evidence_digest']!=row['input_digest']:raise ValueError('Evidence digest mismatch')
            if report_hash(row['result']['report'])!=grade['reviewed_report_sha256']:raise ValueError('Unreviewed response variation')
        grades.extend([grade]*len(valid))
        output['cases'].append({'case':name,'expected':case['expected'],'attempts':len(rows),
            'valid_reports':len(valid),'distinct_reports':len({report_hash(r['result']['report']) for r in valid}),
            'input_digest':rows[0]['input_digest'],
            'baseline_correct':sum(r['baseline']==case['expected'] for r in rows),
            'grades':{flag:sum(grade[flag] for _ in valid) for flag in FLAGS},
            'review_note':grade['reason'],'borderline_judgment':grade.get('borderline',False),
            'technical_caveat':grade.get('technical_caveat',False)})
    output['grades']={flag:sum(g[flag] for g in grades) for flag in FLAGS}
    output['median_provider_latency_seconds']=round(statistics.median(r['latency_seconds'] for r in study['runs']),3)
    output['min_provider_latency_seconds']=min(r['latency_seconds'] for r in study['runs'])
    output['max_provider_latency_seconds']=max(r['latency_seconds'] for r in study['runs'])
    output['baseline_correct']=sum(c['baseline_correct'] for c in output['cases'])
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--original-review',type=Path,required=True)
    parser.add_argument('--revised',type=Path,required=True)
    parser.add_argument('--revised-review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    first=json.loads(args.original.read_text());second=json.loads(args.revised.read_text())
    if first['cases']!=second['cases'] or first['rubric_sha256']!=second['rubric_sha256']:
        raise ValueError('Comparisons must retain identical cases and rubric')
    output={'date':'2026-10-18','design':'Seven constructed contract cases, three calls each, original and refined guidance; same model and evidence. In-sample retention, not held-out validation.',
            'reviewer':'Implementing assistant; one non-independent evaluator; full distinct reports read and repeated hashes verified.',
            'original':summarise(first,json.loads(args.original_review.read_text())),
            'revised':summarise(second,json.loads(args.revised_review.read_text())),
            'limits':['Synthetic numeric cases, not fresh live fault injection or unseen root causes',
                      'Identical per-case responses across repetitions do not provide independent fault diversity',
                      'Prompt revised after seeing original failures; improvement is in-sample',
                      'Strict full-report grades include safety/temporal consistency, not just top diagnosis',
                      'Borderline recovered/stale wording judgments are explicitly identified',
                      'No independent second reviewer, measured human time, production accuracy or cost guarantee']}
    durations=[]
    for _ in range(10):
        start=time.perf_counter_ns()
        for _ in range(1000):
            for case in make_cases_cached:classify_packet(case['packet'])
        durations.append((time.perf_counter_ns()-start)/7000/1000)
    output['baseline_median_microseconds_per_packet']=round(statistics.median(durations),3)
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print('Aggregate-only report written; detailed responses not exported.')


make_cases_cached=make_cases()
if __name__=='__main__':main()
