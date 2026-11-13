"""A tiny SMTP server for tests. It listens on 127.0.0.1 only and keeps every message it accepts.

Modes: "ok" accepts mail, "temp_fail" answers 451 to MAIL, "perm_fail" answers 550 to RCPT,
"drop" closes the connection right after the greeting.
"""
import base64
import socketserver
import threading
from typing import List, Optional, Tuple


class _Handler(socketserver.StreamRequestHandler):
    def _send(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("utf-8"))
        self.wfile.flush()

    def _line(self) -> Optional[str]:
        raw = self.rfile.readline()
        if not raw:
            return None
        return raw.decode("utf-8", "replace").rstrip("\r\n")

    def handle(self) -> None:
        srv: "FakeSMTP" = self.server.owner  # type: ignore[attr-defined]
        srv.connections += 1
        if srv.mode == "drop":
            return
        self._send("220 fake.test ESMTP ready")
        mail_from = ""
        rcpts: List[str] = []
        while True:
            line = self._line()
            if line is None:
                return
            cmd = line.upper()
            if cmd.startswith(("EHLO", "HELO")):
                self.wfile.write(b"250-fake.test\r\n250-8BITMIME\r\n250 AUTH PLAIN LOGIN\r\n")
                self.wfile.flush()
            elif cmd.startswith("AUTH"):
                parts = line.split(None, 2)
                token = parts[2] if len(parts) > 2 else None
                if token is None:
                    self._send("334 ")
                    token = self._line() or ""
                try:
                    pieces = base64.b64decode(token).split(b"\0")
                    srv.auth_users.append(pieces[1].decode() if len(pieces) > 1 else "")
                except Exception:
                    pass
                self._send("235 2.7.0 Authentication successful")
            elif cmd.startswith("MAIL FROM"):
                if srv.mode == "temp_fail":
                    self._send("451 4.3.0 Try again later")
                    continue
                mail_from = line.split(":", 1)[1].strip().split()[0].strip("<>")
                rcpts = []
                self._send("250 OK")
            elif cmd.startswith("RCPT TO"):
                if srv.mode == "perm_fail":
                    self._send("550 5.1.1 No such user")
                    continue
                rcpts.append(line.split(":", 1)[1].strip().split()[0].strip("<>"))
                self._send("250 OK")
            elif cmd == "DATA":
                self._send("354 End data with <CR><LF>.<CR><LF>")
                chunks: List[bytes] = []
                while True:
                    raw = self.rfile.readline()
                    if not raw:
                        return
                    if raw.rstrip(b"\r\n") == b".":
                        break
                    chunks.append(raw[1:] if raw.startswith(b"..") else raw)
                srv.messages.append((mail_from, list(rcpts), b"".join(chunks)))
                self._send("250 OK queued")
            elif cmd.startswith("RSET"):
                mail_from, rcpts = "", []
                self._send("250 OK")
            elif cmd.startswith("NOOP"):
                self._send("250 OK")
            elif cmd.startswith("QUIT"):
                self._send("221 Bye")
                return
            else:
                self._send("502 Command not implemented")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class FakeSMTP:
    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.messages: List[Tuple[str, List[str], bytes]] = []
        self.auth_users: List[str] = []
        self.connections = 0
        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._server.owner = self  # type: ignore[attr-defined]
        self.port: int = self._server.server_address[1]
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "FakeSMTP":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
