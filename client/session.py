#!/usr/bin/env python3
"""Unprivileged desktop/session supervisor for Blue Workspace."""
import json
import hashlib
import logging
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

PROFILE = Path('/var/lib/freethinclient-client/profile.json')
ASSETS = Path('/usr/share/freethinclient')
HOME = Path.home()


def call(args):
    try:
        return subprocess.run(args, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        logging.warning('Falha ao aplicar configuração: %s (%s)', args[0], type(error).__name__)
        return subprocess.CompletedProcess(args, 1, stdout=b'', stderr=b'')


def xfconf(channel, prop, value, kind='string'):
    call(['xfconf-query', '-c', channel, '-p', prop, '--create', '-t', kind, '-s', str(value)])


def desktop_file(name, title, icon, action):
    path = desktop_directory() / (name + '.desktop')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[Desktop Entry]\nType=Application\nName=' + title + '\nIcon=' + str(ASSETS / Path(icon).with_suffix('.png')) +
                    '\nExec=/usr/bin/python3 /usr/local/lib/freethinclient/session.py --launch ' + action + '\nTerminal=false\n')
    path.chmod(0o700)
    # XFCE uses a checksum of the exact launcher bytes, not GNOME metadata::trusted.
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    call(['gio', 'set', '-t', 'string', str(path), 'metadata::xfce-exe-checksum', digest])


def application(profile, mode):
    if mode.startswith('shortcut:'):
        if profile.get('mode')=='kiosk': return None
        identity=mode.removeprefix('shortcut:')
        item=next((item for item in profile.get('shortcuts',[]) if item.get('id')==identity and item.get('enabled',True)),None)
        if not item: return None
        profile={**profile,'homepage':item['url']}
        mode='browser'
    kiosk = mode == 'kiosk'
    if kiosk:
        mode = profile.get('kiosk_app', 'browser')
    browser = shutil.which('google-chrome') or shutil.which('chromium')
    if mode in ('browser', 'kiosk', 'citrix'):
        if not browser:
            return None
        url = profile.get('citrix_url') if mode == 'citrix' else profile.get('homepage')
        if not url:
            return None
        # ICA downloads open through the Citrix package's MIME handler when installed.
        args = [browser, '--no-first-run', '--disable-session-crashed-bubble']
        args += ['--user-data-dir=' + str(HOME / '.config' / 'freethinclient-browser')]
        if kiosk:
            args += ['--kiosk', '--incognito']
        elif profile.get('fullscreen'):
            args += ['--start-fullscreen']
        return args + [url]
    if mode == 'rdp' and profile.get('rdp_host'):
        args = ['xfreerdp', '/v:' + profile['rdp_host'], '/f', '/dynamic-resolution', '/sound', '/microphone', '/cert:deny']
        if profile.get('rdp_domain'):
            args += ['/d:' + profile['rdp_domain']]
        # Password is prompted by FreeRDP; certificate validation remains enabled.
        return args
    return None


def launch(profile, mode):
    if mode in ('shutdown','restart'):
        power_action(profile,mode)
        return None
    args = application(profile, mode)
    if not args:
        return None
    if mode == 'rdp' or (mode == 'kiosk' and profile.get('kiosk_app') == 'rdp'):
        dialog = subprocess.run(['zenity', '--forms', '--title=Conectar à área remota', '--text=Entre com sua conta Windows',
                       '--add-entry=Usuário', '--add-password=Senha', '--separator=\n'], capture_output=True, check=False)
        if dialog.returncode:
            return None
        fields = dialog.stdout.decode().rstrip('\n').split('\n')
        if len(fields) != 2 or not fields[0]:
            return None
        args += ['/u:' + fields[0], '/from-stdin:force']
        child = subprocess.Popen(args, stdin=subprocess.PIPE, start_new_session=True)
        child.stdin.write((fields[1] + '\n').encode())
        child.stdin.close()
        return child
    return subprocess.Popen(args, start_new_session=True)


def power_action(profile, action):
    option='show_shutdown' if action=='shutdown' else 'show_restart'
    if action not in ('shutdown','restart') or not profile.get('approved') or profile.get('mode')=='kiosk' or not profile.get(option,False):
        return
    title='Desligar' if action=='shutdown' else 'Reiniciar'
    if profile.get('confirm_power',True):
        reply=call(['zenity','--question','--title='+title,'--text='+title+' este computador? Salve seus arquivos antes de continuar.'])
        if reply.returncode: return
    result=call(['systemctl','--no-wall','poweroff' if action=='shutdown' else 'reboot'])
    if result.returncode:
        call(['zenity','--error','--title=FreeThinClient','--text=Não foi possível executar a ação. Consulte a administração.'])


