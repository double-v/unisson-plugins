"""Un faux ntfy : un vrai serveur HTTP sur 127.0.0.1, qui garde ce qu'il
reçoit et répond comme ntfy (200 et l'écho JSON du message publié, 401 sans
le bon jeton, ou le code qu'on lui impose)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ID = "ntfy"
ENTETES = {"Host": "localhost", "Origin": "http://localhost"}


class FauxNtfy:
    def __init__(self, *, jeton: str | None = None):
        self.recus: list[dict] = []
        self.jeton = jeton
        self.statut_force: int | None = None
        faux = self

        class Gestion(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_POST(self):
                longueur = int(self.headers.get("Content-Length") or 0)
                brut = self.rfile.read(longueur)
                if faux.statut_force:
                    return self._repondre(faux.statut_force, {"error": "imposé par le test"})
                if faux.jeton and self.headers.get("Authorization") != f"Bearer {faux.jeton}":
                    return self._repondre(401, {"code": 40101, "http": 401, "error": "unauthorized"})
                try:
                    donnees = json.loads(brut)
                except ValueError:
                    return self._repondre(400, {"code": 40001, "error": "invalid request"})
                faux.recus.append({"chemin": self.path, "json": donnees, "auth": self.headers.get("Authorization")})
                return self._repondre(200, {"id": f"m{len(faux.recus)}", "event": "message", **donnees})

            def _repondre(self, code, corps):
                data = json.dumps(corps).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self._serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestion)
        self.url = f"http://127.0.0.1:{self._serveur.server_address[1]}"
        self._fil = threading.Thread(target=self._serveur.serve_forever, daemon=True)
        self._fil.start()

    def fermer(self) -> None:
        self._serveur.shutdown()
        self._serveur.server_close()


def port_ferme() -> str:
    """Une adresse où personne n'écoute : un port pris puis rendu."""
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"
