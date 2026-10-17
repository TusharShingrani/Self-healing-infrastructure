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
queries=[
 ('Does the independent client receive the correct HTTP response?','platform_gateway_transaction_success'),
 ('Independent client transaction latency (seconds)','platform_gateway_transaction_latency_seconds'),
 ('Gateway port capacity, occupancy and active backend connections','{__name__=~"platform_resource_(used_ports|range_size|active_connections)",target="gateway-ports"}'),
 ('Gateway, upstream and independent client health','{__name__=~"platform_resource_(upstream_healthy|gateway_transaction_ok|client_transaction_ok)",target="gateway-ports"}'),
 ('HAProxy HTTP 5xx and backend-connect errors (cumulative)','{__name__=~"platform_resource_(gateway_5xx|backend_connect_errors)",target="gateway-ports"}'),
 ('Allocation probe errno: 99 means no local port available','platform_resource_allocation_probe_errno{target="gateway-ports"}'),
 ('Measured host memory headroom','platform_resource_memory_available_ratio{target="gateway-ports"}'),
 ('Gateway incidents and verification','platform_incidents'),
 ('Gateway learned procedure eligibility','platform_procedures'),
 ('Broker lease and rollback journal','platform_broker_operations'),
 ('Fresh gateway evidence and controller loop','{__name__=~"platform_sample_fresh|platform_controller_loop_fresh|platform_agent_broker_up"}'),
 ('Infrastructure monitoring endpoints','up{job=~"platform_.*"}')]
panels=[]
for title,query in queries:
 n=len(panels);panels.append({'id':n+1,'title':title,'type':'timeseries','datasource':{'type':'prometheus','uid':'prometheus'},'gridPos':{'x':n%2*12,'y':n//2*9,'w':12,'h':9},'targets':[{'refId':'A','expr':query,'legendFormat':'{{__name__}} {{target}} {{node}} {{status}} {{job}}'}]})
dashboard={'uid':'platform-mapek','title':'HAProxy gateway - MAPE-K recovery','schemaVersion':39,'version':2,'editable':False,'refresh':'5s','time':{'from':'now-15m','to':'now'},'tags':['gateway','mapek'],'panels':panels}
blackbox={'modules':{'k3s_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'tls_config':{'ca_file':'/etc/prometheus/healer-k3s-ca.pem'}}}}}
for name,value in [('prometheus.json',prometheus),('rules.json',rules),('dashboard.json',dashboard),('blackbox.json',blackbox)]:
 (ROOT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
