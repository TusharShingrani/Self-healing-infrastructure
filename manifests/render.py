"""Render public, secret-free lab manifests. No Kubernetes write permissions needed."""
import json,sys


def objects(image):
    agent_ns='platform-healer-system';controller_ns='platform-healer'
    result=[]
    for namespace,level in ((agent_ns,'privileged'),(controller_ns,'restricted')):
        result.append({'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace,'labels':{
            'pod-security.kubernetes.io/enforce':level,'pod-security.kubernetes.io/enforce-version':'v1.36'}}})
        result.append({'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':'platform-healer','namespace':namespace},'automountServiceAccountToken':False})
        result.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'default-deny','namespace':namespace},'spec':{'podSelector':{},'policyTypes':['Ingress','Egress']}})
    security={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
    container={'name':'agent','image':image,'imagePullPolicy':'Never','command':['python','-m','platform_healer.agent'],
        'securityContext':security,'ports':[{'containerPort':9119}],
        'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'250m','memory':'96Mi'}},
        'volumeMounts':[{'name':'broker','mountPath':'/run/platform-healer','readOnly':True}],
        'readinessProbe':{'httpGet':{'path':'/healthz','port':9119},'periodSeconds':5},
        'livenessProbe':{'httpGet':{'path':'/healthz','port':9119},'initialDelaySeconds':10,'periodSeconds':15}}
    pod_security={'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'seccompProfile':{'type':'RuntimeDefault'}}
    result.append({'apiVersion':'apps/v1','kind':'DaemonSet','metadata':{'name':'platform-agent','namespace':agent_ns},
        'spec':{'selector':{'matchLabels':{'app':'platform-agent'}},'template':{'metadata':{'labels':{'app':'platform-agent'}},'spec':{
        'serviceAccountName':'platform-healer','automountServiceAccountToken':False,
        'nodeSelector':{'kubernetes.io/hostname':'k8s-worker-2'},
        'securityContext':dict(pod_security,supplementalGroups=[64532]),
        'containers':[container],'volumes':[{'name':'broker','hostPath':{'path':'/run/platform-healer','type':'Directory'}}]}}}})
    result.append({'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':'knowledge','namespace':controller_ns},'spec':{
        'accessModes':['ReadWriteOnce'],'resources':{'requests':{'storage':'1Gi'}}}})
    controller=dict(container,name='controller',command=['python','-m','platform_healer.controller'],ports=[{'containerPort':8085}],
        volumeMounts=[{'name':'config','mountPath':'/etc/platform-healer','readOnly':True},
                      {'name':'keys','mountPath':'/run/keys','readOnly':True},{'name':'state','mountPath':'/state'}],
        readinessProbe={'httpGet':{'path':'/healthz','port':8085},'periodSeconds':5},
        livenessProbe={'httpGet':{'path':'/healthz','port':8085},'initialDelaySeconds':15,'periodSeconds':15})
    result.append({'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'platform-controller','namespace':controller_ns},'spec':{
        'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'platform-controller'}},
        'template':{'metadata':{'labels':{'app':'platform-controller'}},'spec':{
        'serviceAccountName':'platform-healer','automountServiceAccountToken':False,
        'nodeSelector':{'kubernetes.io/hostname':'k8s-worker-1'},
        'securityContext':dict(pod_security,fsGroup=10001), 'containers':[controller],
        'volumes':[{'name':'config','configMap':{'name':'controller-settings'}},
                   {'name':'keys','secret':{'secretName':'controller-keys','defaultMode':0o440}},
                   {'name':'state','persistentVolumeClaim':{'claimName':'knowledge'}}]}}}})
    for namespace,app,port,nodeport in ((agent_ns,'platform-agent',9119,30919),(controller_ns,'platform-controller',8085,30885)):
        result.append({'apiVersion':'v1','kind':'Service','metadata':{'name':app,'namespace':namespace},'spec':{
            'type':'NodePort','selector':{'app':app},'ports':[{'port':port,'targetPort':port,'nodePort':nodeport}]}})
    result.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'agent-ingress','namespace':agent_ns},'spec':{
        'podSelector':{'matchLabels':{'app':'platform-agent'}},'policyTypes':['Ingress'],'ingress':[{
            'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':controller_ns}},'podSelector':{'matchLabels':{'app':'platform-controller'}}},
                    {'ipBlock':{'cidr':'10.1.1.50/32'}},{'ipBlock':{'cidr':'10.42.0.0/32'}}],
            'ports':[{'protocol':'TCP','port':9119}]}]}})
    result.append({'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'controller-network','namespace':controller_ns},'spec':{
        'podSelector':{'matchLabels':{'app':'platform-controller'}},'policyTypes':['Ingress','Egress'],
        'ingress':[{'from':[{'ipBlock':{'cidr':'10.1.1.205/32'}},{'ipBlock':{'cidr':'10.1.1.50/32'}},{'ipBlock':{'cidr':'10.42.0.0/32'}}],
                    'ports':[{'protocol':'TCP','port':8085}]}],
        'egress':[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':agent_ns}},'podSelector':{'matchLabels':{'app':'platform-agent'}}}],
                   'ports':[{'protocol':'TCP','port':9119}]},
                  {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
                   'ports':[{'protocol':'UDP','port':53},{'protocol':'TCP','port':53}]}]}})
    targets=[{'id':'ports-canary','baseline':[40000,40031],'expanded':[40000,40255]},
             {'id':'descriptors-canary','baseline':64,'expanded':256}]
    for target in targets:target.update(url='http://platform-agent.platform-healer-system.svc:9119',key_file='/run/keys/node.key',lease=30,node='k8s-worker-2')
    config={'database':'/state/knowledge.db','token_file':'/run/keys/operator.token','allow_plaintext_lab':True,
            'allowed_origins':['http://127.0.0.1:8085','http://localhost:8085'],'targets':targets}
    result.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'controller-settings','namespace':controller_ns},'data':{'controller.json':json.dumps(config)}})
    return result

if __name__=='__main__':print(json.dumps({'apiVersion':'v1','kind':'List','items':objects(sys.argv[1])},indent=2))
