"""Punto de entrada: servidor HTTP único para frontend y API."""
import os, sys, threading, time
from http.server import ThreadingHTTPServer
from .api.routes import Handler
from . import state


def idle_watchdog():
    while True:
        time.sleep(15)
        if state.IDLE:
            continue
        if time.time() - state.LAST_ACTIVITY > state.IDLE_MINUTES * 60:
            state.IDLE = True
            print(f"[inactividad] Sin uso por {state.IDLE_MINUTES} min. Servicio detenido; "
                  "reactívalo desde la página o ejecuta iniciar.bat.", flush=True)


def main():
    threading.Thread(target=idle_watchdog, daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8502
    host = os.environ.get("HOST", "127.0.0.1")
    if sys.stdout:
        print(f"Frontend en http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
