"""A dependency-aware managed element and investigated, typed repair recipes.

Recipes compose bounded operations on explicitly named lab resources. They
cannot supply commands, addresses, paths, arbitrary service names or secrets.
New compositions need no Python change; new capabilities still need review.
"""
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from .actions import CATALOGUE
from .educloud import EduCloudWorld, ProtectedTarget
from .operator import Operator, encode
from .stages import Diagnosis

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAIRS = {('restore_reference', 'dns'), ('restore_cache_budget', 'cache'),
         ('restore_permissions', 'checkpoint'), ('start_service', 'cache')}
CHECKS = {'dns_record', 'cache_write', 'cache_budget', 'spool_write', 'cache_service', 'endpoint'}
REDIS = 'REDISCLI_AUTH=$(sudo cat /etc/healer-stack/cache-admin-password) redis-cli -p 6380'


class RecipeBook:
    def __init__(self, specs):
        self.recipes = {}
        for spec in specs:
            if set(spec) != {'id', 'operations', 'verify'} or not re.fullmatch(r'[a-z][a-z0-9_]{0,40}', spec['id']):
                raise ValueError('Invalid recipe schema or id')
            if spec['id'] in self.recipes or not 1 <= len(spec['operations']) <= 4:
                raise ValueError('Duplicate recipe or unbounded operation count')
            for step in spec['operations']:
                if set(step) != {'op', 'resource'} or (step['op'], step['resource']) not in PAIRS:
                    raise ValueError('Operation is outside the lab capability allowlist')
            if not isinstance(spec['verify'], list) or not spec['verify'] or not set(spec['verify']) <= CHECKS or 'endpoint' not in spec['verify']:
                raise ValueError('Independent endpoint verification is required')
            required = {('restore_reference','dns'):'dns_record', ('restore_cache_budget','cache'):'cache_budget',
                        ('restore_permissions','checkpoint'):'spool_write', ('start_service','cache'):'cache_service'}
            if any(required[(s['op'],s['resource'])] not in spec['verify'] for s in spec['operations']):
                raise ValueError('Each operation needs its cause-specific verification')
            self.recipes[spec['id']] = spec
        self.digest = hashlib.sha256(encode(specs).encode()).hexdigest()

    @classmethod
    def load(cls, path=None):
        with open(path or os.path.join(ROOT, 'config/repair-recipes.json')) as handle:
            return cls(json.load(handle))

    def register(self):
        for name in self.recipes:
            CATALOGUE['recipe_'+name] = lambda world, name=name: world.run_recipe(name)


