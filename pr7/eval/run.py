"""Послідовний прогін доступних зразків і порівняння з expected.json.

Запуск із кореня роботи:
    python eval/run.py
    python eval/run.py --output eval/results-image-1200.json

Файл результатів містить сирі відповіді моделі. Зберігайте його локально
і не додавайте справжні документи з персональними даними.
"""

import argparse
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.extraction import ProcessingError, process
SAMPLES = ROOT / "samples"
EXPECTED_PATH = SAMPLES / "expected.json"
CRITICAL_FIELDS = {"supplier.iban", "supplier.code", "total"}
VARIANT_NAMES = ("blur", "lowres", "jpeg", "faded", "photo", "crop")


def normalize(value: object, path: str) -> object:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)).normalize()
        except InvalidOperation:
            return value
    if not isinstance(value, str):
        return value
    text = unicodedata.normalize("NFKC", value).strip()
    if path.endswith(".iban"):
        return re.sub(r"\s+", "", text).upper()
    numeric_field = (
        path in {"total_without_vat", "vat", "total"}
        or path.startswith("items.")
        and path.rsplit(".", 1)[-1] in {"quantity", "price", "unit_price", "amount"}
    )
    if numeric_field:
        number = text.replace(" ", "").replace(",", ".")
        try:
            return Decimal(number).normalize()
        except InvalidOperation:
            return text
    text = text.translate(str.maketrans({"ʼ": "'", "’": "'", "‘": "'", "＇": "'"}))
    return " ".join(text.casefold().split())


def flatten_expected(value: object, prefix: str = "") -> dict[str, object]:
    if isinstance(value, dict):
        flattened: dict[str, object] = {}
        for key, child in value.items():
            path_key = "unit_price" if prefix.startswith("items") and key == "price" else key
            path = f"{prefix}.{path_key}" if prefix else path_key
            flattened.update(flatten_expected(child, path))
        return flattened
    if isinstance(value, list):
        flattened = {}
        for index, child in enumerate(value):
            flattened.update(flatten_expected(child, f"{prefix}.{index}"))
        return flattened
    return {prefix: value}


