import json
import unittest
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app import images, llm, rules, schema
from app.extraction import decide
from app.images import PreparedImage
from app.main import app
from app.llm import LLMError


class SchemaTests(unittest.TestCase):
    def test_valid_document_passes_schema(self):
        document = valid_document()
        self.assertEqual(schema.validate(json.dumps(document)), document)

    def test_malformed_and_incomplete_responses_fail(self):
        with self.assertRaises(schema.SchemaValidationError):
            schema.validate("{")
        document = valid_document()
        del document["total"]
        with self.assertRaises(schema.SchemaValidationError):
            schema.validate(json.dumps(document))

    def test_fractional_numbers_remain_decimal_and_extremes_fail(self):
        document = valid_document()
        document["total_without_vat"] = 0.1
        parsed = schema.validate(json.dumps(document))
        self.assertEqual(parsed["total_without_vat"], Decimal("0.1"))
        document["total"] = 1e100
        with self.assertRaises(schema.SchemaValidationError):
            schema.validate(json.dumps(document))


class LlmTests(unittest.TestCase):
    def test_extract_sends_image_and_returns_schema_checked_json(self):
        raw = json.dumps(valid_document())
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=raw, refusal=None),
                )
            ],
            usage=SimpleNamespace(model_dump=lambda exclude_none: {"prompt_tokens": 10}),
            model="test-model",
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: response)
            )
        )
        image = PreparedImage(
            data=b"image-bytes",
            mime="image/png",
            original={"width": 1, "height": 1, "bytes": 11},
            sent={"width": 1, "height": 1, "bytes": 11},
        )
        with patch("app.llm.get_client", return_value=client), patch("app.llm.MODEL", "test-model"):
            result = llm.extract(image)
        self.assertEqual(result["document"]["number"], "A-1")
        self.assertEqual(result["model"], "test-model")
        self.assertEqual(result["usage"]["prompt_tokens"], 10)
        self.assertEqual(result["raw_response"], raw)

    def test_invalid_model_json_preserves_raw_response_for_evaluation(self):
        raw = '{"unexpected": true}'
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content=raw, refusal=None),
                )
            ],
            usage=None,
            model="test-model",
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: response)
            )
        )
        image = PreparedImage(b"x", "image/png", {}, {})
        with patch("app.llm.get_client", return_value=client), patch("app.llm.MODEL", "test-model"):
            with self.assertRaises(llm.LLMError) as error:
                llm.extract(image)
        self.assertEqual(error.exception.raw_response, raw)


class RuleTests(unittest.TestCase):
    def test_reference_invoice_passes_and_can_be_automated(self):
        document = valid_document()
        issues = rules.check(document)
        self.assertEqual(issues, [])
        self.assertEqual(decide(document, issues)[0], "auto")

    def test_invalid_iban_requires_review(self):
        document = valid_document()
        document["supplier"]["iban"] = "UA003510050000026004017723561"
        issues = rules.check(document)
        self.assertIn("iban_checksum", {item.rule for item in issues})
        self.assertEqual(decide(document, issues)[0], "review")

    def test_other_document_is_rejected(self):
        document = valid_document()
        document["document_type"] = "інший документ"
        self.assertEqual(decide(document, rules.check(document))[0], "reject")


class ImageTests(unittest.TestCase):
    def test_image_is_prepared_and_resized(self):
        source = Image.new("RGB", (800, 1200), "white")
        stream = BytesIO()
        source.save(stream, format="PNG")
        with patch.object(images, "IMAGE_MAX_SIDE", 600):
            result = images.prepare(stream.getvalue())
        self.assertEqual(result.original["width"], 800)
        self.assertEqual(result.sent["height"], 600)
        self.assertEqual(result.mime, "image/png")

    def test_empty_invalid_and_oversized_uploads_are_rejected(self):
        with self.assertRaises(images.ImageError):
            images.prepare(b"")
        with self.assertRaises(images.ImageError):
            images.prepare(b"not an image")
        with patch.object(images, "UPLOAD_MAX_BYTES", 4):
            with self.assertRaises(images.ImageError):
                images.prepare(b"12345")


class ApiTests(unittest.TestCase):
    def test_successful_response_contains_document_and_timings(self):
        source = Image.new("RGB", (20, 20), "white")
        stream = BytesIO()
        source.save(stream, format="PNG")
        extracted = {
            "document": valid_document(),
            "model": "test-model",
            "elapsed": 0.01,
            "usage": {"prompt_tokens": 2},
            "raw_response": "{}",
        }
        with patch("app.extraction.llm.extract", return_value=extracted):
            response = TestClient(app).post(
                "/api/extract",
                files={"image": ("document.png", stream.getvalue(), "image/png")},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["decision"], "auto")
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(set(payload["elapsed"]), {"prepare", "extraction", "checks"})
        self.assertEqual(payload["document"]["total"], 120)

    def test_invalid_upload_returns_explanatory_http_error(self):
        response = TestClient(app).post(
            "/api/extract",
            files={"image": ("document.png", b"not an image", "image/png")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("зображення", response.json()["detail"])

    def test_model_failure_returns_service_error(self):
        source = Image.new("RGB", (20, 20), "white")
        stream = BytesIO()
        source.save(stream, format="PNG")
        with patch("app.extraction.llm.extract", side_effect=LLMError("model unavailable", 503)):
            response = TestClient(app).post(
                "/api/extract",
                files={"image": ("document.png", stream.getvalue(), "image/png")},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "model unavailable")

    def test_upload_limit_is_checked_before_processing(self):
        with patch("app.extraction.MAX_UPLOAD_BYTES", 4):
            response = TestClient(app).post(
                "/api/extract",
                files={"image": ("document.png", b"12345", "image/png")},
            )
        self.assertEqual(response.status_code, 413)


def valid_document():
    company, suppliers = rules.load_reference()
    supplier = suppliers[0]
    return {
        "document_type": "рахунок",
        "number": "A-1",
        "date": "2000-01-01",
        "valid_until": None,
        "supplier": {
            "name": supplier["name"],
            "code": supplier["code"],
            "iban": supplier["iban"],
        },
        "buyer": {"name": company["name"], "code": company["code"]},
        "items": [
            {
                "name": "Product",
                "unit": "pcs",
                "quantity": 1,
                "unit_price": 100,
                "amount": 100,
            }
        ],
        "total_without_vat": 100,
        "vat": 20,
        "total": 120,
    }


if __name__ == "__main__":
    unittest.main()
