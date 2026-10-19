"""Generate the single HAProxy gateway dashboard, rules and scrape configuration."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
nodes={'healer-ubuntu':'10.1.1.205','monitor':'10.1.1.50','k8s-control':'10.1.1.80','k8s-worker-1':'10.1.1.81','k8s-worker-2':'10.1.1.82','probe-1':'10.1.1.84'}
tls={'ca_file':'/etc/prometheus/platform-tls/ca.crt','cert_file':'/etc/prometheus/platform-tls/client.crt','key_file':'/etc/prometheus/platform-tls/client.key'}
prometheus={'global':{'scrape_interval':'5s','evaluation_interval':'5s'},'rule_files':['/etc/prometheus/rules/platform.json'],'scrape_configs':[
 {'job_name':'prometheus','static_configs':[{'targets':['127.0.0.1:9090']}]},
 {'job_name':'platform_nodes','static_configs':[{'targets':[ip+':9100'],'labels':{'node':name}} for name,ip in nodes.items()]},
 {'job_name':'platform_agent','scheme':'https','tls_config':tls,'static_configs':[{'targets':['10.1.1.80:30919']}]},
 {'job_name':'platform_gateway_client','scheme':'https','tls_config':tls,'static_configs':[{'targets':['10.1.1.84:9106']}]},
 {'job_name':'platform_controller','static_configs':[{'targets':['10.1.1.80:30885']}]},
 {'job_name':'platform_api_ready','metrics_path':'/probe','params':{'module':['k3s_ready']},'static_configs':[{'targets':['https://10.1.1.80:6443/readyz']}],
  'relabel_configs':[{'source_labels':['__address__'],'target_label':'__param_target'},{'target_label':'__address__','replacement':'127.0.0.1:9115'}]}]}
alerts=[
 ('PlatformTelemetryUnavailable','up{job=~"platform_.*"} == 0','20s','Required platform telemetry is unreachable'),
 ('PlatformSampleStale','platform_sample_fresh{target="gateway-ports"} == 0','15s','Gateway evidence stale; do not infer health'),
 ('PlatformBrokerUnavailable','platform_agent_broker_up == 0','10s','Native broker unreachable'),
 ('PlatformLoopStalled','platform_controller_loop_fresh == 0','10s','MAPE-K controller not completing ticks'),
 ('GatewayClientTransactionFailed','platform_gateway_transaction_success == 0','10s','Independent HTTP transaction through HAProxy is failing'),
 ('GatewayUpstreamUnavailable','platform_resource_upstream_healthy{target="gateway-ports"} == 0','10s','Upstream unavailable; increasing ports is not an eligible repair'),
 ('GatewayRollbackNeedsReview','platform_broker_operations{status=~"rollback_deferred|conflict|identity_changed"} > 0','20s','Inspect lease reconciliation history'),
 ('GatewayApprovalPending','platform_incidents{status="pending"} > 0','30s','Gateway incident awaits investigation or approval'),
 ('PlatformHostMemoryPressure','node_memory_MemAvailable_bytes{job="platform_nodes"}/node_memory_MemTotal_bytes{job="platform_nodes"}<0.15','1m','Host memory headroom below the gateway admission threshold')]
rules={'groups':[{'name':'gateway','rules':[{'alert':name,'expr':expr,'for':duration,'labels':{'severity':'warning'},'annotations':{'summary':detail}} for name,expr,duration,detail in alerts]}]}
# Service health only; incident and safety history belongs in the healer console.
def target(expr, label):return {'refId':chr(65),'expr':expr,'legendFormat':label}
def panel(title,description,targets,kind='timeseries',unit=None,mappings=None):
    n=len(panels)
    pos={'x':n%2*12,'y':n//2*9,'w':12,'h':9}
    fields={'color':{'mode':'palette-classic'},'custom':{'lineWidth':2,'fillOpacity':8}}
    if unit:fields['unit']=unit
    if mappings:fields['mappings']=[{'type':'value','options':mappings}]
    fields['noValue']='Not known'
    for i,t in enumerate(targets):t['refId']=chr(65+i)
    value={'id':n+1,'title':title,'description':description,'type':kind,'datasource':{'type':'prometheus','uid':'prometheus'},'gridPos':pos,'targets':targets,'fieldConfig':{'defaults':fields,'overrides':[]}}
    if kind=='stat':
        # Instant queries prevent an old fallback series and today's value from
        # appearing side-by-side as contradictory health statuses.
        for t in targets:t.update(instant=True,range=False)
        value['options']={'reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False},'colorMode':'value','graphMode':'none','textMode':'value','justifyMode':'auto'}
    panels.append(value)
panels=[]
health={'1':{'text':'Working','color':'green'},'0':{'text':'Failing','color':'red'},'-1':{'text':'Not known','color':'orange'}}
panel('How quickly do requests respond?','Elapsed time for the independent HTTP check. Read alongside request success; a fast error is not recovery.',[target('platform_gateway_transaction_latency_seconds','Response time')],unit='s')
panel('Are outgoing ports running out?','Each outgoing backend connection needs a source port. The qualified repair temporarily increases the namespace pool from 32 to 256 ports.',[target('platform_resource_used_ports{target="gateway-ports"}','Ports in use'),target('platform_resource_range_size{target="gateway-ports"}','Available port range'),target('platform_resource_active_connections{target="gateway-ports"}','Active backend connections')],unit='short')
panel('Are new errors occurring?','Estimated increase over the last minute. Old cumulative error totals do not mean the service is still failing.',[target('increase(platform_resource_gateway_5xx{target="gateway-ports"}[1m])','Failed HTTP responses'),target('increase(platform_resource_backend_connect_errors{target="gateway-ports"}[1m])','Backend connection errors')],unit='short')
panel('Is there memory headroom for a repair?','Host available-memory fraction. Repair also requires at least 256 MiB free; a percentage alone is not approval.',[target('platform_resource_memory_available_ratio{target="gateway-ports"}','Memory available')],unit='percentunit')
panels[1]['fieldConfig']['overrides']=[{'matcher':{'id':'byName','options':'Available port range'},'properties':[{'id':'custom.lineInterpolation','value':'stepAfter'}]}]

dashboard={'uid':'platform-mapek','title':'Gateway operations - performance trends','description':'Four measured trends: HTTP check duration, port pressure, new errors and memory. Current state, incidents and decisions are in the operations console.','links':[{'title':'Open healer and review an incident','url':'http://127.0.0.1:8085/','type':'link'}],'schemaVersion':39,'version':4,'editable':False,'refresh':'5s','time':{'from':'now-15m','to':'now'},'tags':['gateway','mapek'],'panels':panels}
blackbox={'modules':{'k3s_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'tls_config':{'ca_file':'/etc/prometheus/healer-k3s-ca.pem'}}}}}
for name,value in [('prometheus.json',prometheus),('rules.json',rules),('dashboard.json',dashboard),('blackbox.json',blackbox)]:
 (ROOT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