def get_path(document: dict, path: str) -> object:
    value: object = document
    for part in path.split("."):
        if isinstance(value, list):
            try:
                value = value[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def is_related(issue_field: str, field: str) -> bool:
    return issue_field == field or field.startswith(issue_field + ".") or issue_field.startswith(field + ".")


def is_caught(issue: dict, field: str) -> bool:
    issue_field = issue.get("field", "")
    if is_related(issue_field, field):
        return True
    rule = issue.get("rule")
    if rule == "arithmetic_line":
        return issue_field.rsplit(".", 1)[0] == field.rsplit(".", 1)[0] and field.startswith("items.")
    if rule == "arithmetic_subtotal":
        return field == "total_without_vat" or (
            field.startswith("items.") and field.endswith(".amount")
        )
    if rule == "arithmetic_vat":
        return field in {"total_without_vat", "vat"}
    if rule == "arithmetic_total":
        return field in {"total_without_vat", "vat", "total"}
    return False


def classify_fields(expected: dict, actual: dict, issues: list[dict], decision: str | None) -> list[dict]:
    outcomes = []
    expected_fields = flatten_expected(expected)
    for path, expected_value in expected_fields.items():
        actual_value = get_path(actual, path)
        expected_normalized = normalize(expected_value, path)
        actual_normalized = normalize(actual_value, path)
        if expected_value is None and actual_value is not None:
            status = "hallucination"
        elif expected_value is not None and actual_value is None:
            status = "missing"
        elif expected_normalized == actual_normalized:
            status = "correct"
        else:
            status = "error"
        caught = any(is_caught(issue, path) for issue in issues)
        outcomes.append({
            "field": path,
            "status": status,
            "caught_by_rule": caught,
            "silent": status in {"error", "hallucination"} and decision == "auto" and not caught,
        })
    return outcomes


def variant_for(relative_path: str) -> str:
    path = Path(relative_path)
    if path.parent.name == "clean":
        return "clean"
    if path.parent.name == "degraded":
        match = re.search(r"-(" + "|".join(VARIANT_NAMES) + r")\.jpg$", path.name)
        return match.group(1) if match else "degraded"
    return "own"


def summarize(records: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["variant"]].append(record)

    summary = {}
    for variant, group in sorted(groups.items()):
        counts = defaultdict(int)
        critical = defaultdict(int)
        decision_matrix = defaultdict(int)
        for record in group:
            if record.get("field_results"):
                record_has_silent_error = False
                for field in record["field_results"]:
                    counts[field["status"]] += 1
                    if field["field"] in CRITICAL_FIELDS:
                        critical[field["status"]] += 1
                    if field["caught_by_rule"] and field["status"] in {"error", "hallucination"}:
                        counts["caught"] += 1
                    if field["silent"]:
                        counts["silent_fields"] += 1
                        record_has_silent_error = True
                        critical["silent" if field["field"] in CRITICAL_FIELDS else "noncritical_silent"] += 1
                counts["documents_with_silent_errors"] += record_has_silent_error
            if record.get("expected_decision") is not None and record.get("decision") is not None:
                counts["decision_match"] += record["decision"] == record["expected_decision"]
                counts["decision_mismatch"] += record["decision"] != record["expected_decision"]
                decision_matrix[f"{record['expected_decision']}->{record['decision']}"] += 1
            if record.get("error"):
                counts["processing_errors"] += 1
            counts["prompt_tokens"] += (record.get("usage") or {}).get("prompt_tokens", 0)
            counts["completion_tokens"] += (record.get("usage") or {}).get("completion_tokens", 0)
        summary[variant] = {
            "documents": len(group),
            "fields": dict(counts),
            "critical_fields": dict(critical),
            "decision_matrix": dict(decision_matrix),
        }
    return summary


def json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Оцінити вилучення даних на зразках.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "eval" / "results.json",
        help="локальний JSON-файл для результатів (містить сирі відповіді моделі)",
    )
    args = parser.parse_args()

    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    records = []
    for relative_path, truth in expected.items():
        source = SAMPLES / relative_path
        if not source.is_file():
            records.append({
                "file": relative_path,
                "variant": variant_for(relative_path),
                "error": "Зображення з expected.json не знайдено.",
                "expected_decision": truth.get("expected_decision"),
            })
            continue

        print(f"Обробка {relative_path}...")
        try:
            result = process(source.read_bytes())
        except ProcessingError as exc:
            records.append({
                "file": relative_path,
                "variant": variant_for(relative_path),
                "error": str(exc),
                "status_code": exc.status_code,
                "raw_response": exc.raw_response,
                "expected_decision": truth.get("expected_decision"),
                "expected_checks": truth.get("expected_checks", []),
            })
            continue

        issues = [issue.__dict__ for issue in result.issues]
        fields = classify_fields(truth["fields"], result.document or {}, issues, result.decision)
        triggered_checks = sorted({issue["rule"] for issue in issues})
        expected_checks = sorted(set(truth.get("expected_checks", [])))
        records.append({
            "file": relative_path,
            "variant": variant_for(relative_path),
            "expected_decision": truth.get("expected_decision"),
            "expected_checks": expected_checks,
            "triggered_checks": triggered_checks,
            "missing_expected_checks": sorted(set(expected_checks) - set(triggered_checks)),
            "unexpected_checks": sorted(set(triggered_checks) - set(expected_checks)),
            "decision": result.decision,
            "decision_match": result.decision == truth.get("expected_decision"),
            "field_results": fields,
            "issues": issues,
            "image": result.image,
            "model": result.model,
            "elapsed": result.elapsed,
            "usage": result.usage,
            "document": result.document,
            "raw_response": result.raw_response,
        })

    output = {
        "normalization": "Unicode NFKC, casefolded text with collapsed spaces; IBAN strips spaces; numeric values compare as Decimal.",
        "records": records,
        "summary": summarize(records),
        "unlisted_own_images": sorted(
            str(path.relative_to(SAMPLES)).replace("\\", "/")
            for path in (SAMPLES / "own").glob("*")
            if path.is_file() and str(path.relative_to(SAMPLES)).replace("\\", "/") not in expected
        ) if (SAMPLES / "own").is_dir() else [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    print(f"Збережено {len(records)} записів: {args.output}")
    print("Тихі помилки:", sum(
        field["silent"]
        for record in records
        for field in record.get("field_results", [])
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
