"""Shared validation for arguments passed directly to supported applications."""
import re
import shlex
from urllib.parse import urlsplit

WINDOW_MODES = ('inherit', 'window', 'fullscreen', 'kiosk')
BROWSER_FLAGS = {'--incognito', '--disable-gpu', '--disable-dev-shm-usage',
                 '--disable-pinch', '--start-maximized', '--kiosk-printing'}
RDP_FLAGS = {'/multimon', '/span', '+clipboard', '-clipboard', '/clipboard',
             '/dynamic-resolution', '+dynamic-resolution', '-dynamic-resolution',
             '/smart-sizing', '/sound', '/microphone', '+fonts', '-fonts',
             '+compression', '-compression', '+wallpaper', '-wallpaper',
             '/auto-reconnect'}


def rdp_host(value):
    return isinstance(value,str) and bool(re.fullmatch(r'(?:[A-Za-z0-9][A-Za-z0-9.:[\]_-]{0,252}|\[[0-9A-Fa-f:]+\](?::[0-9]{1,5})?)', value))


def arguments(value, app):
    if not isinstance(value,str) or len(value)>1024 or any(ord(c)<32 for c in value):
        raise ValueError('Parâmetros inválidos: use uma única linha de até 1024 caracteres')
    try:
        tokens=shlex.split(value)
    except ValueError:
        raise ValueError('Aspas não fechadas nos parâmetros') from None
    if len(tokens)>24:
        raise ValueError('Use no máximo 24 parâmetros por aplicativo')
    for token in tokens:
        valid=False
        if app in ('browser','citrix'):
            valid=token in BROWSER_FLAGS or bool(re.fullmatch(
                r'--(?:window-size=\d{2,5},\d{2,5}|window-position=-?\d{1,5},-?\d{1,5}|lang=[A-Za-z-]{2,20}|overscroll-history-navigation=0)',token))
            if token.startswith('--force-device-scale-factor='):
                try: valid=0.5<=float(token.split('=',1)[1])<=3
                except ValueError: pass
            if token.startswith('--proxy-server='):
                address=token.split('=',1)[1]
                url=urlsplit(address if '://' in address else 'http://'+address)
                try:
                    valid=(url.scheme in ('http','https','socks4','socks5') and bool(url.hostname)
                           and not url.username and not url.password and url.path in ('','/')
                           and not url.query and not url.fragment and url.port is not None)
                except ValueError: valid=False
            if token.startswith('--proxy-bypass-list='):
                valid=bool(re.fullmatch(r'--proxy-bypass-list=[A-Za-z0-9*.;:<>,/_-]{1,256}',token))
        elif app=='rdp':
            valid=token in RDP_FLAGS or bool(re.fullmatch(
                r'/(?:size:\d{2,5}x\d{2,5}|bpp:(?:16|24|32)|network:(?:modem|broadband|broadband-low|broadband-high|wan|lan|auto)|scale:(?:100|140|180)|timeout:[1-9]\d{0,2})',token))
        if not valid:
            raise ValueError('Parâmetro não permitido para '+app+': '+token[:80])
    return tokens


def window_mode(profile, app):
    mode=profile.get(app+'_window_mode','inherit')
    if mode not in WINDOW_MODES:
        raise ValueError('Modo de abertura inválido')
    if mode=='inherit':
        return 'fullscreen' if profile.get('fullscreen') or app=='rdp' else 'window'
    return mode