def desktop_directory():
    # Follow XDG localization (Desktop or Área de trabalho), not a hardcoded directory.
    result = call(['xdg-user-dir', 'DESKTOP']) if shutil.which('xdg-user-dir') else None
    value = result.stdout.decode().strip() if result else ''
    path = Path(value) if value else HOME / 'Desktop'
    if not path.is_absolute() or path == HOME or HOME not in path.parents:
        path = HOME / 'Desktop'
        if shutil.which('xdg-user-dirs-update'):
            call(['xdg-user-dirs-update','--set','DESKTOP',str(path)])
    return path


def apply_wallpaper(profile):
    wallpaper = profile.get('wallpaper_path', str(ASSETS / 'blue-workspace.png'))
    result = call(['xfconf-query', '-c', 'xfce4-desktop', '-l'])
    keys = {key for key in result.stdout.decode().splitlines() if key.endswith('/last-image')}
    # XFCE defaults do not necessarily appear in xfconf until explicitly set.
    monitors = call(['xrandr', '--listactivemonitors']).stdout.decode().splitlines()[1:]
    names = {line.split()[-1] for line in monitors if line.split()}
    names.update(('0', 'VGA-1', 'eDP-1'))
    for name in names:
        for workspace in range(4):
            keys.add('/backdrop/screen0/monitor' + name + '/workspace' + str(workspace) + '/last-image')
    for key in sorted(keys):
        xfconf('xfce4-desktop', key, wallpaper)
        xfconf('xfce4-desktop', key.rsplit('/', 1)[0] + '/image-style', 5, 'int')


def xfconf_array(channel, prop, values, kind='int'):
    args = ['xfconf-query', '-c', channel, '-p', prop, '--create', '--force-array']
    for value in values:
        args += ['-t', kind, '-s', str(value)]
    call(args)


def stop_component(name):
    if name not in ('xfdesktop','xfce4-panel'):
        raise ValueError('Componente inválido')
    call([name,'--quit'])
    if os.name!='posix': return True
    args=['pgrep','-u',str(os.getuid()),'-x',name]
    for _ in range(20):
        if call(args).returncode: return True
        time.sleep(0.05)
    call(['pkill','-TERM','-u',str(os.getuid()),'-x',name])
    for _ in range(20):
        if call(args).returncode: return True
        time.sleep(0.05)
    logging.warning('Componente ainda ativo: %s; aplicação será tentada novamente.',name)
    return False


def apply_panel():
    # One full-width bottom bar instead of the default top panel and launcher dock.
    xfconf('xfce4-panel','/configver',2,'int')
    xfconf_array('xfce4-panel', '/panels', [1])
    for prop, value, kind in [('position', 'p=10;x=0;y=0', 'string'), ('size', 38, 'uint'),
                              ('length', 100, 'uint'), ('length-adjust', 'false', 'bool'),
                              ('position-locked', 'true', 'bool')]:
        xfconf('xfce4-panel', '/panels/panel-1/' + prop, value, kind)
    xfconf_array('xfce4-panel', '/panels/panel-1/plugin-ids', [101, 102, 103])
    for plugin, name in [(101, 'tasklist'), (102, 'separator'), (103, 'clock')]:
        xfconf('xfce4-panel', '/plugins/plugin-' + str(plugin), name)
    xfconf('xfce4-panel', '/plugins/plugin-102/expand', 'true', 'bool')
    xfconf('xfce4-panel', '/plugins/plugin-102/style', 0, 'uint')
    xfconf('xfce4-panel', '/plugins/plugin-103/digital-format', '%H:%M')
    xfconf('xfce4-panel', '/plugins/plugin-103/mode', 2, 'uint')
    css = HOME / '.config' / 'gtk-3.0' / 'gtk.css'
    css.parent.mkdir(parents=True, exist_ok=True)
    css.write_text('.xfce4-panel.background { background-color: #07182f; color: #c9e6ff; }\n')