class InfrastructureWorld:
    """Uses the existing CloudStack ownership and pinned SSH transport.

app-1 hosts the synthetic transaction; app-2 hosts dedicated DNS and Redis.
No network firewall or operating system DNS settings are modified.
"""
    def __init__(self, cs, lab, key_path=None, recipes=None):
        if any(lab.get('addresses', {}).get(name) != address for name, address in
               (('app-1', '10.1.1.60'), ('app-2', '10.1.1.61'))):
            raise ProtectedTarget('This bounded capability book requires the documented fixed lab topology')
        self.lab, self.name = lab, 'app-1'
        self.service = 'healer-stack-transaction'
        self.config_path = '/etc/healer-stack/dns.conf'
        self.reference_dir = '/opt/healer-stack/reference'
        self.log_mount = self.log_image = None
        self.nodes = {n: EduCloudWorld(cs, n, lab, key_path=key_path) for n in ('app-1', 'app-2')}
        self.recipes = recipes or RecipeBook.load(); self.recipes.register()
        self._vm = None
        self._trusted = False
        self.tick_count = self.downtime_ticks = 0
        self.last_action_at = 0
        self.latest = {}

    def ownership(self):
        self._trusted = False
        for name, node in self.nodes.items():
            vm = node._assert_destructive_allowed()
            address = node.cs.ip_of(vm)
            if address != self.lab.get('addresses', {}).get(name) or not vm.get('templateid'):
                raise ProtectedTarget('Unexpected address or missing template identity')
            if not node._ssh or not node._ssh.reachable():
                raise ProtectedTarget('Pinned SSH transport cannot be established')
        self._vm = self.nodes['app-1']._vm
        self._trusted = True

    def command(self, node, command):
        if not getattr(self, '_trusted', False):
            return False, '', 'Composite lab ownership and transport are unproven'
        return self.nodes[node]._probe(command)

    def observe(self, sample=True):
        obs = {'tick':self.tick_count, 'reachable': False, 'service_running': None, 'config_correct': True,
               'http_ok': None, 'probe_error': '', 'monitor_source': 'direct-dependency-transaction',
               'infrastructure_checks': {}, 'disk_percent': None, 'disk_growth': None}
        try:
            self.ownership(); obs['reachable'] = True
            ok, out, err = self.command('app-1', 'systemctl is-active healer-stack-transaction')
            obs['service_running'] = True if out == 'active' else False if out in ('inactive','failed') else None
            ok, out, err = self.command('app-2', 'systemctl is-active healer-stack-redis')
            cache_service = True if out == 'active' else False if out in ('inactive','failed') else None
            obs['infrastructure_checks']['cache_service'] = cache_service
            if cache_service:
                ok, out, err = self.command('app-2', REDIS+' --raw CONFIG GET maxmemory')
                parts = out.splitlines()
                obs['infrastructure_checks']['cache_budget'] = (parts == ['maxmemory','67108864']) if ok and len(parts)==2 else None
                if obs['infrastructure_checks']['cache_budget'] is None:
                    obs['probe_error'] = 'Unreadable independent cache budget probe'
            else:
                obs['infrastructure_checks']['cache_budget'] = None
            try:
                response = urllib.request.urlopen('http://10.1.1.60:8088/healthz', timeout=4)
            except urllib.error.HTTPError as error:
                response = error  # A 503 contains useful dependency evidence.
            with response:
                data = json.loads(response.read(16384))
            expected = {'dns_record','cache_write','spool_write'}
            if not isinstance(data, dict) or not isinstance(data.get('checks'), dict) or not expected <= set(data['checks']) or any(data['checks'][k] is not None and type(data['checks'][k]) is not bool for k in expected):
                raise ValueError('Invalid transaction check payload')
            obs['infrastructure_checks'].update({k:data['checks'][k] for k in expected})
            obs['http_ok'] = response.code == 200 and data.get('healthy') is True and all(data['checks'][k] is True for k in expected)
            obs['transaction'] = data
            if obs['service_running'] is None or cache_service is None:
                obs['probe_error'] = (obs['probe_error'] + '; Unreadable systemd state').lstrip('; ')
        except (OSError, ValueError, RuntimeError) as error:
            obs['probe_error'] = f'{type(error).__name__}: {error}'[:500]
        self.latest = obs
        return obs

    def health(self, obs=None):
        obs = self.observe(False) if obs is None else obs
        return (not obs.get('probe_error') and all(obs.get(k) is True for k in
                ('reachable','service_running','config_correct','http_ok')) and
                all(obs.get('infrastructure_checks', {}).get(k) is True for k in CHECKS-{'endpoint'}))

    def step(self):
        self.tick_count += 1

    def note_health(self, healthy):
        if not healthy:
            self.downtime_ticks += 1

    def repair_identity(self):
        # Both VM identities, deployed reference bytes and recipe version enter
        # the scope. Replacing either VM or editing a recipe requires revalidation.
        refs = []
        for node, command in [('app-1','sha256sum /opt/healer-stack/transaction.py'),
                              ('app-2','sha256sum /opt/healer-stack/reference/dns.conf /opt/healer-stack/reference/redis.conf')]:
            ok, out, _ = self.command(node, command)
            hashes = [line.split()[0] for line in out.splitlines()]
            if not ok or any(not re.fullmatch('[0-9a-f]{64}', h) for h in hashes) or len(hashes) != (1 if node=='app-1' else 2):
                return {'references': None, 'live_config': None}
            refs.extend(hashes)
        refs += [self.recipes.digest, encode({n:[w._vm.get('id'),w._vm.get('templateid')] for n,w in self.nodes.items()})]
        checks = self.latest.get('infrastructure_checks', {})
        ok, live, _ = self.command('app-2', 'sha256sum /etc/healer-stack/dns.conf')
        return {'references': refs, 'live_config': hashlib.sha256(encode([checks,live if ok else None]).encode()).hexdigest()}

    def diagnostic_evidence(self):
        evidence = {'topology': {'transaction':'app-1:8088','dns':'app-2:1053','cache':'app-2:6380',
                               'checkpoint':'app-1:/var/lib/healer-stack/checkpoint'},
                    'transaction':self.latest.get('transaction'), 'checks':self.latest.get('infrastructure_checks')}
        for node, cmd in [('app-1','sudo stat -c "%a %U %n" /var/lib/healer-stack/checkpoint; systemctl show healer-stack-transaction -p ActiveState -p MemoryCurrent -p CPUUsageNSec'),
                          ('app-2','systemctl show healer-stack-redis healer-stack-dns -p ActiveState -p MemoryCurrent -p CPUUsageNSec; cat /etc/healer-stack/dns.conf; '+REDIS+' --raw CONFIG GET maxmemory')]:
            ok, out, err = self.command(node, cmd)
            evidence[node] = {'command_success':ok,'stdout':out[:4000],'stderr':err[:1000]}
        return evidence

    def run_recipe(self, name):
        self.ownership()  # Positive proof for BOTH targets immediately before effects.
        spec = self.recipes.recipes[name]
        operations = {
            ('restore_reference','dns'):('app-2','sudo cp /opt/healer-stack/reference/dns.conf /etc/healer-stack/dns.conf && sudo dnsmasq --test --conf-file=/etc/healer-stack/dns.conf && sudo systemctl restart healer-stack-dns'),
            ('restore_cache_budget','cache'):('app-2','test "$('+REDIS+' CONFIG SET maxmemory 67108864)" = OK'),
            ('restore_permissions','checkpoint'):('app-1','test ! -L /var/lib/healer-stack/checkpoint && sudo chown healer-stack:healer-stack /var/lib/healer-stack/checkpoint && sudo chmod 640 /var/lib/healer-stack/checkpoint'),
            ('start_service','cache'):('app-2','sudo systemctl start healer-stack-redis'),
        }
        self.last_action_at = time.time()
        for step in spec['operations']:
            node, cmd = operations[(step['op'],step['resource'])]
            ok, _, err = self.command(node, cmd)
            if not ok:
                return False, err or 'Bounded operation failed'
        ok, checks = self.recipe_verified(name)
        return ok, encode(checks)

    def recipe_verified(self, name):
        obs = self.observe(False)
        checks = dict(obs['infrastructure_checks'], endpoint=self.health(obs))
        spec = self.recipes.recipes[name]
        wanted = list(spec['verify'])
        if any(step['op']=='restore_permissions' for step in spec['operations']):
            ok, mode, _ = self.command('app-1','sudo stat -c "%a %U %G" /var/lib/healer-stack/checkpoint')
            checks['least_privilege_permissions'] = ok and mode=='640 healer-stack healer-stack'
            wanted.append('least_privilege_permissions')
        return all(checks.get(k) is True for k in wanted), {k:checks.get(k) for k in wanted}

    def reboot_instance(self):
        raise ProtectedTarget('Platform repairs are excluded from the multi-host transaction')

    rebuild_instance = reboot_instance


