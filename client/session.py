#!/usr/bin/env python3
"""Unprivileged desktop/session supervisor for Blue Workspace."""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

PROFILE = Path('/var/lib/freethinclient-client/profile.json')
ASSETS = Path('/usr/share/freethinclient')
HOME = Path.home()


def call(args):
    return subprocess.run(args, capture_output=True, timeout=10, check=False)


def xfconf(channel, prop, value, kind='string'):
    call(['xfconf-query', '-c', channel, '-p', prop, '--create', '-t', kind, '-s', str(value)])


def desktop_file(name, title, icon, action):
    path = HOME / 'Desktop' / (name + '.desktop')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[Desktop Entry]\nType=Application\nName=' + title + '\nIcon=' + str(ASSETS / icon) +
                    '\nExec=/usr/bin/python3 /usr/local/lib/freethinclient/session.py --launch ' + action + '\nTerminal=false\n')
    path.chmod(0o700)
    call(['gio', 'set', str(path), 'metadata::trusted', 'true'])


def application(profile, mode):
    browser = shutil.which('google-chrome') or shutil.which('chromium')
    if mode in ('browser', 'kiosk', 'citrix'):
        if not browser:
            return None
        url = profile.get('citrix_url') if mode == 'citrix' else profile.get('homepage')
        if not url:
            return None
        # ICA downloads open through the Citrix package's MIME handler when installed.
        args = [browser, '--no-first-run', '--disable-session-crashed-bubble']
        if mode == 'kiosk':
            args += ['--kiosk', '--incognito']
        return args + [url]
    if mode == 'rdp' and profile.get('rdp_host'):
        args = ['xfreerdp', '/v:' + profile['rdp_host'], '/f', '/dynamic-resolution', '/sound', '/microphone', '/cert:deny']
        if profile.get('rdp_domain'):
            args += ['/d:' + profile['rdp_domain']]
        # Password is prompted by FreeRDP; certificate validation remains enabled.
        return args
    return None


def launch(profile, mode):
    args = application(profile, mode)
    if not args:
        return None
    if mode == 'rdp':
        dialog = subprocess.run(['zenity', '--forms', '--title=Conectar à área remota', '--text=Entre com sua conta Windows',
                       '--add-entry=Usuário', '--add-password=Senha', '--separator=\n'], capture_output=True, check=False)
        if dialog.returncode:
            return None
        fields = dialog.stdout.decode().rstrip('\n').split('\n')
        if len(fields) != 2 or not fields[0]:
            return None
        args += ['/u:' + fields[0], '/from-stdin:force']
        child = subprocess.Popen(args, stdin=subprocess.PIPE)
        child.stdin.write((fields[1] + '\n').encode())
        child.stdin.close()
        return child
    return subprocess.Popen(args)


def apply_wallpaper(profile):
    wallpaper = profile.get('wallpaper_path', str(ASSETS / 'blue-workspace.svg'))
    result = call(['xfconf-query', '-c', 'xfce4-desktop', '-l'])
    for key in result.stdout.decode().splitlines():
        if key.endswith('/last-image'):
            xfconf('xfce4-desktop', key, wallpaper)


def apply_desktop(profile):
    apply_wallpaper(profile)
    xfconf('xsettings', '/Net/ThemeName', 'Adwaita-dark')
    xfconf('xsettings', '/Net/IconThemeName', 'Papirus-Dark')
    xfconf('xsettings', '/Gtk/FontName', 'Noto Sans 10')
    xfconf('thunar-volman', '/automount-drives/enabled', str(profile.get('allow_usb', False)).lower(), 'bool')
    xfconf('thunar-volman', '/automount-media/enabled', str(profile.get('allow_usb', False)).lower(), 'bool')
    desktop_file('browser', 'Navegador', 'browser.svg', 'browser')
    for name, title, icon, mode, enabled in (
            ('remote', 'Área remota', 'remote.svg', 'rdp', profile.get('rdp_host')),
            ('citrix', 'Citrix', 'citrix.svg', 'citrix', profile.get('citrix_url'))):
        if enabled:
            desktop_file(name, title, icon, mode)
        else:
            (HOME / 'Desktop' / (name + '.desktop')).unlink(missing_ok=True)


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
    apply_desktop({})
    while True:
        profile = read_profile()
        if not profile.get('approved'):
            if child and child.poll() is None:
                child.terminate()
            if not waiting or waiting.poll() is not None:
                waiting = subprocess.Popen(['zenity', '--info', '--title=FreeThinClient', '--width=480',
                    '--text=Conectando ao seu ambiente…\n\nAguarde o cadastro e a aprovação desta máquina no painel.'])
            time.sleep(5)
            continue
        if waiting and waiting.poll() is None:
            waiting.terminate()
        revision = profile.get('revision', '')
        if revision != previous:
            if child and child.poll() is None:
                child.terminate()
            # Changing kiosk / desktop requires a new LightDM session.
            # The root agent never accepts arbitrary shell commands.
            mode = profile.get('mode', 'desktop')
            previous = revision
            apply_desktop(profile)
            if mode == 'kiosk':
                call(['xfce4-panel', '--quit'])
                call(['pkill', '-u', str(os.getuid()), '-x', 'xfdesktop'])
                call(['pkill', '-u', str(os.getuid()), '-x', 'xfsettingsd'])
                subprocess.Popen(['openbox', '--replace', '--config-file', str(ASSETS / 'kiosk.xml')],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if call(['pgrep', '-u', str(os.getuid()), '-x', 'xfwm4']).returncode:
                    subprocess.Popen(['xfwm4', '--replace'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if call(['pgrep', '-u', str(os.getuid()), '-x', 'xfsettingsd']).returncode:
                    subprocess.Popen(['xfsettingsd'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for executable in ('xfdesktop', 'xfce4-panel'):
                    if call(['pgrep', '-u', str(os.getuid()), '-x', executable]).returncode:
                        subprocess.Popen([executable], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            child = launch(profile, mode)
        elif child and child.poll() is not None and profile.get('reconnect'):
            time.sleep(3)
            child = launch(profile, mode)
        if profile.get('lock_wallpaper') and mode != 'kiosk':
            apply_wallpaper(profile)
        time.sleep(3)


if __name__ == '__main__':
    main()
