import socket
import threading
import subprocess
import os
import struct
import sys
import time
import requests  # pip install requests
from io import BytesIO
from PIL import ImageGrab
import pyautogui

# Настройки сервера
HOST = 'localhost'     # IP-адрес сервера
PORT = 5000               # Порт
PASSWORD = 'StrongPassword123'

# URL для автообновления (raw-ссылка на server.py)
UPDATE_URL = (
    'https://gist.githubusercontent.com/Dimonlomon/f52cb1bc8e8779181445b868e391cb4b/raw/server.py'
)
CHECK_INTERVAL = 300  # проверка каждые 300 секунд

# --- Отправка/приём данных с префиксом длины ---
def send_data(conn, data: bytes):
    conn.sendall(struct.pack('>I', len(data)))
    conn.sendall(data)

def recv_data(conn) -> bytes:
    raw_len = conn.recv(4)
    if not raw_len:
        return b''
    length = struct.unpack('>I', raw_len)[0]
    data = b''
    while len(data) < length:
        packet = conn.recv(length - len(data))
        if not packet:
            break
        data += packet
    return data

# Функция автообновления
def auto_update():
    while True:
        try:
            print('[*] Checking for update...')
            r = requests.get(UPDATE_URL, timeout=10)
            if r.status_code == 200:
                remote_code = r.text
                local_path = os.path.realpath(__file__)
                with open(local_path, 'r', encoding='utf-8') as f:
                    local_code = f.read()
                if remote_code != local_code:
                    print('[*] New version detected. Updating...')
                    backup = local_path + '.bak'
                    os.replace(local_path, backup)
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(remote_code)
                    print('[*] Restarting server...')
                    os.execv(sys.executable, [sys.executable, local_path])
                else:
                    print('[*] Already up-to-date.')
            else:
                print(f'[!] Update check failed: HTTP {r.status_code}')
        except Exception as e:
            print(f'[!] Auto-update error: {e}')
        time.sleep(CHECK_INTERVAL)

# Обработчик клиента
def handle_client(conn, addr):
    print(f'[+] Connected by {addr}')
    try:
        send_data(conn, b'PASSWORD:')
        pwd = recv_data(conn).decode()
        if pwd != PASSWORD:
            send_data(conn, b'ACCESS DENIED')
            return
        send_data(conn, b'ACCESS GRANTED')
        while True:
            cmd = recv_data(conn).decode()
            if not cmd or cmd.lower() in ('exit', 'quit'):
                break
            parts = cmd.split()
            action = parts[0].lower()

            if action == 'ls':
                path = ' '.join(parts[1:]) or '.'
                try:
                    files = os.listdir(path)
                    send_data(conn, '\n'.join(files).encode())
                except Exception as e:
                    send_data(conn, f'ERROR: {e}'.encode())

            elif action == 'screenshot':
                img = ImageGrab.grab()
                buf = BytesIO()
                img.save(buf, format='PNG')
                send_data(conn, buf.getvalue())

            elif action == 'mouse_move':
                try:
                    x, y = map(int, parts[1:3])
                    pyautogui.moveTo(x, y)
                    send_data(conn, b'OK')
                except Exception as e:
                    send_data(conn, f'ERROR: {e}'.encode())

            elif action == 'mouse_click':
                try:
                    button = parts[1] if len(parts) > 1 else 'left'
                    clicks = int(parts[2]) if len(parts) > 2 else 1
                    pyautogui.click(button=button, clicks=clicks)
                    send_data(conn, b'OK')
                except Exception as e:
                    send_data(conn, f'ERROR: {e}'.encode())

            elif action == 'key_press':
                try:
                    pyautogui.press(parts[1])
                    send_data(conn, b'OK')
                except Exception as e:
                    send_data(conn, f'ERROR: {e}'.encode())

            elif action == 'key_write':
                try:
                    text = cmd[len('key_write'):].strip()
                    pyautogui.write(text)
                    send_data(conn, b'OK')
                except Exception as e:
                    send_data(conn, f'ERROR: {e}'.encode())

            else:
                try:
                    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
                except subprocess.CalledProcessError as e:
                    out = e.output
                send_data(conn, out)

    except Exception as e:
        print(f'Client handler error: {e}')
    finally:
        conn.close()
        print(f'[-] Disconnected {addr}')

# Запуск сервера
def start_server():
    # Запускаем автообновление в фоне
    threading.Thread(target=auto_update, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f'Listening on {HOST}:{PORT}...')
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    start_server()

