"""Typed control contracts. Telemetry is data, never an executable instruction."""
from dataclasses import dataclass,asdict
import hashlib,hmac,json,time,uuid,math

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()

@dataclass(frozen=True)
class Sample:
    target:str
    kind:str
    identity:str
    time:float
    metrics:dict
    supported:bool=True
    error:str=''
    def valid(self,now=None,max_age=10):
        now=time.time() if now is None else now
        return bool(self.identity) and self.supported and not self.error and isinstance(self.time,(float,int)) and math.isfinite(self.time) and -2<=now-self.time<=max_age
    def json(self):return asdict(self)

def sign(payload,key):return hmac.new(key,canonical(payload).encode(),hashlib.sha256).hexdigest()
def intent(target,identity,action,expected,parameters,approval,key,lease=60,now=None):
    p={'version':1,'id':str(uuid.uuid4()),'target':target,'identity':identity,'action':action,'expected':expected,'parameters':parameters,'approval':approval,'lease':lease,'issued':time.time() if now is None else now}
    return {'payload':p,'signature':sign(p,key)}

def authenticate(envelope,key,now=None):
    if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:raise ValueError('Invalid envelope')
    p=envelope['payload']
    required={'version','id','target','identity','action','expected','parameters','approval','lease','issued'}
    if not isinstance(p,dict) or set(p)!=required or p['version']!=1:raise ValueError('Invalid intent schema')
    if not isinstance(envelope['signature'],str) or not hmac.compare_digest(sign(p,key),envelope['signature']):raise ValueError('Invalid signature')
    age=(time.time() if now is None else now)-p['issued']
    if not math.isfinite(age) or not -2<=age<=60:raise ValueError('Expired/future intent')
    if type(p['lease']) is not int or not 5<=p['lease']<=120:raise ValueError('Unbounded lease')
    if not isinstance(p['approval'],str) or not p['approval'].strip():raise ValueError('Missing decision reference')
    if str(uuid.UUID(p['id']))!=p['id']:raise ValueError('Invalid operation id')
    return p
