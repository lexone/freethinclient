#!/usr/bin/env python3
"""Unprivileged, non-interactive desktop identity card; no credentials are displayed."""
import json
import socket
import subprocess
from pathlib import Path

PROFILE=Path('/var/lib/freethinclient-client/profile.json')


def read_profile():
    try:
        data=json.loads(PROFILE.read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):
        return {}


def current_ip():
    def ip(*args):
        return json.loads(subprocess.run(['ip','-json',*args],check=True,capture_output=True,text=True,timeout=3).stdout)
    try:
        routes=ip('route','show','default')
        args=['address','show']
        if routes:
            args+=['dev',sorted(routes,key=lambda row:row.get('metric',0))[0]['dev']]
        args+=['scope','global']
        for interface in ip(*args):
            for address in interface.get('addr_info',[]):
                if address.get('family')=='inet': return address['local']
    except (OSError,ValueError,subprocess.SubprocessError,KeyError):
        pass
    return 'Sem IPv4'


def visible(profile):
    return profile.get('mode')!='kiosk' and profile.get('show_device_info',True)


def caption(profile, address):
    name=profile.get('device_name') or socket.gethostname()
    return 'Máquina: '+str(name)+'\nIP: '+address


def main():
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,Gdk,GLib,Pango
    window=Gtk.Window(title='FreeThinClient — Identificação')
    window.set_name('ftc-device-info')
    window.set_decorated(False);window.set_resizable(False)
    window.set_accept_focus(False);window.set_focus_on_map(False)
    window.set_skip_taskbar_hint(True);window.set_skip_pager_hint(True)
    # Normal/below stays above xfdesktop and below application windows.
    window.set_type_hint(Gdk.WindowTypeHint.NORMAL);window.set_keep_below(True);window.stick()
    visual=window.get_screen().get_rgba_visual()
    if visual: window.set_visual(visual)
    css=Gtk.CssProvider();css.load_from_data(b'#ftc-device-info {background-color:rgba(5,25,48,0.85);border:1px solid #315575;border-radius:9px;} #ftc-device-info label {color:#deefff;font:11pt "Noto Sans";padding:12px 16px;}')
    Gtk.StyleContext.add_provider_for_screen(window.get_screen(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    label=Gtk.Label();label.set_xalign(0);label.set_ellipsize(Pango.EllipsizeMode.END);label.set_max_width_chars(48)
    window.add(label)
    def update():
        profile=read_profile()
        if not visible(profile):
            window.hide();return True
        label.set_text(caption(profile,current_ip()))
        if not window.get_visible(): window.show_all()
        display=Gdk.Display.get_default()
        monitor=display.get_primary_monitor() or display.get_monitor(0)
        if monitor:
            area=monitor.get_workarea();width,height=window.get_size()
            window.move(area.x+20,max(area.y+20,area.y+area.height-height-20))
        return True
    update();GLib.timeout_add_seconds(5,update)
    window.connect('destroy',Gtk.main_quit)
    Gtk.main()


if __name__=='__main__':main()
