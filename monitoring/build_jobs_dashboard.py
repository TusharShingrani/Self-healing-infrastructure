"""Read-only concrete business outcome, infrastructure and security dashboard."""
import json
from pathlib import Path
items=[
 ('Do submitted jobs complete correctly?','job_client_healthy','stat'),
 ('Managed infrastructure contract','job_healer_healthy','stat'),
 ('Last independent sample age (seconds)','time()-job_client_last_sample_seconds','stat'),
 ('Job completion time (seconds)','job_client_completion_seconds','timeseries'),
 ('Database available','job_database_up','stat'),
 ('Waiting jobs and completed jobs','{__name__=~"job_database_pending|job_database_done"}','timeseries'),
 ('Oldest waiting job (seconds)','job_database_oldest_pending_seconds','timeseries'),
 ('Security and dependency checks: 1 pass, 0 fail, -1 unmeasured','job_healer_check','timeseries'),
 ('Human investigation or approval needed','job_healer_pending','stat'),
 ('Validated job repair procedures','job_healer_validated','stat'),
 ('Desired and ready replicas','job_kubernetes_replicas','timeseries'),
 ('Container restart counts (native Kubernetes)','job_kubernetes_pod_restarts','timeseries'),
 ('Application operations','sum by (__name__) ({__name__=~"job_process_submitted_total|job_process_completed_total|job_process_errors_total"})','timeseries'),
 ('Actual container memory (MiB)','job_pod_memory_mib','timeseries'),
 ('Actual container CPU cores','job_pod_cpu_cores','timeseries'),
 ('Host memory use','1-node_memory_MemAvailable_bytes{job="expanded_nodes"}/node_memory_MemTotal_bytes{job="expanded_nodes"}','timeseries'),
 ('Host root disk use','1-node_filesystem_avail_bytes{job="expanded_nodes",mountpoint="/"}/node_filesystem_size_bytes{job="expanded_nodes",mountpoint="/"}','timeseries'),
 ('Job-healer errors','job_healer_errors_total','timeseries'),
 ('Job-healer cycle duration (seconds)','job_healer_tick_seconds','timeseries'),
 ('API server requests per second','rate(job_kubernetes_apiserver_request_total[2m])','timeseries'),
 ('Host CPU use','1-avg by (node) (rate(node_cpu_seconds_total{job="expanded_nodes",mode="idle"}[2m]))','timeseries'),
]
panels=[]
for i,(title,query,kind) in enumerate(items):
 panels.append({'id':i+1,'type':kind,'title':title,'gridPos':{'x':(i%2)*12,'y':(i//2)*8,'w':12,'h':8},
                'datasource':{'type':'prometheus','uid':'prometheus'},'targets':[{'expr':query,'refId':'A','legendFormat':'{{check}}{{deployment}}{{pod}}{{node}}'}],
                'fieldConfig':{'defaults':{},'overrides':[]},'options':{}})
data={'uid':'selfheal-jobs','title':'Job workflow, Kubernetes and reviewed recovery','schemaVersion':39,'version':1,'refresh':'10s','time':{'from':'now-30m','to':'now'},'panels':panels,'tags':['MAPE-K','jobs','security']}
Path(__file__).parent.joinpath('grafana/dashboards/jobs.json').write_bytes((json.dumps(data,indent=2)+'\n').encode())
