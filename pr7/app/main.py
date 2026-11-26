"""Веб-рівень застосунку: сторінка розбору рахунків і JSON-ендпоінти.

Цей файл не знає ані як готується зображення, ані якою моделлю й за
якою інструкцією вилучено поля, ані якими правилами їх перевірено — усе
це в `app/images.py`, `app/llm.py`, `app/schema.py`, `app/rules.py` і
поєднується в `app/extraction.py`. Тут вирішується інше: що застосунок
приймає від сторінки, що віддає їй і з яким HTTP-статусом.

Запуск із папки pr7:

    uvicorn app.main:app --reload

Далі відкрийте http://127.0.0.1:8000
"""

from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import extraction

app = FastAPI(title="Розбір рахунків — ПР7")

INDEX_PAGE = Path(__file__).parent / "templates" / "index.html"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# Зразки віддаються як статичні файли, щоб сторінка могла їх показати й
# надіслати на розбір так само, як завантажений користувачем файл.
app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")


def result_to_dict(result: extraction.Result) -> dict:
    """Перетворити результат конвеєра на те, що піде на сторінку."""
    return {
        "decision": result.decision,
        "reasons": result.reasons,
        "document": result.document,
        "issues": [asdict(issue) for issue in result.issues],
        "image": result.image,
        "model": result.model,
        "elapsed": result.elapsed,
        "usage": result.usage,
    }


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    """Віддати сторінку."""
    return INDEX_PAGE.read_text(encoding="utf-8")


@app.get("/api/samples")
def api_samples() -> dict:
    """Перелік зразків за папками: `clean`, `degraded` і, якщо є, `own`."""
    groups = {}
    for folder in sorted(p for p in SAMPLES_DIR.iterdir() if p.is_dir()):
        files = sorted(f.name for f in folder.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES)
        if files:
            groups[folder.name] = files
    return groups


@app.post("/api/extract")
async def api_extract(image: UploadFile = File(...)) -> dict:
    """Розібрати документ і повернути поля, проблеми й рішення.

    Сторінка очікує обʼєкт із полями `decision`, `reasons`, `document`,
    `issues`, `image`, `model`, `elapsed`, `usage` — див. `result_to_dict`.

    Помилки підготовки зображення та запиту до моделі повертаються з
    поясненням і відповідним HTTP-статусом.
    """
    try:
        content = await image.read(extraction.MAX_UPLOAD_BYTES + 1)
        if len(content) > extraction.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Файл завеликий. Максимальний розмір — {extraction.MAX_UPLOAD_BYTES / (1024 * 1024):g} МБ.",
            )
        return result_to_dict(extraction.process(content))
    except extraction.ProcessingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        await image.close()
