"""Build one image, deploy bounded Kubernetes jobs and generate private credentials."""
import base64,hashlib,json,os,shlex,subprocess
from pathlib import Path
from expansion import transport,CONFIG,ROOT
from provision_expansion import put

NS=CONFIG['namespace']

def objects(image,secrets):
    objects=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,'labels':{'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'v1.36'}}},
             {'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'job-app','namespace':NS},'automountServiceAccountToken':False},
             {'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'healer','namespace':NS}},
             {'apiVersion':'v1','kind':'Secret','metadata':{'name':'job-credentials','namespace':NS},'type':'Opaque','stringData':{'DB_PASSWORD':secrets['db_api_password'],'API_TOKEN':secrets['api_token'],'SECOND_API_TOKEN':secrets['second_api_token']}},
             {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'job-settings','namespace':NS},'data':{'DB_HOST':CONFIG['desired_db_host']}},
             {'apiVersion':'v1','kind':'ResourceQuota','metadata':{'name':'job-budget','namespace':NS},'spec':{'hard':{'pods':'12','requests.cpu':'2','requests.memory':'1Gi','limits.cpu':'4','limits.memory':'2Gi'}}}]
    objects += [{'apiVersion':'v1','kind':'Secret','metadata':{'name':'bank-worker-credentials','namespace':NS},'type':'Opaque','stringData':{'DB_PASSWORD':secrets['db_worker_password']}},
                {'apiVersion':'v1','kind':'Secret','metadata':{'name':'statement-tls','namespace':NS},'type':'kubernetes.io/tls','stringData':{'tls.crt':secrets['api_cert'],'tls.key':secrets['api_key']}}]
    for role in ('api','worker','policy-witness'):
        label={'app':'job-'+role}
        container={'name':'job-'+role,'image':image,'imagePullPolicy':'Never','ports':[{'containerPort':8080},{'containerPort':8081}],
                   'env':[{'name':'ROLE','value':role}],'envFrom':[{'configMapRef':{'name':'job-settings'}},{'secretRef':{'name':'job-credentials'}}],
                   'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                   'resources':{'requests':{'cpu':'100m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'128Mi'}},
                   'livenessProbe':{'httpGet':{'path':'/livez','port':8081},'initialDelaySeconds':5,'periodSeconds':10},
                   'readinessProbe':{'httpGet':{'path':'/readyz','port':8081},'initialDelaySeconds':2,'periodSeconds':5}}
        container['volumeMounts']=[{'name':'statement-tls','mountPath':'/run/statement-tls','readOnly':True}]
        if role=='worker':container['envFrom']=[{'configMapRef':{'name':'job-settings'}},{'secretRef':{'name':'bank-worker-credentials'}}]
        if role=='policy-witness':
            container['volumeMounts']=[]
            container['command']=['python','/app/policy_witness.py']
            container['envFrom']=[]
            container['livenessProbe']['httpGet']={'path':'/status','port':8080}
            container['readinessProbe']['httpGet']={'path':'/status','port':8080}
        objects.append({'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'job-'+role,'namespace':NS},
                        'spec':{'replicas':1 if role=='policy-witness' else 2,'selector':{'matchLabels':label},'strategy':{'type':'RollingUpdate','rollingUpdate':{'maxSurge':1,'maxUnavailable':0}},
                                'template':{'metadata':{'labels':label},'spec':{'serviceAccountName':'job-app','automountServiceAccountToken':False,
                                           'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'fsGroup':10001,'seccompProfile':{'type':'RuntimeDefault'}},
                                           'affinity':{'podAntiAffinity':{'preferredDuringSchedulingIgnoredDuringExecution':[{'weight':100,'podAffinityTerm':{'labelSelector':{'matchLabels':label},'topologyKey':'kubernetes.io/hostname'}}]}},
                                           'volumes':[{'name':'statement-tls','secret':{'secretName':'statement-tls','defaultMode':0o440}}],'containers':[container]}}}})
        objects.append({'apiVersion':'policy/v1','kind':'PodDisruptionBudget','metadata':{'name':'job-'+role,'namespace':NS},'spec':{'minAvailable':1,'selector':{'matchLabels':label}}})
        objects.append({'apiVersion':'v1','kind':'Service','metadata':{'name':'job-'+role,'namespace':NS},
                        'spec':dict({'selector':label,'ports':[dict({'port':8080,'targetPort':8080},**({'nodePort':30081 if role=='policy-witness' else 30080} if role!='worker' else {}))]},**({'type':'NodePort'} if role!='worker' else {}))})
    # No DNS or Internet egress is needed by these Pods: DB_HOST is a literal IP.
    objects += [
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'job-default-deny','namespace':NS},'spec':{'podSelector':{},'policyTypes':['Ingress','Egress']}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'job-api-ingress','namespace':NS},'spec':{'podSelector':{'matchLabels':{'app':'job-api'}},'policyTypes':['Ingress'],'ingress':[{'from':[{'ipBlock':{'cidr':'10.1.1.0/24'}},{'ipBlock':{'cidr':CONFIG['control_forwarding_source']}}],'ports':[{'protocol':'TCP','port':8080},{'protocol':'TCP','port':8081}]}]}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'job-metrics-ingress','namespace':NS},'spec':{'podSelector':{},'policyTypes':['Ingress'],'ingress':[{'from':[{'ipBlock':{'cidr':'10.1.1.50/32'}},{'ipBlock':{'cidr':CONFIG['control_forwarding_source']}}],'ports':[{'protocol':'TCP','port':8080},{'protocol':'TCP','port':8081}]}]}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'job-witness-ingress','namespace':NS},'spec':{'podSelector':{'matchLabels':{'app':'job-policy-witness'}},'policyTypes':['Ingress'],'ingress':[{'from':[{'ipBlock':{'cidr':'10.1.1.0/24'}},{'ipBlock':{'cidr':CONFIG['control_forwarding_source']}}],'ports':[{'protocol':'TCP','port':8080},{'protocol':'TCP','port':8081}]}]}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'job-database-egress','namespace':NS},'spec':{'podSelector':{},'policyTypes':['Egress'],'egress':[{'to':[{'ipBlock':{'cidr':'10.1.1.83/32'}}],'ports':[{'protocol':'TCP','port':5432}]}]}},
        {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'Role','metadata':{'name':'healer-bounded','namespace':NS},'rules':[
          {'apiGroups':['apps'],'resources':['deployments'],'resourceNames':['job-api','job-worker','job-policy-witness'],'verbs':['get','patch']},
          {'apiGroups':[''],'resources':['pods','events'],'verbs':['get','list']},
          {'apiGroups':[''],'resources':['pods/proxy'],'verbs':['get']},
          {'apiGroups':['metrics.k8s.io'],'resources':['pods'],'verbs':['get','list']},
          {'apiGroups':[''],'resources':['configmaps'],'resourceNames':['job-settings'],'verbs':['get','patch']},
          {'apiGroups':['networking.k8s.io'],'resources':['networkpolicies'],'verbs':['get','list']},
          {'apiGroups':['networking.k8s.io'],'resources':['networkpolicies'],'resourceNames':['job-default-deny','job-api-ingress','job-metrics-ingress','job-witness-ingress','job-database-egress'],'verbs':['patch']}]},
        {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'RoleBinding','metadata':{'name':'healer-bounded','namespace':NS},'subjects':[{'kind':'ServiceAccount','name':'healer','namespace':NS}],'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'healer-bounded'}},
        {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'ClusterRole','metadata':{'name':'healer-lab-observer'},'rules':[
          {'apiGroups':[''],'resources':['nodes'],'resourceNames':['k8s-control','k8s-worker-1','k8s-worker-2'],'verbs':['get']},
          {'apiGroups':[''],'resources':['namespaces'],'resourceNames':['jobs-lab'],'verbs':['get']},
          {'nonResourceURLs':['/metrics'],'verbs':['get']}]},
        {'apiVersion':'rbac.authorization.k8s.io/v1','kind':'ClusterRoleBinding','metadata':{'name':'healer-lab-observer'},'subjects':[{'kind':'ServiceAccount','name':'healer','namespace':NS}],'roleRef':{'apiGroup':'rbac.authorization.k8s.io','kind':'ClusterRole','name':'healer-lab-observer'}}]
    return objects

