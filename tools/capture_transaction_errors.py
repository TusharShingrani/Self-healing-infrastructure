"""Retain actual transaction diagnostics under a bounded concurrent workload."""
import concurrent.futures
import json
import urllib.error
import urllib.request
from pathlib import Path
from infrastructure import build


def request(_):
    try:r=urllib.request.urlopen('http://10.1.1.60:8088/healthz',timeout=5)
    except urllib.error.HTTPError as e:r=e
    with r:
        data=json.loads(r.read())
    return data


if __name__=='__main__':
    w,_,_=build();w.ownership()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(request,range(1200)))
    failed=[r for r in results if not r['healthy']]
    Path('evidence/infrastructure-concurrency-failures.json').write_text(json.dumps({'requests':len(results),'failed':failed},indent=2)+'\n')
    print(json.dumps({'requests':len(results),'failed':len(failed),'examples':failed[:4]},indent=2))
