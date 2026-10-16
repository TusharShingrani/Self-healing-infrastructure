"""Observe a quiet healthy banking interval; this is not a load/scale benchmark."""
import argparse,json,sqlite3,time,urllib.request
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--samples',type=int,choices=range(6,31),default=12);p.add_argument('--output',required=True);a=p.parse_args()
 dest=Path(a.output)
 if dest.exists():raise RuntimeError('Preserve prior baseline evidence')
 def count():
  with sqlite3.connect('file:state/jobs/operator.db?mode=ro',uri=True) as db:return db.execute('SELECT count(*) FROM cases').fetchone()[0]
 before=count();samples=[];previous=0;deadline=time.monotonic()+a.samples*25
 while len(samples)<a.samples and time.monotonic()<deadline:
  with urllib.request.urlopen('http://10.1.1.205:9109/status',timeout=5) as response:snapshot=json.load(response)
  obs=snapshot.get('observation',{});client=obs.get('client',{});stamp=client.get('time',0)
  if stamp>previous:
   checks=obs.get('infrastructure_checks',{})
   samples.append({'time':time.time(),'client_time':stamp,'seconds':client.get('seconds'),
    'healthy':not snapshot.get('paused',True) and time.time()-snapshot['time']<45 and time.time()-stamp<45 and client.get('healthy') is True and bool(checks) and all(v is True for v in checks.values())})
   previous=stamp
  time.sleep(3)
 result={'samples':samples,'cases_before':before,'cases_after':count(),'quiet_window_no_new_incidents':before==count(),
  'passed':len(samples)==a.samples and all(s['healthy'] for s in samples) and before==count()}
 dest.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'samples':len(samples),'healthy_samples':sum(s['healthy'] for s in samples),'no_new_incidents':result['quiet_window_no_new_incidents'],'passed':result['passed']}))
 if not result['passed']:raise RuntimeError('Quiet baseline not verified; inspect retained evidence')

if __name__=='__main__':main()
