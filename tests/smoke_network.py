"""Exercise the GTK network window, diagnostics and live permission revocation."""
import importlib.util
from pathlib import Path
import gi

gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
spec=importlib.util.spec_from_file_location('network',Path(__file__).parents[1]/'client/network.py')
network=importlib.util.module_from_spec(spec);spec.loader.exec_module(network)
profile={'approved':True,'allow_network_settings':True}
network.read_profile=lambda:profile
network.diagnostics=lambda:'IP: 10.9.2.194\nDNS: teste concluído'
errors=[]


def walk(widget):
    yield widget
    if isinstance(widget,Gtk.Container):
        for child in widget.get_children(): yield from walk(child)


def start():
    try:
        window=next(w for w in Gtk.Window.list_toplevels() if w.get_title()=='Rede e Wi-Fi — FreeThinClient')
        assert window.get_visible()
        next(w for w in walk(window) if isinstance(w,Gtk.Button) and w.get_label()=='Executar diagnóstico').clicked()
    except Exception as error: errors.append(error)
    return False


def revoke():
    try:
        window=next(w for w in Gtk.Window.list_toplevels() if w.get_visible())
        view=next(w for w in walk(window) if isinstance(w,Gtk.TextView))
        buffer=view.get_buffer();assert '10.9.2.194' in buffer.get_text(*buffer.get_bounds(),True)
        profile['allow_network_settings']=False
    except Exception as error: errors.append(error)
    return False


def timeout():
    errors.append(AssertionError('Network window did not close after permission revocation'))
    Gtk.main_quit();return False


GLib.timeout_add(300,start)
GLib.timeout_add(800,revoke)
GLib.timeout_add(6000,timeout)
network.main()
assert not errors,errors
assert not any(w.get_visible() for w in Gtk.Window.list_toplevels())
print('GTK network controls passed: visible window, diagnostic feedback and live permission revocation')
