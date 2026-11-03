"""Windows desktop entry point used by the installer. Python is bundled."""
import os
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from irboard.server import create_server
from irboard.telemetry import Telemetry
from irboard.version import VERSION, DISPLAY_VERSION
from irboard.firewall import allow_private_lan
from irboard.updater import check_update, download_update, launch_installer


def main():
    # Windowed executables have no console. Keep server diagnostics in user data.
    if getattr(sys, 'frozen', False):
        directory = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'iR-Board'
        directory.mkdir(parents=True, exist_ok=True)
        log = open(directory / 'server.log', 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    root = tk.Tk()
    root.configure(background='#101216')
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), background='#101216', foreground='#f1f3f7')
    style.configure('TFrame', background='#101216')
    style.configure('TLabel', background='#101216', foreground='#f1f3f7')
    style.configure('TCheckbutton', background='#101216', foreground='#f1f3f7', padding=(0,6))
    style.map('TCheckbutton', background=[('active','#101216')], foreground=[('disabled','#8b94a4')])
    style.configure('TButton', background='#242a34', foreground='#f1f3f7', bordercolor='#343c49', padding=(12,10))
    style.map('TButton', background=[('active','#343c49'),('pressed','#343c49')], foreground=[('disabled','#7b8494')])
    style.configure('Accent.TButton', background='#c3f35c', foreground='#142006', bordercolor='#c3f35c')
    style.map('Accent.TButton', background=[('active','#d4ff7b'),('pressed','#a6d643')], foreground=[('disabled','#6b7657')])
    style.configure('Muted.TLabel', foreground='#a5adba')
    root.title(f'iR-Board {DISPLAY_VERSION}')
    root.geometry('600x760')
    try:
        root.iconbitmap(str(Path(__file__).parent / 'irboard/static/icon.ico'))
    except tk.TclError:
        pass
    root.resizable(False, False)
    if sys.platform == 'win32':
        try:
            import ctypes
            root.update_idletasks()
            from ctypes import wintypes
            parent = ctypes.windll.user32.GetParent
            parent.argtypes = [wintypes.HWND]
            parent.restype = wintypes.HWND
            window = parent(root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(window, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except (AttributeError, OSError):
            pass
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='iR-Board', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Your iRacing dashboard on any tablet.').pack(anchor='w', pady=(4, 16))
    status = tk.StringVar(value='Starting local server…')
    ttk.Label(frame, textvariable=status, wraplength=420).pack(anchor='w', pady=14)
    server = telemetry = None
    ready_update = None
    closing = False
    pairing_code = tk.StringVar(value='------')
    pairing_status = tk.StringVar(value='Tablet pairing code · preparing server…')
    ttk.Label(frame, textvariable=pairing_code, font=('Segoe UI', 27, 'bold')).pack(anchor='w')
    ttk.Label(frame, textvariable=pairing_status, style='Muted.TLabel', wraplength=530).pack(anchor='w', pady=(0, 10))

    def show_pairing_code():
        if closing:
            return
        if server:
            code = server.pairing.manual_code()
            pairing_code.set(code['code'])
            pairing_status.set(f'Tablet code · single use · expires in {code["expires_in"]} s. This computer does not need a code.')
        root.after(1000, show_pairing_code)

    def check_updates():
        update_button.state(['disabled'])
        update_status.set('Checking for updates…')
        def worker():
            try:
                update = check_update()
                if update and getattr(sys, 'frozen', False):
                    root.after(0, lambda: update_status.set(f'Downloading {update["tag"]}…'))
                    path, digest = download_update(update)
                    root.after(0, lambda: update_finished(f'{update["tag"]} is ready. Install when you finish driving.', (path,digest)))
                elif update:
                    root.after(0, lambda: update_finished('A new release is available. Install the Windows app for automatic downloads.'))
                else:
                    root.after(0, lambda: update_finished('You have the latest available version.'))
            except Exception:
                root.after(0, lambda: update_finished('Update check unavailable. Check your connection and public GitHub Releases.'))
        threading.Thread(target=worker, daemon=True).start()

    def update_finished(message, ready=None):
        nonlocal ready_update
        if closing:
            return
        ready_update = ready
        update_status.set(message)
        update_button.configure(text='Install downloaded update' if ready else 'Check for updates')
        update_button.state(['!disabled'])
        root.after(6*60*60*1000, check_updates)

    def open_connection():
        if server:
            webbrowser.open(server.connection_info['local_url']+'connect')

    def setup_network():
        if not messagebox.askokcancel('Allow tablet access',
                'Windows will ask for administrator permission to allow iR-Board on TCP port 8000. '
                'Only Private networks and devices on your local subnet are allowed. '
                'Use this only on your trusted home network. Public networks stay blocked.', parent=root):
            return
        network.state(['disabled'])
        status.set('Waiting for Windows permission to enable tablet access…')
        def worker():
            try:
                allow_private_lan()
                message = 'Firewall rule added. Set your trusted home network to Private in Windows Settings, then scan a fresh QR. Guest Wi-Fi isolation can also block tablets.'
            except Exception as exc:
                message = str(exc)
            root.after(0, lambda: finished(message))
        def finished(message):
            status.set(message)
            network.state(['!disabled'])
        threading.Thread(target=worker, daemon=True).start()

    def stop():
        nonlocal closing
        if closing:
            return
        install = bool(ready_update and messagebox.askyesno('Update ready',
            'A new version has been downloaded and its checksum verified. Close the dashboard and open the installer now?', parent=root))
        if install:
            try:
                launch_installer(*ready_update)
            except Exception as exc:
                messagebox.showerror('Update could not start', str(exc), parent=root)
                return
        closing = True
        if server:
            server.shutdown()
            server.server_close()
        if telemetry:
            telemetry.stop()
        root.destroy()

    def start():
        nonlocal server, telemetry
        telemetry = Telemetry(demo='--demo' in sys.argv)
        try:
            server = create_server('0.0.0.0', 8000, telemetry)
        except (OSError, ValueError) as exc:
            status.set('Cannot start the local server. Check whether port 8000 is in use.')
            messagebox.showerror('iR-Board could not start', f'{exc}\n\nClose another iR-Board instance or the Python server and restart.', parent=root)
            return
        telemetry.start()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        status.set(f'Running on port {server.server_port} · {"DEMO" if telemetry.demo else "iRacing SDK"}. Keep this window open while driving.')
        connect.state(['!disabled'])
        root.after(300, open_connection)

    connect = ttk.Button(frame, text='Show connection page and QR code', style='Accent.TButton', command=open_connection, state='disabled')
    connect.pack(fill='x', pady=(0, 10))
    network = ttk.Button(frame, text='Allow tablet access through Windows Firewall', command=setup_network)
    network.pack(fill='x', pady=(0, 10))
    ttk.Button(frame, text='Open Windows network settings', command=lambda: os.startfile('ms-settings:network-status')).pack(fill='x', pady=(0, 10))
    ttk.Button(frame, text='Stop server and quit', command=stop).pack(fill='x')
    update_status = tk.StringVar(value='Updates are checked automatically. Installation waits until you finish driving.')
    ttk.Label(frame, textvariable=update_status, style='Muted.TLabel', wraplength=480).pack(anchor='w', pady=(18,6))
    update_button = ttk.Button(frame, text='Check for updates', command=lambda: stop() if ready_update else check_updates())
    update_button.pack(fill='x')
    ttk.Label(frame, text='Private LAN only · Python is included in this installation.', wraplength=420).pack(anchor='w', pady=(12, 0))
    root.protocol('WM_DELETE_WINDOW', stop)
    root.after(150, start)
    root.after(300, show_pairing_code)
    root.after(3000, check_updates)
    root.mainloop()


if __name__ == '__main__':
    main()
