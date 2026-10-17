"""Secret-free Prometheus rules and Grafana view for the platform use case."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
nodes={'healer-ubuntu':'10.1.1.205','monitor':'10.1.1.50','k8s-control':'10.1.1.80',
       'k8s-worker-1':'10.1.1.81','k8s-worker-2':'10.1.1.82','probe-1':'10.1.1.84'}
prometheus={'global':{'scrape_interval':'5s','evaluation_interval':'5s'},'rule_files':['/etc/prometheus/rules/platform.json'],
 'scrape_configs':[{'job_name':'prometheus','static_configs':[{'targets':['127.0.0.1:9090']}]},
 {'job_name':'platform_nodes','static_configs':[{'targets':[ip+':9100'],'labels':{'node':name}} for name,ip in nodes.items()]},
 {'job_name':'platform_agent','static_configs':[{'targets':['10.1.1.80:30919']}]},
 {'job_name':'platform_controller','static_configs':[{'targets':['10.1.1.80:30885']}]},
 {'job_name':'platform_api_ready','metrics_path':'/probe','params':{'module':['k3s_ready']},'static_configs':[{'targets':['https://10.1.1.80:6443/readyz']}],
 'relabel_configs':[{'source_labels':['__address__'],'target_label':'__param_target'},{'target_label':'__address__','replacement':'127.0.0.1:9115'}]}]}
rules={'groups':[{'name':'platform','rules':[
 {'alert':'PlatformTelemetryUnavailable','expr':'up{job=~"platform_agent|platform_controller|platform_nodes"} == 0','for':'20s','labels':{'severity':'warning'},'annotations':{'summary':'Required platform telemetry is unreachable'}},
 {'alert':'PlatformSampleStale','expr':'platform_sample_fresh == 0','for':'15s','labels':{'severity':'warning'},'annotations':{'summary':'Canary telemetry is stale: investigate, never assume healthy'}},
 {'alert':'PlatformBrokerUnavailable','expr':'platform_agent_broker_up == 0','for':'10s','labels':{'severity':'critical'},'annotations':{'summary':'Native mutation/rollback broker is unreachable'}},
 {'alert':'PlatformLoopStalled','expr':'platform_controller_loop_fresh == 0','for':'10s','labels':{'severity':'critical'},'annotations':{'summary':'MAPE-K controller has stopped completing ticks'}},
 {'alert':'PlatformRollbackNeedsReview','expr':'platform_broker_operations{status=~"rollback_deferred|conflict|identity_changed"} > 0','for':'20s','labels':{'severity':'warning'},'annotations':{'summary':'Inspect broker journal: a historical or active lease needs review'}},
 {'alert':'PlatformApprovalPending','expr':'platform_incidents{status="pending"} > 0','for':'30s','labels':{'severity':'info'},'annotations':{'summary':'An incident is awaiting investigation or operator approval'}},
 {'alert':'PlatformApiUnready','expr':'probe_success{job="platform_api_ready"} == 0','for':'20s','labels':{'severity':'warning'},'annotations':{'summary':'Kubernetes API readiness probe failed'}},
 {'alert':'PlatformHostMemoryPressure','expr':'node_memory_MemAvailable_bytes{job="platform_nodes"}/node_memory_MemTotal_bytes{job="platform_nodes"}<0.1','for':'1m','labels':{'severity':'warning'},'annotations':{'summary':'Node memory headroom below ten percent; runtime tuning may be unsafe'}}]}]}
panels=[]
for title,expression in [
 ('Monitoring endpoints available','up{job=~"platform_.*"}'),
 ('Fresh observations and controller loop','{__name__=~"platform_sample_fresh|platform_controller_loop_fresh"}'),
 ('Descriptor use and soft ceiling','{__name__=~"platform_resource_(open_fds|soft_limit|held_fds)"}'),
 ('Outbound port occupancy and connection recovery','{__name__=~"platform_resource_(used_ports|range_size|active_connections)"}'),
 ('Actual allocation failures (cumulative)','platform_resource_allocation_errors'),
 ('Incident lifecycle','platform_incidents'),
 ('Procedure qualification and automatic reuse eligibility','platform_procedures'),
 ('Broker application and rollback journal','platform_broker_operations'),
 ('Host I/O stall seconds per second','rate(node_pressure_io_waiting_seconds_total{job="platform_nodes"}[1m])'),
 ('Host memory available','node_memory_MemAvailable_bytes{job="platform_nodes"}')]:
    n=len(panels);panels.append({'id':n+1,'title':title,'type':'timeseries','datasource':{'type':'prometheus','uid':'prometheus'},
        'gridPos':{'x':(n%2)*12,'y':(n//2)*9,'w':12,'h':9},'targets':[{'refId':'A','expr':expression,'legendFormat':'{{__name__}} {{target}} {{node}} {{status}} {{job}} {{instance}}'}]})
dashboard={'uid':'platform-mapek','title':'Kernel & platform tuning - MAPE-K','schemaVersion':39,'version':1,'editable':False,'refresh':'5s',
 'time':{'from':'now-15m','to':'now'},'tags':['platform','mapek'],'panels':panels}
for name,value in [('prometheus.json',prometheus),('rules.json',rules),('dashboard.json',dashboard),
                   ('blackbox.json',{'modules':{'k3s_ready':{'prober':'http','timeout':'5s','http':{'valid_status_codes':[200],'tls_config':{'ca_file':'/etc/prometheus/healer-k3s-ca.pem'}}}}})]:
    (ROOT/name).write_text(json.dumps(value,indent=2)+'\n')