class InvestigationOperator(Operator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db.execute('CREATE TABLE IF NOT EXISTS investigations(scope TEXT,symptoms TEXT,cause TEXT,actions TEXT,who TEXT,notes TEXT,UNIQUE(scope,symptoms))')

    def record_human(self, world, case_id, actions, who, notes):
        if any(not a.startswith('recipe_') or a[7:] not in world.recipes.recipes for a in actions):
            raise ValueError('Human infrastructure repairs must use this stack capability book')
        return super().record_human(world, case_id, actions, who, notes)

    def investigate(self, world, case_id, cause, actions, who, notes):
        case = self.case(case_id)
        if case['status'] != 'pending' or case['cause'] != 'unknown' or not who.strip() or not notes.strip() or not re.fullmatch('[a-z][a-z0-9_]{2,80}', cause) or cause == 'unknown':
            raise ValueError('Pending unknown incident, meaningful diagnosis and investigator required')
        if not actions or any(not a.startswith('recipe_') or a[7:] not in world.recipes.recipes for a in actions):
            raise ValueError('Only reviewed typed recipes may be bound to an investigation')
        obs = world.observe(False)
        from .stages import Monitor
        symptoms = Monitor().symptoms(obs)
        identity, scope = self.context(world, symptoms, 'unknown', [], obs)
        if identity != case['identity']:
            raise ValueError('Evidence changed during investigation; open the current incident')
        from .operator import redact
        self.db.execute('INSERT OR REPLACE INTO investigations VALUES(?,?,?,?,?,?)',
                        (scope, case['symptoms'], cause, encode(actions), who, redact(notes)))
        self.db.execute("UPDATE cases SET status='investigated' WHERE id=?", (case_id,))
        self.db.commit(); self.audit(f'incident:{case_id}',who,'investigate',notes)
        return self.capture(world, symptoms, cause, actions, obs)

    def verify(self, world, actions):
        ok, after = super().verify(world, actions)
        for action in actions:
            if action.startswith('recipe_'):
                passed, checks = world.recipe_verified(action[7:])
                after['checks'][action] = passed
                after.setdefault('recipe_checks', {})[action] = checks
                ok = ok and passed
        return ok, after


class InvestigatedAnalyser:
    def __init__(self, world, operator):
        self.world, self.operator = world, operator

    def analyse(self, symptoms, knowledge=None):
        _, scope = self.operator.context(self.world, symptoms, 'unknown', [], self.world.latest)
        row = self.operator.db.execute('SELECT * FROM investigations WHERE scope=? AND symptoms=?', (scope,encode(sorted(symptoms)))).fetchone()
        if row:
            return Diagnosis(row['cause'], 1.0, list(symptoms), 'investigation', json.loads(row['actions']))
        return Diagnosis('unknown', 0.0, list(symptoms))