def main():
    builder=transport('k8s-worker-1');builder._ssh.timeout=900
    db=transport('db-1');ok,ca,_=db._probe('sudo cat /etc/healer-bank/pki/ca.crt')
    if not ok:raise RuntimeError('Bank CA unavailable; run prepare_bank.py first')
    image_files=('app.py','banking.py','policy_witness.py','Dockerfile')
    source=hashlib.sha256(b''.join((ROOT/'tools/job-host'/name).read_bytes() for name in image_files)+ca.encode()).hexdigest()
    put(builder,'/home/ubuntu/job-lab/tools/job-host/bank-ca.crt',ca.encode())
    for name in image_files:
        put(builder,'/home/ubuntu/job-lab/tools/job-host/'+name,(ROOT/'tools/job-host'/name).read_bytes())
    image='selfheal/jobs:'+source[:16]
    command='cd /home/ubuntu/job-lab/tools/job-host && sudo docker pull python:3.12-slim >/dev/null && BASE=$(sudo docker image inspect python:3.12-slim --format "{{index .RepoDigests 0}}") && sed "s|^FROM .*|FROM $BASE|" Dockerfile | sudo tee Dockerfile.pinned >/dev/null && sudo docker build -f Dockerfile.pinned -t '+image+' . >/home/ubuntu/job-build.log 2>&1 && sudo docker save '+image+' -o /home/ubuntu/jobs-image.tar && sudo chmod 644 /home/ubuntu/jobs-image.tar && echo "$BASE"'
    ok,base,err=builder._probe('bash -o pipefail -c '+shlex.quote(command))
    if not ok:raise RuntimeError('Image build failed; inspect private node build log: '+err[:200])
    key=os.environ['LAB_SSH_KEY'];tmp='/tmp/selfheal-jobs-image.tar'
    def copy(source,destination):
        for ip in ('10.1.1.81','10.1.1.82'):transport('k8s-worker-1' if ip.endswith('81') else 'k8s-worker-2')
        host='10.1.1.81' if source.startswith('ubuntu@') else '10.1.1.82'
        args=['scp','-q','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(Path.home()/'.ssh/healer-lab-known-hosts'/host),'-i',key,'-o','IdentitiesOnly=yes',source,destination]
        subprocess.run(args,check=True,timeout=180)
    copy('ubuntu@10.1.1.81:/home/ubuntu/jobs-image.tar',tmp)
    copy(tmp,'ubuntu@10.1.1.82:/tmp/selfheal-jobs-image.tar')
    for name,path in (('k8s-worker-1','/home/ubuntu/jobs-image.tar'),('k8s-worker-2',tmp)):
        node=transport(name);node._ssh.timeout=120
        ok,_,err=node._probe('sudo k3s ctr images import '+shlex.quote(path))
        if not ok:raise RuntimeError('Image import failed: '+name)
    os.unlink(tmp)
    db=transport('db-1');ok,raw,_=db._probe('sudo cat /etc/healer-jobs/secrets.json')
    if not ok:raise RuntimeError('Private credentials unavailable')
    secrets=json.loads(raw)
    for name,file in [('api_cert','api.crt'),('api_key','api.key')]:
        ok,secret_value,_=db._probe('sudo cat /etc/healer-bank/pki/'+file)
        if not ok:raise RuntimeError('Private bank TLS material unavailable')
        secrets[name]=secret_value
    control=transport('k8s-control');control._ssh.timeout=300
    ok,raw,_=control._probe('ip -j -4 address show flannel.1')
    if CONFIG['control_forwarding_source']!='10.42.0.0/32' or not ok or not any(a.get('local')=='10.42.0.0' and a.get('prefixlen')==32 for interface in json.loads(raw) for a in interface.get('addr_info',[])):
        raise RuntimeError('Single-address control forwarding source unproven')
    manifest={'apiVersion':'v1','kind':'List','items':objects(image,secrets)}
    put(control,'/etc/healer-jobs/workload-private.json',json.dumps(manifest).encode(),True)
    ok,out,err=control._probe('sudo k3s kubectl apply -f /etc/healer-jobs/workload-private.json && sudo k3s kubectl -n jobs-lab rollout status deployment/job-api --timeout=180s && sudo k3s kubectl -n jobs-lab rollout status deployment/job-worker --timeout=180s')
    print(out,err,flush=True)
    if not ok:raise RuntimeError('Workload did not become ready')
    ok,token,_=control._probe('sudo k3s kubectl -n jobs-lab create token healer --duration=720h')
    if not ok:raise RuntimeError('Scoped healer credential unavailable')
    ok,ca,_=control._probe("sudo k3s kubectl config view --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}'")
    if not ok:raise RuntimeError('TLS trust anchor unavailable')
    ok,ca_bank,_=db._probe('sudo cat /etc/healer-bank/pki/ca.crt')
    if not ok:raise RuntimeError('Bank CA unavailable')
    private=Path.home()/'.config/healer-jobs';private.mkdir(mode=0o700,exist_ok=True)
    for name,data in (('kube.json',{'url':'https://10.1.1.80:6443','token':token.strip(),'ca':ca}),('client.json',{'url':CONFIG['api_url'],'token':secrets['api_token'],'ca':base64.b64encode(ca_bank.encode()).decode()})):
        path=private/name;path.write_text(json.dumps(data));path.chmod(0o600)
    reference=[o for o in manifest['items'] if o['kind'] in ('Deployment','ConfigMap','NetworkPolicy')]
    # Public references have no secret values; Secrets and their last-applied data are excluded.
    (ROOT/'config/jobs-reference.json').write_text(json.dumps(reference,indent=2)+'\n')
    (ROOT/'config/jobs-image.json').write_text(json.dumps({'image':image,'source_sha256':source,'base_image':base.strip()},indent=2)+'\n')
    print('Image, scoped API client and public repair references prepared',flush=True)

if __name__=='__main__':main()
