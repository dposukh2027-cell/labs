"""Локальна вебпанель для запуску оцінювача PR12."""

import argparse
import json
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "eval" / "runs"
PAGE = ROOT / "web" / "index.html"
MAX_LOG_CHARS = 100_000
STATE_LOCK = threading.Lock()
STATE = {
    "running": False,
    "status": "idle",
    "output": "",
    "error": None,
    "run": None,
    "run_file": None,
}


def _append_output(text: str) -> None:
    with STATE_LOCK:
        STATE["output"] = (STATE["output"] + text)[-MAX_LOG_CHARS:]


def _run_process(command: list[str], output_path: Path) -> None:
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if process.stdout is not None:
            for line in process.stdout:
                _append_output(line)
        return_code = process.wait()
        run = None
        error = None
        if output_path.exists():
            try:
                run = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                error = f"Не вдалося прочитати файл результату: {exc}"
        if return_code != 0:
            error = error or f"Сценарій завершився з кодом {return_code}."
        with STATE_LOCK:
            STATE.update({
                "running": False,
                "status": "done" if return_code == 0 else "error",
                "error": error,
                "run": run,
                "run_file": str(output_path.relative_to(ROOT)) if output_path.exists() else None,
            })
    except OSError as exc:
        with STATE_LOCK:
            STATE.update({"running": False, "status": "error", "error": str(exc)})


class Handler(BaseHTTPRequestHandler):
    server_version = "PR12Local/1.0"

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, value: dict) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/":
            try:
                page = PAGE.read_bytes()
            except OSError:
                self._send(500, b"web/index.html not found", "text/plain; charset=utf-8")
                return
            self._send(200, page, "text/html; charset=utf-8")
            return
        if route == "/api/status":
            with STATE_LOCK:
                state = dict(STATE)
            self._send_json(200, state)
            return
        self._send_json(404, {"error": "Не знайдено"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/run":
            self._send_json(404, {"error": "Не знайдено"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 16_384:
                raise ValueError("Некоректний розмір запиту.")
            request = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": f"Некоректний запит: {exc}"})
            return
        if not isinstance(request, dict):
            self._send_json(400, {"error": "Очікується JSON-об'єкт із параметрами запуску."})
            return

        target = request.get("target")
        if target not in ("drafts", "agent"):
            self._send_json(400, {"error": "Оберіть drafts або agent."})
            return
        k = request.get("k", 1)
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= 3:
            self._send_json(400, {"error": "Кількість повторів має бути від 1 до 3."})
            return
        use_heldout = request.get("heldout", False)
        no_judge = request.get("no_judge", True)
        if not isinstance(use_heldout, bool) or not isinstance(no_judge, bool):
            self._send_json(400, {"error": "Параметри запуску мають неправильний формат."})
            return
        if use_heldout and target != "drafts":
            self._send_json(400, {"error": "Відкладений набір доступний лише для drafts."})
            return

        cases = "eval/cases/drafts.heldout.json" if use_heldout else f"eval/cases/{target}.json"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        output_path = RUNS_DIR / f"web-{target}-{stamp}.json"
        command = [
            sys.executable, "-u", str(ROOT / "eval" / "run.py"),
            "--target", target, "--cases", cases, "--k", str(k),
            "--label", "Вебпанель: чернетки PR11" if target == "drafts" else "Вебпанель: помічник PR8",
            "--out", str(output_path.relative_to(ROOT)),
        ]
        if no_judge:
            command.append("--no-judge")

        with STATE_LOCK:
            if STATE["running"]:
                self._send_json(409, {"error": "Прогін уже виконується."})
                return
            STATE.update({
                "running": True,
                "status": "running",
                "output": "",
                "error": None,
                "run": None,
                "run_file": None,
            })
        thread = threading.Thread(target=_run_process, args=(command, output_path), daemon=True)
        thread.start()
        self._send_json(202, {"status": "running"})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[web] {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000, help="локальний порт (типово 8000)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port має бути в діапазоні від 1 до 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"PR12 UI: http://127.0.0.1:{args.port}  (зупинити: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер зупинено.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
