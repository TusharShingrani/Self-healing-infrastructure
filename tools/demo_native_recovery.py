"""Controlled baseline: Kubernetes replaces ONE stateless worker Pod, healer paused.

This is a different fault from desired replicas=0. Do not compare their times
as a head-to-head algorithm benchmark. Run only in the owned synthetic lab.
"""
import argparse
import json
import shlex
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mapek.jobs import JobsWorld
from tools.expansion import transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controlled-experiment', action='store_true')
    args = parser.parse_args()
    if not args.controlled_experiment:
        parser.error('Use --controlled-experiment only for the owned synthetic lab')
    output = Path('evidence/jobs-native-pod-recovery.json')
    pause = Path('state/jobs/paused')
    if output.exists() or pause.exists():
        raise RuntimeError('Preserve existing evidence or operator pause')
    world = JobsWorld()
    before = world.observe(False)
    if not world.health(before):
        raise RuntimeError('Baseline must be healthy')
    workers = [pod for pod in world.kube.pods()
               if pod['metadata'].get('labels', {}).get('app') == 'job-worker'
               and pod['status']['phase'] == 'Running']
    if len(workers) != 2:
        raise RuntimeError('Exactly two running workers required before removing one')
    target = workers[0]['metadata']
    result = {'started': time.time(), 'target': target['name'], 'old_uid': target['uid'],
              'before': before, 'protocol': 'Kubernetes-only Pod replacement; MAPE-K observe-only'}
    pause.touch()
    try:
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            with urllib.request.urlopen('http://10.1.1.205:9109/status', timeout=3) as response:
                if json.load(response).get('paused') is True:
                    break
            time.sleep(1)
        else:
            raise RuntimeError('Observe-only mode not confirmed')
        world.ownership()
        started = time.time()
        ok, _, _ = transport('k8s-control')._probe(
            'sudo k3s kubectl -n jobs-lab delete pod '+shlex.quote(target['name'])+' --wait=false')
        if not ok:
            raise RuntimeError('Controlled Pod removal failed')
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            after = world.observe(False)
            running = [pod for pod in after.get('pods', [])
                       if pod['name'].startswith('job-worker-') and pod['phase'] == 'Running']
            if (world.health(after) and len(running) == 2
                    and all(pod['uid'] != target['uid'] for pod in running)
                    and after.get('client', {}).get('time', 0) >= started):
                result.update({'verified': True, 'seconds': time.time()-started, 'after': after})
                break
            time.sleep(2)
        else:
            raise RuntimeError('Native replacement/fresh job did not verify')
    except Exception as error:
        result.update({'verified': False, 'failure': type(error).__name__+': '+str(error)})
        raise
    finally:
        result['finished'] = time.time()
        output.write_text(json.dumps(result, indent=2)+'\n')
        pause.unlink(missing_ok=True)
    print(json.dumps({'native_recovery_verified': result['verified'], 'seconds': result['seconds']}))


if __name__ == '__main__':
    main()
