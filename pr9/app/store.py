"""Сховище стану звернень: зберегти, прочитати, перелічити.

Стан живе поза памʼяттю процесу, бо звернення чекає на оператора
довше, ніж живе один процес застосунку. Модуль не знає ані про модель,
ані про магазин, ані про кроки workflow: він зберігає `Run` і
повертає його таким, яким зберіг.

Каталог — `RUNS_DIR` з `.env` (за замовчуванням `runs/` у папці
роботи). До репозиторію він не потрапляє: там тексти звернень клієнтів.

Функції нижче — заготовки. Рішення з розділу 2 практичної роботи:

* у чому зберігати: JSON-файл на звернення чи SQLite (`sqlite3` зі
  стандартної бібліотеки) — і що це змінює для переліку за статусом;
* як записувати, щоб збій посередині запису не лишив зіпсованого файлу;
* як перетворити `Run` на JSON і назад, разом зі списком `Step`;
* що робити, якщо два запити одночасно змінюють те саме звернення —
  наприклад, оператор двічі натиснув «підтвердити». Чи це справа
  сховища, чи workflow?
"""

import json
import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from .state import Run, Step

load_dotenv()

RUNS_DIR = Path(os.getenv("RUNS_DIR", "runs"))


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def save(run: Run) -> None:
    """Зберегти стан звернення, замінивши попередній."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = _run_path(run.run_id)
    payload = asdict(run)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load(run_id: str) -> Run | None:
    """Прочитати стан звернення; `None`, якщо такого немає."""
    path = _run_path(run_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = [Step(**step) for step in payload.get("steps", [])]
    payload["steps"] = steps
    return Run(**payload)


def list_runs(status: str | None = None) -> list[Run]:
    """Усі звернення, за потреби — лише з певним статусом; нові першими."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[Run] = []
    for path in sorted(RUNS_DIR.glob("*.json"), reverse=True):
        if path.name.endswith(".tmp"):
            continue
        run = load(path.stem)
        if run is None:
            continue
        if status is None or run.status == status:
            runs.append(run)
    return runs
