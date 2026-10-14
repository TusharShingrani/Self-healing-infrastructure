"""One additional automatic recurrence proving owner/mode verification live."""
import json
import subprocess
import time
from pathlib import Path
from infrastructure import build,inject


if __name__=='__main__':
    subprocess.run(['systemctl','--user','stop','healer-infrastructure'],check=True)
    w,o,h=build()
    try:
        if not w.health(w.observe(False)):raise RuntimeError('Unhealthy baseline')
        start=time.time();before=inject(w,'permissions');h.tick()
        case=o.cases()[0]
        after=json.loads(case['after_evidence'] or '{}')
        if case['status']!='verified' or not case['procedure_id'] or after.get('recipe_checks',{}).get('recipe_checkpoint_permissions',{}).get('least_privilege_permissions') is not True:
            raise RuntimeError('Automatic least-privilege recurrence did not verify')
        Path('evidence/infrastructure-permission-recurrence.json').write_text(json.dumps({'started':start,'seconds':time.time()-start,'before':before,'case':case},indent=2)+'\n')
        print('Automatic permissions repair verified, including exact owner/group and mode 0640')
    finally:
        w.run_recipe('checkpoint_permissions')
        subprocess.run(['systemctl','--user','start','healer-infrastructure'],check=True)
