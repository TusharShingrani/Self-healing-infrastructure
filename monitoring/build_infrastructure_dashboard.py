"""Generate a read-only dependency and reviewed-learning dashboard."""
import json
from pathlib import Path
panels=[]
items=[
 ('Transaction usable','healer_infrastructure_healthy','stat'),
 ('Waiting for investigation or approval','healer_infrastructure_pending','stat'),
 ('Validated repair procedures','healer_infrastructure_validated','stat'),
 ('Component checks: 1 good, 0 failed, -1 unmeasured','healer_infrastructure_check','timeseries'),
 ('Actual transaction latency','healer_infrastructure_transaction_ms','timeseries'),
 ('Monitor cycle duration','healer_infrastructure_tick_seconds','timeseries'),
 ('Healer CPU seconds per second','rate(healer_infrastructure_process_cpu_seconds[2m])','timeseries'),
 ('Loop errors','healer_infrastructure_errors_total','timeseries'),
 ('Age of last completed monitor cycle (seconds)','time() - healer_infrastructure_last_tick_seconds','stat'),
 ('Pending advisory answers (not repair approval)','healer_infrastructure_advisor_pending','stat'),
]
for i,(title,expr,kind) in enumerate(items):
 panels.append({'id':i+1,'type':kind,'title':title,'gridPos':{'x':(i%2)*12,'y':(i//2)*8,'w':12,'h':8},
                'datasource':{'type':'prometheus','uid':'prometheus'},'targets':[{'expr':expr,'refId':'A','legendFormat':'{{check}}'}],
                'fieldConfig':{'defaults':{},'overrides':[]},'options':{}})
dashboard={'uid':'selfheal-infrastructure','title':'Infrastructure dependencies and reviewed learning','schemaVersion':39,
           'version':1,'refresh':'10s','time':{'from':'now-30m','to':'now'},'panels':panels,'tags':['MAPE-K','infrastructure']}
Path(__file__).parent.joinpath('grafana/dashboards/infrastructure.json').write_bytes((json.dumps(dashboard,indent=2)+'\n').encode())
