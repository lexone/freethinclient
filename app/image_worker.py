"""Root-only image maintenance worker. Updates a staged Debian image, never the host OS."""
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from app import images
from app.store import Store
from app.updater import atomic_json

BASE = Path(__file__).resolve().parents[1]
INSTALL = Path('/opt/freethinclient')
STATE = Path('/var/lib/freethinclient')
CONTROL = STATE / 'image-jobs' / 'request.json'
WORK = Path('/var/lib/freethinclient-image')
BOOT = Path('/srv/freethinclient/boot')
FILES = ('vmlinuz','initrd.img','filesystem.squashfs')
CHROME = 'https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb'
MAX_DOWNLOAD = 600 * 1024 * 1024


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_versions(raw):
    wanted={'linux-image-amd64','chromium','google-chrome-stable','icaclient'}
    result={}
    for paragraph in raw.split('\n\n'):
        fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in paragraph.splitlines() if ':' in line and not line.startswith(' ')}
        name=fields.get('Package')
        if name in wanted and fields.get('Status')=='install ok installed':
            result[name]=fields.get('Version','desconhecida')
    return result


def source_image():
    if not (BOOT/'boot.ipxe').is_file():
        raise ValueError('Publique primeiro uma imagem PXE no servidor')
    text=(BOOT/'boot.ipxe').read_text()
    match=re.search(r'^set base (https?://[^\s]+)$',text,re.M)
    if not match:
        raise ValueError('boot.ipxe não contém uma base HTTP reconhecida')
    url=urlsplit(match[1]); path=url.path.rstrip('/')
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Base de boot inválida')
    origin=match[1][:-len(path)] if path else match[1].rstrip('/')
    if path and not re.fullmatch(r'/releases/[a-f0-9]{24}',path):
        raise ValueError('O diretório de boot não usa o formato de releases suportado')
    root=BOOT/path.lstrip('/') if path else BOOT
    if root.resolve()!=root or not all((root/name).is_file() and not (root/name).is_symlink() for name in FILES):
        raise ValueError('Imagem publicada ausente ou com links não suportados')
    previous=re.search(r'^# previous-image: ([a-f0-9]{24})$',text,re.M)
    return root,origin,previous[1] if previous else None


def inventory(root, previous=None):
    raw=subprocess.run(['unsquashfs','-cat',str(root/'filesystem.squashfs'),'var/lib/dpkg/status'],
                       check=True,capture_output=True,timeout=60).stdout.decode(errors='replace')
    return {'versions':parse_versions(raw),'image':root.name if root!=BOOT else 'original',
            'rollback_available':bool(previous and (BOOT/'releases'/previous/'filesystem.squashfs').is_file())}


def activate(target, origin, previous):
    if target.parent != BOOT/'releases' or not re.fullmatch('[a-f0-9]{24}',target.name):
        raise ValueError('Release de imagem inválida')
    for name in FILES:
        if not (target/name).is_file() or (target/name).is_symlink():
            raise ValueError('Release de imagem incompleta')
    script='#!ipxe\n# iPXE project: https://ipxe.org\n# previous-image: '+previous+'\ndhcp\nset base '+origin+'/releases/'+target.name+'''
kernel ${base}/vmlinuz initrd=initrd.magic boot=live quiet loglevel=3 components username=thinclient hostname=freethinclient locales=pt_BR.UTF-8 keyboard-layouts=br timezone=America/Sao_Paulo fetch=${base}/filesystem.squashfs nopersistence
initrd ${base}/initrd.img
boot
'''
    temporary=BOOT/'boot.ipxe.next'
    temporary.write_text(script)
    temporary.chmod(0o644)
    os.replace(temporary,BOOT/'boot.ipxe')


def verify(root):
    manifest=root/'SHA256SUMS'
    if not manifest.is_file():
        raise ValueError('Manifesto SHA256SUMS ausente')
    values={}
    for line in manifest.read_text().splitlines():
        fields=line.split()
        if len(fields)==2:
            values[fields[1].lstrip('*')]=fields[0]
    for name in FILES:
        if values.get(name)!=sha(root/name):
            raise ValueError('Checksum divergente: '+name)


def copy_release(source, identity):
    target=BOOT/'releases'/identity
    target.mkdir(parents=True,mode=0o755)
    for name in FILES:
        try: os.link(source/name,target/name)
        except OSError: shutil.copyfile(source/name,target/name)
    (target/'SHA256SUMS').write_text(''.join(sha(target/name)+'  '+name+'\n' for name in FILES))
    return target


class VendorRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts=hosts
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed=urlsplit(newurl)
        if parsed.scheme!='https' or parsed.hostname not in self.hosts or parsed.port not in (None,443) or parsed.username or parsed.password:
            raise ValueError('Redirecionamento fora do fornecedor oficial')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_package(job, destination):
    url=CHROME if job['action']=='chrome' else job['url']
    hosts=('dl.google.com',) if job['action']=='chrome' else images.CITRIX_HOSTS
    opener=urllib.request.build_opener(VendorRedirect(hosts))
    total=0
    with opener.open(url,timeout=60) as response, destination.open('xb') as output:
        while True:
            chunk=response.read(1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>MAX_DOWNLOAD: raise ValueError('Pacote maior que 600 MB')
            output.write(chunk)
    if job['action']=='citrix' and sha(destination)!=job['sha256']:
        raise ValueError('O SHA-256 do pacote Citrix não confere')
    fields=subprocess.run(['dpkg-deb','-f',str(destination),'Package','Architecture'],check=True,capture_output=True,timeout=30).stdout.decode()
    package='google-chrome-stable' if job['action']=='chrome' else 'icaclient'
    if ('Package: '+package) not in fields or 'Architecture: amd64' not in fields:
        raise ValueError('Pacote não corresponde ao aplicativo amd64 solicitado')


def run_command(args, log, timeout=1800):
    with log.open('ab') as output:
        subprocess.run(args,stdout=output,stderr=subprocess.STDOUT,check=True,timeout=timeout)


def extract_image(source, target, log):
    # /dev is runtime state, supplied by devtmpfs at boot and by the private
    # device mount during maintenance. Do not recreate archived device nodes.
    run_command(['unsquashfs','-d',str(target),'-excludes',str(source),'dev'],log)
    (target/'dev').mkdir(mode=0o755,exist_ok=True)


def cleanup_staging():
    # Caller holds the worker lock: any earlier build directory is abandoned.
    for path in WORK.glob('build-*'):
        if (not path.is_symlink() and path.is_dir() and path.resolve().parent==WORK.resolve()
                and re.fullmatch(r'build-[a-z0-9_]{8}',path.name)):
            shutil.rmtree(path)


def missing_client_packages(root):
    required=[('polkitd','usr/lib/polkit-1/polkitd'),
              ('libglib2.0-bin','usr/bin/gio'),('xdg-user-dirs','usr/bin/xdg-user-dir'),
              ('gvfs-daemons','usr/libexec/gvfsd-metadata'),
              ('network-manager','usr/bin/nmcli'),('network-manager','usr/bin/nmtui'),
              ('network-manager-gnome','usr/bin/nm-connection-editor'),
              ('xfce4-terminal','usr/bin/xfce4-terminal'),('x11vnc','usr/bin/x11vnc'),
              ('wpasupplicant','sbin/wpa_supplicant'),('wireless-regdb','lib/firmware/regulatory.db'),
              ('rfkill','usr/sbin/rfkill')]
    return list(dict.fromkeys(package for package,binary in required if not (root/binary).is_file()))


def chroot_update(root, action, package=None):
    # This branch is launched only by root in a fresh, private mount namespace.
    if action not in ('client','linux','chromium','chrome','citrix'):
        raise ValueError('Atualização não permitida')
    for name in ('dev','proc','sys'):
        (root/name).mkdir(exist_ok=True)
    subprocess.run(['mount','--rbind','/dev',str(root/'dev')],check=True)
    subprocess.run(['mount','--make-rslave',str(root/'dev')],check=True)
    subprocess.run(['mount','-t','proc','proc',str(root/'proc')],check=True)
    subprocess.run(['mount','--rbind','/sys',str(root/'sys')],check=True)
    subprocess.run(['mount','--make-rslave',str(root/'sys')],check=True)
    policy=root/'usr/sbin/policy-rc.d'; saved=policy.read_bytes() if policy.exists() else None
    resolver=root/'etc/resolv.conf'
    saved_link=os.readlink(resolver) if resolver.is_symlink() else None
    saved_resolver=resolver.read_bytes() if resolver.is_file() else None
    resolver.unlink(missing_ok=True)
    resolver.write_bytes(Path('/etc/resolv.conf').read_bytes())
    policy.write_text('#!/bin/sh\nexit 101\n');policy.chmod(0o755)
    environment={**os.environ,'DEBIAN_FRONTEND':'noninteractive','LC_ALL':'C'}
    def apt(*args):
        subprocess.run(['chroot',str(root),'apt-get','-o','Dpkg::Options::=--force-confdef','-o','Dpkg::Options::=--force-confold',*args],check=True,env=environment)
    try:
        if action=='client':
            missing=missing_client_packages(root)
            if missing:
                apt('update');apt('install','-y',*missing);apt('clean')
            subprocess.run(['chroot',str(root),'update-initramfs','-u','-k','all'],check=True,env=environment)
            return
        apt('update')
        if action=='linux':
            apt('-y','upgrade')
            apt('install','-y','linux-image-amd64','live-boot','initramfs-tools')
        elif action=='chromium':
            apt('install','-y','chromium')
        else:
            destination=root/'tmp/ftc-vendor.deb'
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(package,destination)
            if action=='chrome':
                (root/'etc/default/google-chrome').touch()
            try: apt('install','-y','/tmp/ftc-vendor.deb')
            finally: destination.unlink(missing_ok=True)
        apt('clean')
    finally:
        resolver.unlink(missing_ok=True)
        if saved_link: resolver.symlink_to(saved_link)
        elif saved_resolver is not None: resolver.write_bytes(saved_resolver)
        if saved is None: policy.unlink(missing_ok=True)
        else: policy.write_bytes(saved)


def newest_kernel(root):
    candidates=[]
    for file in (root/'boot').glob('vmlinuz-*'):
        match=re.fullmatch(r'vmlinuz-(\d+)\.(\d+)\.(\d+)-(\d+)-amd64',file.name)
        if match and not file.is_symlink(): candidates.append((tuple(map(int,match.groups())),file))
    if not candidates: raise ValueError('Kernel amd64 não encontrado na imagem')
    kernel=max(candidates)[1]
    initrd=root/'boot'/kernel.name.replace('vmlinuz-','initrd.img-',1)
    if not initrd.is_file(): raise ValueError('Initrd não corresponde ao kernel')
    return kernel,initrd


def perform(job, progress, log):
    root,origin,previous=source_image()
    details=inventory(root,previous)
    if job['action']=='inspect': return details
    verify(root)
    if job['action']=='rollback':
        if not previous: raise ValueError('Não há imagem anterior para restaurar')
        target=BOOT/'releases'/previous
        verify(target)
        if root==BOOT: raise ValueError('Imagem atual sem identificador de release')
        activate(target,origin,root.name)
        return inventory(target,root.name)
    if shutil.disk_usage(WORK).free < 4*1024**3 + 4*(root/'filesystem.squashfs').stat().st_size:
        raise ValueError('Espaço livre insuficiente para descompactação e backup')
    with tempfile.TemporaryDirectory(prefix='build-',dir=WORK) as directory:
        directory=Path(directory); staged=directory/'root'
        progress('preparing',1,'Descompactando uma cópia da imagem. Os clientes atuais continuam funcionando.',**details)
        extract_image(root/'filesystem.squashfs',staged,log)
        if not (staged/'etc/debian_version').read_text().strip().startswith('12.'):
            raise ValueError('Esta atualização suporta a imagem Debian 12; mudança de distribuição exige nova compilação')
        if (staged/'var/lib/freethinclient-client/identity.json').exists():
            raise ValueError('A imagem contém identidade privada de cliente')
        package=None
        if job['action'] in ('chrome','citrix'):
            progress('updating',2,'Baixando e verificando o pacote do fornecedor oficial.',**details)
            package=directory/'vendor.deb'; download_package(job,package)
        progress('updating',2,'Atualizando os pacotes dentro da cópia da imagem.',**details)
        if job['action']=='client':
            client_lib=staged/'usr/local/lib/freethinclient';client_lib.mkdir(parents=True,exist_ok=True)
            assets=staged/'usr/share/freethinclient';assets.mkdir(parents=True,exist_ok=True)
            (staged/'etc/NetworkManager/conf.d').mkdir(parents=True,exist_ok=True)
            units=staged/'etc/systemd/system';units.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(BASE/'client/freethinclient-client.service',units/'freethinclient-client.service')
            for name in ('agent.py','session.py','device_info.py','launch_options.py','network.py','dns_config.py','remote.py'):
                shutil.copyfile(BASE/'client'/name,client_lib/name)
            autostart=staged/'etc/xdg/autostart';autostart.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(BASE/'client/freethinclient-info.desktop',autostart/'freethinclient-info.desktop')
            policy=staged/'etc/polkit-1/rules.d/49-freethinclient-power.rules'
            policy.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(BASE/'client/power.rules',policy)
            shutil.copyfile(BASE/'client/network.rules',policy.parent/'10-freethinclient-network.rules')
            shutil.copyfile(BASE/'client/kiosk.xml',assets/'kiosk.xml')
            shutil.copyfile(BASE/'client/boot-banner.txt',assets/'boot-banner.txt')
            for source,relative in [('initramfs-banner-hook','hooks'),('initramfs-banner','scripts/init-premount')]:
                destination=staged/'etc/initramfs-tools'/relative/'freethinclient-banner'
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(BASE/'client'/source,destination);destination.chmod(0o755)
            for name in ('blue-workspace','browser','remote','citrix','shutdown','restart','network'):
                run_command(['rsvg-convert','-o',str(assets/(name+'.png')),str(BASE/'web/assets'/(name+'.svg'))],log)
        args=['unshare','--mount','--fork','--kill-child','--propagation','private',sys.executable,'-B','-m','app.image_worker',
              '--chroot',str(staged),'--action',job['action']]
        if package: args+=['--package',str(package)]
        run_command(args,log,3600)
        kernel,initrd=newest_kernel(staged)
        image=directory/'output';image.mkdir()
        shutil.copyfile(kernel,image/'vmlinuz');shutil.copyfile(initrd,image/'initrd.img')
        progress('packing',3,'Compactando a nova imagem Linux.',**details)
        run_command(['mksquashfs',str(staged),str(image/'filesystem.squashfs'),'-noappend','-comp','xz'],log)
        progress('publishing',4,'Verificando arquivos e preparando a publicação.',**details)
        old=root if root!=BOOT else copy_release(root,secrets.token_hex(12))
        target=copy_release(image,job['id'])
        verify(target)
        next_details=inventory(target,old.name)
        activate(target,origin,old.name)
        return next_details


def run():
    import fcntl
    if not CONTROL.exists(): return
    WORK.mkdir(parents=True,exist_ok=True)
    BOOT.mkdir(parents=True,exist_ok=True)
    with (INSTALL/'update.lock').open('r') as app_lock, (BOOT/'client-image.lock').open('a') as lock:
        try:
            fcntl.flock(app_lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return
        cleanup_staging()
        actor='system';job={}
        status_path=WORK/'status.json';log=WORK/'job.log'
        def progress(state,step,message,**details):
            old_status=json.loads(status_path.read_text()) if status_path.exists() else {}
            details={**{key:old_status[key] for key in ('versions','image','rollback_available') if key in old_status},**details}
            atomic_json(status_path,{'state':state,'step':step,'message':message,'id':job.get('id'),
                'actor':actor,'timestamp':int(time.time()),**details})
        try:
            if CONTROL.is_symlink() or CONTROL.stat().st_size>8192: raise ValueError('Solicitação inválida')
            fd=os.open(CONTROL,os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd) as source:
                content=source.read(8193)
            if len(content)>8192: raise ValueError('Solicitação maior que o limite')
            raw=json.loads(content)
            if not isinstance(raw,dict): raise ValueError('Solicitação inválida')
            validated=images.validate(raw)
            if not re.fullmatch('[a-f0-9]{24}',raw.get('id','')): raise ValueError('Identificador inválido')
            job={**validated,'id':raw['id']};actor=raw.get('actor','system')[:64]
            old=json.loads(status_path.read_text()) if status_path.exists() else {}
            if old.get('id')==job['id'] and old.get('state') in images.BUSY:
                raise ValueError('A tarefa anterior foi interrompida. Confira o log e solicite novamente.')
            log.write_text('Iniciando tarefa de imagem: '+job['action']+'\n')
            progress('preparing',0,'Conferindo a imagem publicada.')
            details=perform(job,progress,log)
            progress('done',5,'Consulta concluída.' if job['action']=='inspect' else 'Imagem publicada. Reinicie os clientes para carregar a nova versão.',**details)
            Store(STATE).audit(actor,'Imagem PXE: concluído '+job['action']+' / tarefa '+job['id'])
        except Exception as error:
            # Vendor URLs may contain signed tokens. Never echo exception URLs into the panel.
            message=str(error)[:300] if isinstance(error,ValueError) else 'Falha na tarefa: '+type(error).__name__+'. Consulte o log.'
            progress('error',0,message)
            if job: Store(STATE).audit(actor,'Imagem PXE: falha '+job['action']+' / tarefa '+job['id'])
        finally:
            CONTROL.unlink(missing_ok=True)


if __name__=='__main__':
    if len(sys.argv)>1:
        import argparse
        parser=argparse.ArgumentParser();parser.add_argument('--chroot',type=Path,required=True)
        parser.add_argument('--action',choices=('client','linux','chromium','chrome','citrix'),required=True)
        parser.add_argument('--package',type=Path)
        arguments=parser.parse_args()
        chroot_update(arguments.chroot,arguments.action,arguments.package)
    else: run()
