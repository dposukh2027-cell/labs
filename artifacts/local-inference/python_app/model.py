"""Model loading and local object detection.

The model is deliberately isolated from the HTTP layer.  ``load_model`` is
cached so the relatively expensive YOLO weights are loaded once per process
and then reused for every request.
"""

from functools import lru_cache
from io import BytesIO
from time import perf_counter
from typing import Any

from PIL import Image, UnidentifiedImageError
from ultralytics import YOLO

MODEL_NAME = "yolov8n.pt"


@lru_cache(maxsize=1)
def load_model() -> YOLO:
    """Load pretrained weights once and keep them in process memory."""
    return YOLO(MODEL_NAME)


def detect(image_bytes: bytes, confidence_threshold: float) -> dict[str, Any]:
    """Run local YOLO inference and return a JSON-serializable result."""
    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Файл не є коректним зображенням") from exc

    model = load_model()
    started_at = perf_counter()
    predictions = model.predict(
        source=image,
        conf=confidence_threshold,
        device="cpu",
        verbose=False,
    )
    inference_time_ms = (perf_counter() - started_at) * 1000

    detections: list[dict[str, Any]] = []
    if predictions:
        boxes = predictions[0].boxes
        names = predictions[0].names
        for box, confidence, class_id in zip(
            boxes.xyxy.cpu().tolist(),
            boxes.conf.cpu().tolist(),
            boxes.cls.cpu().tolist(),
        ):
            numeric_class_id = int(class_id)
            detections.append(
                {
                    "class_id": numeric_class_id,
                    "class_name": str(names[numeric_class_id]),
                    "confidence": round(float(confidence), 4),
                    "box": {
                        "x1": round(float(box[0]), 2),
                        "y1": round(float(box[1]), 2),
                        "x2": round(float(box[2]), 2),
                        "y2": round(float(box[3]), 2),
                    },
                }
            )

    return {
        "image_width": image.width,
        "image_height": image.height,
        "model_name": MODEL_NAME,
        "confidence_threshold": confidence_threshold,
        "inference_time_ms": round(inference_time_ms, 2),
        "detections": detections,
    }