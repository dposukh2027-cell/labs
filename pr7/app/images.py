"""Підготовка зображення до надсилання моделі.

Файл, який надіслав користувач, — недовірені байти: це може бути не
зображення, зображення завбільшки 40 мегапікселів, фото, повернуте на
бік (орієнтація записана в EXIF, а не в пікселях), або знімок 300 × 200,
на якому цифр не розібрати. Модуль вирішує, що з цього можна віддати
моделі і в якому вигляді. Про модель він не знає: повертає підготовлені
байти й відомості про них, а як вкласти їх у запит — справа `app/llm.py`.

Функція `prepare` перевіряє вхідні байти, застосовує EXIF-орієнтацію,
обмежує роздільність і повертає PNG для надсилання моделі.
Рішення з розділу 2 практичної роботи:

* що вважати неприйнятним файлом і яку помилку повернути: не
  зображення, порожній файл, завеликий файл, завеликий у пікселях;
* чи враховувати орієнтацію з EXIF (фото з телефона);
* до якого розміру зменшувати і чи зменшувати взагалі — ціна зображення
  в токенах росте з роздільністю, а дрібний шрифт зі зменшенням
  зливається;
* у якому форматі надсилати: PNG без втрат чи JPEG, який менший;
* чи відсіювати завідомо непридатні знімки ще до моделі (надто малі,
  надто розмиті) — і що тоді сказати користувачеві.
"""

import os
from dataclasses import dataclass
from io import BytesIO
import warnings

from dotenv import load_dotenv
from PIL import Image, ImageOps, UnidentifiedImageError

load_dotenv()

UPLOAD_MAX_BYTES = int(float(os.getenv("UPLOAD_MAX_MB", "10")) * 1024 * 1024)
IMAGE_MAX_SIDE = int(os.getenv("IMAGE_MAX_SIDE", "1600"))
MAX_IMAGE_PIXELS = 40_000_000


class ImageError(Exception):
    """Файл не можна віддати моделі. Повідомлення — для користувача."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class PreparedImage:
    """Зображення, готове до надсилання.

    `data` і `mime` — те, що піде моделі. `original` і `sent` — розміри
    до й після підготовки, наприклад `{"width": 1240, "height": 1754,
    "bytes": 179639}`: сторінка показує їх поруч із токенами, щоб було
    видно, скільки коштує роздільність.
    """

    data: bytes
    mime: str
    original: dict
    sent: dict


def prepare(content: bytes) -> PreparedImage:
    """Перевірити байти, що надійшли, і підготувати зображення для моделі.

    Непридатний файл — `ImageError` з поясненням, що не так.
    """
    if not content:
        raise ImageError("Файл порожній. Завантажте зображення рахунку.")
    if len(content) > UPLOAD_MAX_BYTES:
        limit_mb = UPLOAD_MAX_BYTES / (1024 * 1024)
        raise ImageError(f"Файл завеликий. Максимальний розмір — {limit_mb:g} МБ.", 413)
    if UPLOAD_MAX_BYTES <= 0:
        raise ImageError("Налаштування UPLOAD_MAX_MB має бути додатним числом.", 500)
    if IMAGE_MAX_SIDE <= 0:
        raise ImageError("Налаштування IMAGE_MAX_SIDE має бути додатним числом.", 500)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                width, height = source.size
                if width <= 0 or height <= 0:
                    raise ImageError("Зображення має некоректні розміри.")
                if width * height > MAX_IMAGE_PIXELS:
                    raise ImageError("Зображення має надто високу роздільність (понад 40 мегапікселів).")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                original_size = {"width": oriented.width, "height": oriented.height, "bytes": len(content)}
                prepared = oriented.convert("RGB")
                prepared.thumbnail(
                    (IMAGE_MAX_SIDE, IMAGE_MAX_SIDE),
                    Image.Resampling.LANCZOS,
                )
                output = BytesIO()
                prepared.save(output, format="PNG", optimize=True)
    except ImageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ImageError("Файл не є коректним зображенням або його неможливо прочитати.") from exc

    data = output.getvalue()
    return PreparedImage(
        data=data,
        mime="image/png",
        original=original_size,
        sent={"width": prepared.width, "height": prepared.height, "bytes": len(data)},
    )
