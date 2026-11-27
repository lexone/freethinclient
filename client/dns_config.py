"""Validated group DNS configuration; only the root agent writes its own NM snippet."""
import ipaddress
import json
import os
import re
import subprocess
from pathlib import Path

CONFIG=Path('/etc/NetworkManager/conf.d/90-freethinclient-dns.conf')
STATE=Path('/var/lib/freethinclient-client/dns-status.json')


def entries(value):
    if isinstance(value,str):
        if len(value)>512 or any(ord(c)<32 for c in value): raise ValueError('Lista DNS inválida')
        value=[part for part in re.split(r'[ ,;]+',value.strip()) if part]
    if not isinstance(value,list) or len(value)>6 or any(not isinstance(v,str) for v in value):
        raise ValueError('Informe no máximo seis endereços ou domínios DNS')
    return value


def servers(value):
    result=[]
    for item in entries(value):
        if '%' in item: raise ValueError('DNS deve ser um IP sem identificador de interface')
        try: address=ipaddress.ip_address(item)
        except ValueError: raise ValueError('Servidor DNS inválido: informe um IP') from None
        if address.is_unspecified or address.is_multicast: raise ValueError('Servidor DNS inválido')
        if str(address) not in result: result.append(str(address))
    return result


def domains(value):
    result=[]
    for item in entries(value):
        if len(item)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label)
                                   for label in item.rstrip('.').split('.')):
            raise ValueError('Domínio de pesquisa DNS inválido')
        item=item.rstrip('.').lower()
        if item not in result: result.append(item)
    if sum(len(item)+1 for item in result)>256: raise ValueError('Lista de domínios DNS muito longa')
    return result


def configuration(profile):
    if not (profile.get('approved') is True and profile.get('dns_override') is True): return ''
    addresses=servers(profile.get('dns_servers',[]));searches=domains(profile.get('dns_search',[]))
    if not addresses: raise ValueError('Informe pelo menos um servidor DNS')
    return ('# Managed by FreeThinClient; remove only through the group profile.\n'
            '[global-dns]\nsearches='+','.join(searches)+'\n\n'
            '[global-dns-domain-*]\nservers='+','.join(addresses)+'\n')


def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w') as output:
        os.chmod(temporary,0o644);output.write(value)
    os.replace(temporary,path)


def status():
    try:
        result=json.loads(STATE.read_text())
        return {key:result[key] for key in ('state','message')}
    except (OSError,ValueError,KeyError): return {}


def apply(profile):
    # Never restart networking or change connection IPs/routes; reload only DNS config.
    desired=''
    try:
        desired=configuration(profile)
        existing=CONFIG.read_text() if CONFIG.exists() else ''
        previous=json.loads(STATE.read_text()) if STATE.exists() else {}
        if desired!=existing:
            if desired: atomic(CONFIG,desired)
            else: CONFIG.unlink(missing_ok=True)
        if desired!=existing or previous.get('configuration','')!=desired or previous.get('state')=='error':
            subprocess.run(['nmcli','general','reload','conf','dns-rc'],check=True,
                           capture_output=True,timeout=15)
        result={'state':'applied' if desired else 'dhcp',
                'message':('DNS do grupo configurado: '+', '.join(servers(profile.get('dns_servers',[]))))
                    if desired else 'Sem DNS imposto pelo grupo; usando a configuração da conexão.',
                'configuration':desired}
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        result={'state':'error','message':'Falha ao aplicar DNS ('+type(error).__name__+'). Consulte o diagnóstico no cliente.',
                'configuration':None}
    try: atomic(STATE,json.dumps(result))
    except OSError: pass
    return {key:result[key] for key in ('state','message')}
