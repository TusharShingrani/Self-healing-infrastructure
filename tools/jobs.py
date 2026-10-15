"""Operator CLI for the job lab; submit work, inspect evidence and approve recipes."""
import argparse,json,os,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mapek.jobs import JobsWorld,JobsOperator,ROOT,CONFIG
from mapek.infrastructure import InvestigatedAnalyser
from mapek.loop import Healer

def build(state='state/jobs'):
    Path(state).mkdir(parents=True,exist_ok=True)
    world=JobsWorld();operator=JobsOperator(str(Path(state)/'operator.db'))
    healer=Healer(world,knowledge_path=str(Path(state)/'knowledge.db'),auto_approve=False)
    healer.operator=operator;healer.analyser=InvestigatedAnalyser(world,operator)
    if os.environ.get('GEMINI_API_KEY'):
        from mapek.advisor import Advisor
        healer.advisor=Advisor(healer.knowledge)
    return world,operator,healer

def request(path,data=None):
    config=json.loads((Path.home()/'.config/healer-jobs/client.json').read_text())
    req=urllib.request.Request(config['url']+path,data=None if data is None else json.dumps(data).encode(),headers={'Authorization':'Bearer '+config['token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',default='state/jobs');sub=p.add_subparsers(dest='command',required=True)
    for name in ('status','list','procedures','tick','export'):sub.add_parser(name)
    submit=sub.add_parser('submit');submit.add_argument('payload')
    result=sub.add_parser('result');result.add_argument('id',type=int)
    show=sub.add_parser('show');show.add_argument('id',type=int)
    for name in ('investigate','approve','reject','record-human','promote'):
        c=sub.add_parser(name);c.add_argument('id',type=int);c.add_argument('--who',required=True)
        if name!='promote':c.add_argument('--notes',required=True)
        if name in ('investigate','record-human'):c.add_argument('--recipe',required=True)
        if name=='investigate':c.add_argument('--cause',required=True)
    a=p.parse_args()
    if a.command in ('submit','result'):
        print(json.dumps(request('/jobs',{'payload':a.payload}) if a.command=='submit' else request('/jobs/'+str(a.id)),indent=2));return
    world,op,h=build(a.state)
    if a.command=='status':data=world.observe(False)
    elif a.command=='list':data=op.cases()
    elif a.command=='procedures':data=op.procedures()
    elif a.command=='show':data=op.case(a.id)
    elif a.command=='export':data={'cases':op.cases(),'procedures':op.procedures(),'audit':[dict(r) for r in op.db.execute('SELECT * FROM operator_audit ORDER BY id')]}
    elif a.command=='investigate':data=op.investigate(world,a.id,a.cause,['recipe_'+a.recipe],a.who,a.notes)
    elif a.command in ('approve','reject'):data={'saved':op.decide(a.id,a.command=='approve',a.who,a.notes)}
    elif a.command=='promote':op.promote(a.id,a.who);data={'promoted':a.id}
    elif a.command=='record-human':world.observe(False);data={'verified':op.record_human(world,a.id,['recipe_'+a.recipe],a.who,a.notes)}
    else:h.tick();data=[e.__dict__ for e in h.events[-1:]]
    print(json.dumps(data,indent=2))

if __name__=='__main__':main()