def apply_desktop(profile):
    # Apply the icon catalog while xfdesktop is stopped. Creating/removing icons
    # concurrently with XFCE's initial scan can invalidate its icon objects.
    if not stop_component('xfdesktop') or not stop_component('xfce4-panel'):
        return False
    if shutil.which('xdg-user-dirs-update'):
        call(['xdg-user-dirs-update'])
    apply_wallpaper(profile)
    xfconf('xsettings', '/Net/ThemeName', 'Adwaita-dark')
    xfconf('xsettings', '/Net/IconThemeName', 'Papirus-Dark')
    xfconf('xsettings', '/Gtk/FontName', 'Noto Sans 10')
    system_icons = str(profile.get('show_system_icons', False)).lower()
    for key in ('show-home', 'show-filesystem', 'show-trash', 'show-removable',
                'show-device-removable', 'show-device-fixed', 'show-network-removable'):
        xfconf('xfce4-desktop', '/desktop-icons/file-icons/' + key, system_icons, 'bool')
    for key in ('show-desktop-menu', 'show-windowlist-menu'):
        xfconf('xfce4-desktop', '/desktop-menu/' + key, 'false', 'bool')
    xfconf('xfce4-desktop', '/desktop-icons/style', 2, 'int')
    xfconf('xfce4-desktop', '/desktop-icons/icon-size', 48, 'uint')
    xfconf('thunar-volman', '/automount-drives/enabled', str(profile.get('allow_usb', False)).lower(), 'bool')
    xfconf('thunar-volman', '/automount-media/enabled', str(profile.get('allow_usb', False)).lower(), 'bool')
    for name, title, icon, mode, enabled in (
            ('browser', profile.get('browser_title','Navegador'), 'browser.png', 'browser', profile.get('show_browser', True)),
            ('remote', profile.get('rdp_title','Área remota'), 'remote.png', 'rdp', profile.get('show_rdp', True) and profile.get('rdp_host')),
            ('citrix', profile.get('citrix_title','Citrix'), 'citrix.png', 'citrix', profile.get('show_citrix', True) and profile.get('citrix_url')),
            ('shutdown','Desligar','shutdown.png','shutdown',profile.get('show_shutdown',False)),
            ('restart','Reiniciar','restart.png','restart',profile.get('show_restart',False))):
        if enabled and profile.get('mode') != 'kiosk':
            desktop_file(name, title, icon, mode)
        else:
            # Only remove launchers managed by this application.
            for directory in {desktop_directory(), HOME / 'Desktop'}:
                (directory / (name + '.desktop')).unlink(missing_ok=True)
    active=set()
    for item in profile.get('shortcuts',[]):
        if item.get('enabled',True) and profile.get('mode')!='kiosk' and re.fullmatch('[a-f0-9]{12}',item.get('id','')):
            name='ftc-web-'+item['id'];active.add(name+'.desktop')
            desktop_file(name,item['name'],item.get('icon','browser')+'.png','shortcut:'+item['id'])
    for directory in {desktop_directory(),HOME/'Desktop'}:
        for file in directory.glob('ftc-web-*.desktop'):
            if file.name not in active: file.unlink(missing_ok=True)
    apply_panel()
    return True


def stop_child(child):
    if child and child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def session_shell(profile):
    if profile.get('mode') == 'kiosk':
        call(['xfce4-panel', '--quit'])
        call(['pkill', '-u', str(os.getuid()), '-x', 'xfdesktop'])
        subprocess.Popen(['openbox', '--replace', '--config-file', str(ASSETS / 'kiosk.xml')],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    if call(['pgrep', '-u', str(os.getuid()), '-x', 'xfwm4']).returncode:
        subprocess.Popen(['xfwm4', '--replace'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if call(['pgrep', '-u', str(os.getuid()), '-x', 'xfdesktop']).returncode:
        subprocess.Popen(['xfdesktop'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if profile.get('show_panel', True):
        if call(['pgrep', '-u', str(os.getuid()), '-x', 'xfce4-panel']).returncode:
            subprocess.Popen(['xfce4-panel'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        call(['xfce4-panel', '--quit'])


def read_profile():
    try:
        return json.loads(PROFILE.read_text())
    except (OSError, ValueError):
        return {'approved': False}


def main():
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == '--launch':
        profile = read_profile()
        if profile.get('approved'):
            child = launch(profile, sys.argv[2])
            if child:
                child.wait()
        return
    child, previous, mode = None, '', ''
    waiting = None
    pending_initialized=False
    while True:
        profile = read_profile()
        if not profile.get('approved'):
            stop_child(child)
            previous = ''
            if not pending_initialized:
                pending_initialized=apply_desktop({})
                if pending_initialized: session_shell({})
            if not waiting or waiting.poll() is not None:
                waiting = subprocess.Popen(['zenity', '--info', '--title=FreeThinClient', '--width=480',
                    '--text=Conectando ao seu ambiente…\n\nAguarde o cadastro e a aprovação desta máquina no painel.'])
            time.sleep(5)
            continue
        if waiting and waiting.poll() is None:
            waiting.terminate()
        pending_initialized=False
        revision = profile.get('revision', '')
        if revision != previous:
            stop_child(child)
            # The root agent never accepts arbitrary shell commands.
            mode = profile.get('mode', 'desktop')
            if apply_desktop(profile):
                session_shell(profile)
                previous = revision
                child = launch(profile, mode)
        elif child and child.poll() is not None and profile.get('reconnect'):
            time.sleep(3)
            child = launch(profile, mode)
        if profile.get('lock_wallpaper') and mode != 'kiosk':
            apply_wallpaper(profile)
        time.sleep(3)


if __name__ == '__main__':
    main()
