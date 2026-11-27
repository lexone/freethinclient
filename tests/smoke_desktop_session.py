"""Exercise the real Xfce processes and launcher trust on an isolated HOME/X display."""
import hashlib
import importlib.util
import os
import sys
from pathlib import Path
import subprocess
import tempfile
import time

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
spec=importlib.util.spec_from_file_location('session',BASE/'client/session.py')
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)
assert 'ftc-xfce-test-' in str(Path.home()),'Use a disposable HOME'
assets=Path.home()/'assets';assets.mkdir()
for name in ('blue-workspace','browser','remote','citrix','shutdown','restart','network'):
    subprocess.run(['rsvg-convert','-o',str(assets/(name+'.png')),str(BASE/'web/assets'/(name+'.svg'))],check=True)
session.ASSETS=assets
profile={'approved':True,'mode':'desktop','show_shutdown':True,'show_restart':True,'show_browser':True,'show_panel':True,'allow_network_settings':True}
try:
    assert session.apply_desktop(profile)
    desktop=session.desktop_directory()
    for name in ('browser','shutdown','restart','network'):
        file=desktop/(name+'.desktop')
        assert file.is_file(),file
        digest=hashlib.sha256(file.read_bytes()).hexdigest()
        result=subprocess.run(['gio','info','-a','metadata::xfce-exe-checksum',str(file)],check=True,capture_output=True,text=True)
        assert digest in result.stdout,result.stdout
    session.session_shell({**profile,'allow_network_settings':False})
    time.sleep(2)
    for name in ('xfdesktop','xfce4-panel'):
        subprocess.run(['pgrep','-u',str(os.getuid()),'-x',name],check=True)
    # Reapply while both real components are running: they must restart cleanly.
    profile.update(show_shutdown=False,show_restart=False,allow_network_settings=False)
    assert session.apply_desktop(profile)
    session.session_shell({**profile,'allow_network_settings':False})
    time.sleep(2)
    assert not (desktop/'network.desktop').exists()
    assert not (desktop/'shutdown.desktop').exists()
    assert not (desktop/'restart.desktop').exists()
    for name in ('xfdesktop','xfce4-panel'):
        subprocess.run(['pgrep','-u',str(os.getuid()),'-x',name],check=True)
    print('Real Xfce smoke passed: launcher creation/trust, live reapply and desktop/panel restart')
finally:
    session.stop_component('xfdesktop');session.stop_component('xfce4-panel')
