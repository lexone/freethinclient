#!/usr/bin/env python3
"""Unprivileged network controls and read-only diagnostics for the local seat."""
import json
import os
import socket
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

PROFILE=Path('/var/lib/freethinclient-client/profile.json')


def read_profile():
    try: return json.loads(PROFILE.read_text())
    except (OSError,ValueError): return {}


def permitted():
    profile=read_profile()
    return profile.get('approved') is True and profile.get('allow_network_settings') is True


def output(args):
    try:
        result=subprocess.run(args,capture_output=True,text=True,timeout=8,check=False,
                              env={**os.environ,'LC_ALL':'C'})
        return (result.stdout+result.stderr).strip() or '(sem saída)'
    except (OSError,subprocess.TimeoutExpired) as error:
        return 'Indisponível: '+type(error).__name__


def diagnostics():
    # No PSKs, passwords, saved connection details, or automatic route/DNS changes.
    sections=[('Conexões e placas', ['nmcli','device','status']),
              ('Estado do NetworkManager', ['nmcli','general','status']),
              ('Endereços IP', ['ip','-br','address']),
              ('Rotas', ['ip','route']),
              ('DNS e gateway por placa', ['nmcli','-f','GENERAL.DEVICE,IP4.GATEWAY,IP4.DNS,IP6.GATEWAY,IP6.DNS','device','show']),
              ('Bloqueios de Wi-Fi', ['/usr/sbin/rfkill','list'])]
    result=['DIAGNÓSTICO DE REDE — FreeThinClient']
    for label,args in sections: result += ['\n'+label+'\n'+output(args)]
    try: resolver=Path('/etc/resolv.conf').read_text()
    except OSError: resolver='Não foi possível ler /etc/resolv.conf'
    result+=['\nResolvedor do sistema\n'+resolver]
    address=read_profile().get('homepage') or 'https://www.google.com'
    host=urlsplit(address).hostname
    if host:
        result+=['\nTeste DNS: '+host]
        try:
            records=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            result+=['DNS OK: '+', '.join(sorted({row[4][0] for row in records}))]
            # Try a bounded set of returned IPv4/IPv6 addresses; no HTTP request or credentials.
            connected=False
            for family,kind,protocol,_,target in records[:4]:
                try:
                    with socket.socket(family,kind,protocol) as probe:
                        probe.settimeout(2);probe.connect(target)
                    connected=True;break
                except OSError: pass
            result+=['TCP 443: '+('acessível' if connected else 'não respondeu aos testes')]
            result+=['TCP acessível não confirma TLS, proxy ou login no portal.']
        except OSError as error: result+=['Falha de DNS: '+str(error)]
    return '\n'.join(result)


def open_tool(tool):
    # Polkit checks the current root-owned profile again when NM receives an action.
    if not permitted(): return
    commands={'editor':['nm-connection-editor'],
              'wifi':['xfce4-terminal','--disable-server','--title=Rede e Wi-Fi',
                      '--execute','nmtui-connect'],
              'enable-wifi':['nmcli','radio','wifi','on']}
    if tool in commands:
        try: return subprocess.Popen(commands[tool],start_new_session=True)
        except OSError: return None


def main():
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,GLib
    if not permitted(): return
    window=Gtk.Window(title='Rede e Wi-Fi — FreeThinClient')
    window.set_default_size(780,520)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);box.set_border_width(16)
    window.add(box)
    box.pack_start(Gtk.Label(label='Conecte por Wi-Fi ou edite IP, gateway e DNS. Alterar a conexão pode interromper o acesso ao servidor.',wrap=True),False,False,0)
    actions=Gtk.Box(spacing=8);box.pack_start(actions,False,False,0)
    for title,tool in [('Conectar rede / Wi-Fi','wifi'),('Ativar Wi-Fi','enable-wifi'),('Editar IP e DNS','editor')]:
        button=Gtk.Button(label=title);button.connect('clicked',lambda _,item=tool:open_tool(item));actions.pack_start(button,False,False,0)
    button=Gtk.Button(label='Executar diagnóstico');actions.pack_start(button,False,False,0)
    scroller=Gtk.ScrolledWindow();view=Gtk.TextView(editable=False,monospace=True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR);scroller.add(view);box.pack_start(scroller,True,True,0)
    buffer=view.get_buffer();buffer.set_text('Execute o diagnóstico para ver IP, gateway, DNS e conectividade.')
    def finish(text):
        buffer.set_text(text);button.set_sensitive(True);button.set_label('Executar diagnóstico')
        return False
    def worker():
        try: text=diagnostics()
        except Exception as error: text='Falha no diagnóstico: '+type(error).__name__
        GLib.idle_add(finish,text)
    def start(_):
        button.set_sensitive(False);button.set_label('Verificando…');buffer.set_text('Consultando placas, rotas e DNS…')
        threading.Thread(target=worker,daemon=True).start()
    button.connect('clicked',start)
    def check_permission():
        if not permitted(): window.destroy();return False
        return True
    GLib.timeout_add_seconds(3,check_permission)
    window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()


if __name__=='__main__': main()
