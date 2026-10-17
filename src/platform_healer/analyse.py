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
    if sample.kind=='gateway_ports':
        required=('used_ports','range_size','backend_connect_errors','gateway_5xx','allocation_probe_errno')
        if any(type(m.get(k)) is not int or m[k]<0 for k in required):return Diagnosis('unknown',None,'Incomplete gateway allocation evidence')
        if any(type(m.get(k)) is not bool for k in ('upstream_healthy','gateway_transaction_ok','client_transaction_ok','headroom_safe','reserved_conflict')):
            return Diagnosis('unknown',None,'Missing upstream/headroom/conflict evidence')
        if not m['upstream_healthy']:return Diagnosis('gateway_dependency_unavailable',None,'Upstream fails its independent Unix health check; increasing ports cannot repair it')
        if not m['headroom_safe']:return Diagnosis('gateway_unsafe_headroom',None,'Memory headroom is below the approved safety threshold')
        if m['reserved_conflict']:return Diagnosis('gateway_reserved_port_conflict',None,'Approved expansion overlaps reserved ports; operator investigation required')
        if previous and previous.identity==sample.identity and previous.valid(now):
            for counter in ('backend_connect_errors','gateway_5xx'):
                if m[counter]<previous.metrics.get(counter,m[counter]):return Diagnosis('unknown',None,'Gateway counter reset; establish a fresh observation window')
            failed=m['gateway_5xx']>previous.metrics.get('gateway_5xx',m['gateway_5xx'])
            connection_errors=m['backend_connect_errors']>previous.metrics.get('backend_connect_errors',m['backend_connect_errors'])
            if m['range_size']>0 and m['used_ports']/m['range_size']>=.85 and m['allocation_probe_errno']==99 and failed and connection_errors and not m['gateway_transaction_ok'] and not m['client_transaction_ok']:
                return Diagnosis('gateway_outbound_port_exhaustion','expand_port_range','HAProxy HTTP/connect errors, namespace EADDRNOTAVAIL and saturated port pool; upstream independently healthy')
        if not m['gateway_transaction_ok'] or not m['client_transaction_ok']:return Diagnosis('gateway_investigation_required',None,'Gateway/client transaction failed without a complete safe port-exhaustion signature')
    elif sample.kind=='ports':
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
