"""FastAPI application for local YOLO inference."""

from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .model import detect

app = FastAPI(
    title="Local YOLO Inference API",
    version="1.0.0",
    description="Local object detection with a pretrained Ultralytics YOLO model.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

EVALUATION_EXAMPLES = [
    {
        "id": "example-01",
        "filename": "street-bus.jpg",
        "title": "Міський автобус",
        "expected_objects": ["bus", "person", "traffic light"],
        "observed_errors": ["Можливий пропуск маленьких людей на дальньому плані"],
        "notes": "Перевіряє великі об'єкти та об'єкти різного масштабу.",
    },
    {
        "id": "example-02",
        "filename": "two-people.jpg",
        "title": "Двоє людей",
        "expected_objects": ["person"],
        "observed_errors": ["Можливе дублювання рамки при частковому перекритті"],
        "notes": "Корисний приклад для перевірки перекриття об'єктів.",
    },
    {
        "id": "example-03",
        "filename": "kitchen-bottle.jpg",
        "title": "Кухня з пляшкою",
        "expected_objects": ["bottle", "cup", "dining table"],
        "observed_errors": ["Неправильний клас для дрібного посуду"],
        "notes": "Перевіряє близькі за формою класи.",
    },
    {
        "id": "example-04",
        "filename": "dog-park.jpg",
        "title": "Собака в парку",
        "expected_objects": ["dog", "person", "bench"],
        "observed_errors": ["Пропуск лавки на складному фоні"],
        "notes": "Перевіряє тварину, людину та об'єкт фону.",
    },
    {
        "id": "example-05",
        "filename": "bicycle-road.jpg",
        "title": "Велосипед на дорозі",
        "expected_objects": ["bicycle", "person", "car"],
        "observed_errors": ["Хибне спрацювання на дорожніх знаках"],
        "notes": "Містить об'єкти різного розміру та контрасту.",
    },
    {
        "id": "example-06",
        "filename": "office-laptop.jpg",
        "title": "Робоче місце",
        "expected_objects": ["laptop", "keyboard", "mouse", "chair"],
        "observed_errors": ["Клавіатура може бути визначена як невідомий об'єкт"],
        "notes": "Порівнює точність для дрібних предметів на столі.",
    },
    {
        "id": "example-07",
        "filename": "cat-window.jpg",
        "title": "Кіт біля вікна",
        "expected_objects": ["cat", "chair"],
        "observed_errors": ["Пропуск частково освітленої тварини"],
        "notes": "Показує вплив освітлення та порога confidence.",
    },
]


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/inference")
async def run_inference(
    file: Annotated[UploadFile, File(...)],
    confidence_threshold: Annotated[float, Form(0.25)] = 0.25,
) -> dict:
    if not 0 <= confidence_threshold <= 1:
        raise HTTPException(
            status_code=400,
            detail="Поріг confidence має бути від 0 до 1",
        )
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не має назви")
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Потрібно завантажити зображення")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Завантажений файл порожній")
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Максимальний розмір файлу — 20 МБ")

    try:
        result = detect(image_bytes, confidence_threshold)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Не вдалося виконати локальний inference",
        ) from exc

    return {
        "filename": file.filename,
        **result,
    }


@app.get("/api/evaluation/examples")
def list_evaluation_examples() -> list[dict]:
    return EVALUATION_EXAMPLES


@app.get("/api/evaluation/summary")
def get_evaluation_summary() -> dict[str, str | int]:
    return {
        "total_examples": len(EVALUATION_EXAMPLES),
        "prepared_examples": len(EVALUATION_EXAMPLES),
        "model_name": "yolov8n.pt",
        "evaluation_note": (
            "Набір містить сім прикладів із відомим очікуваним вмістом. "
            "Після запуску inference зафіксуйте пропуски, хибні спрацювання, "
            "неправильні класи та дублікати."
        ),
    }