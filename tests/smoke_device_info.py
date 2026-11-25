"""Start the actual GTK widget on a disposable X display and verify kiosk hiding."""
import importlib.util
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
spec=importlib.util.spec_from_file_location('device_info',Path(__file__).parents[1]/'client/device_info.py')
widget=importlib.util.module_from_spec(spec);spec.loader.exec_module(widget)
profile={'device_name':'LAB-01','mode':'desktop'}
widget.read_profile=lambda:profile
widget.current_ip=lambda:'10.9.2.194'
errors=[]


def check_visible():
    try:
        window=next(w for w in Gtk.Window.list_toplevels() if w.get_name()=='ftc-device-info')
        assert window.get_visible()
        assert 'LAB-01' in window.get_child().get_text()
        assert '10.9.2.194' in window.get_child().get_text()
        assert not window.get_accept_focus()
        assert window.get_skip_taskbar_hint()
        profile['mode']='kiosk'
    except Exception as error:
        errors.append(error)
    return False


def finish():
    try:
        window=next(w for w in Gtk.Window.list_toplevels() if w.get_name()=='ftc-device-info')
        assert not window.get_visible(),'Kiosk must hide the identity card'
    except Exception as error:
        errors.append(error)
    Gtk.main_quit();return False


GLib.timeout_add(500,check_visible)
GLib.timeout_add(7000,finish)
widget.main()
if errors: raise AssertionError(errors)
print('GTK device information smoke passed: caption, focus, taskbar and kiosk hiding')
