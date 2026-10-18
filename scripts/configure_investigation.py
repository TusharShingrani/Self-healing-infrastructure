"""Administrator-only opt-in Gemini configuration; never print credential material."""
import argparse
import base64
import ipaddress
import json
import socket
from pathlib import Path

from deploy_lab import Admin, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default=str(ROOT/'config/educloud.json'))
    parser.add_argument('--model',required=True)
    parser.add_argument('--key-file',required=True)
    args=parser.parse_args()
    # Validate without contacting the provider or inheriting its secret into shell text.
    import sys
    sys.path.insert(0,str(ROOT/'src'))
    from platform_healer.investigation import GeminiAdvisor
    key=Path(args.key_file).expanduser().read_text().strip()
    GeminiAdvisor(args.model,key)
    addresses=sorted({entry[4][0] for entry in socket.getaddrinfo(
        'generativelanguage.googleapis.com',443,socket.AF_INET,socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('Public Gemini addresses required')
    admin=Admin(json.loads(Path(args.config).read_text()))
    prefix='sudo k3s kubectl -n platform-healer '
    settings=json.loads(admin.run('k8s-control',prefix+'get configmap controller-settings -o json'))
    config=json.loads(settings['data']['controller.json'])
    config['investigation']={'enabled':True,'model':args.model}
    objects=[{'apiVersion':'v1','kind':'Secret','metadata':{'name':'gemini-advisor','namespace':'platform-healer'},
        'type':'Opaque','data':{'api-key':base64.b64encode(key.encode()).decode()}},
        {'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy',
         'metadata':{'name':'gemini-advisor-egress','namespace':'platform-healer'},
         'spec':{'podSelector':{'matchLabels':{'app':'platform-controller'}},'policyTypes':['Egress'],
                 'egress':[{'to':[{'ipBlock':{'cidr':ip+'/32'}} for ip in addresses],
                            'ports':[{'protocol':'TCP','port':443}]}]}},
        {'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'controller-settings','namespace':'platform-healer'},
         'data':{'controller.json':json.dumps(config)}}]
    admin.run('k8s-control','sudo k3s kubectl apply -f -',json.dumps({'apiVersion':'v1','kind':'List','items':objects}).encode())
    patch={'spec':{'template':{'spec':{'containers':[{'name':'controller',
        'env':[{'name':'GEMINI_API_KEY','valueFrom':{'secretKeyRef':{'name':'gemini-advisor','key':'api-key'}}}]}]}}}}
    admin.run('k8s-control',prefix+'patch deployment platform-controller --type=strategic --patch-file=/dev/stdin',json.dumps(patch).encode())
    admin.run('k8s-control',prefix+'rollout restart deployment/platform-controller')
    admin.run('k8s-control',prefix+'rollout status deployment/platform-controller --timeout=120s',timeout=150)
    print('Gemini enabled with Secret reference and resolved destination IPs only; default-deny retained.')
    print('Refresh this administrator configuration if the provider DNS addresses change.')


if __name__=='__main__':main()
