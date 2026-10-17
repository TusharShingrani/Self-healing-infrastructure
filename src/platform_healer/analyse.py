"""Correlated signatures; missing evidence cannot become a diagnosis."""
from dataclasses import dataclass
@dataclass(frozen=True)
class Diagnosis:
    cause:str
    action:str|None
    detail:str

def analyse(sample,previous=None,now=None):
    if not sample.valid(now):return Diagnosis('unknown',None,sample.error or 'Unsupported or stale measurement')
    m=sample.metrics
    if sample.kind=='ports':
        needed=('used_ports','range_size','allocation_errors','successful_connections','desired_connections')
        if any(type(m.get(k)) is not int or m[k]<0 for k in needed):return Diagnosis('unknown',None,'Incomplete port evidence')
        error_delta=m['allocation_errors']-(previous.metrics.get('allocation_errors',0) if previous and previous.identity==sample.identity else m['allocation_errors'])
        if m['range_size']>0 and m['used_ports']/m['range_size']>=.85 and error_delta>0 and m['successful_connections']<m['desired_connections']:
            return Diagnosis('outbound_port_exhaustion','expand_port_range','Measured local-port pressure and failed outbound allocation')
    elif sample.kind=='descriptors':
        needed=('open_fds','soft_limit','hard_limit','allocation_errors','held_fds','desired_fds')
        if any(type(m.get(k)) is not int or m[k]<0 for k in needed):return Diagnosis('unknown',None,'Incomplete descriptor evidence')
        delta=m['allocation_errors']-(previous.metrics.get('allocation_errors',0) if previous and previous.identity==sample.identity else m['allocation_errors'])
        if m['soft_limit']>0 and m['open_fds']/m['soft_limit']>=.85 and delta>0 and m['held_fds']<m['desired_fds']:
            return Diagnosis('process_descriptor_exhaustion','raise_nofile_soft','Measured per-process descriptor pressure and EMFILE')
    elif sample.kind=='io':
        if m.get('scheduler_supported') is not True:return Diagnosis('unsupported',None,'No verified effective I/O scheduling capability')
        return Diagnosis('investigate_io_contention',None,'I/O scheduling requires correlated durable-operation latency and reviewed competitor')
    else:return Diagnosis('unknown',None,'No diagnostic contract for this resource kind')
    return Diagnosis('healthy',None,'No supported saturation signature')
