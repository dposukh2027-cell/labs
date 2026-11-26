from __future__ import annotations

from app.rag.schema import LLMAnswer


class AnswerValidator:
    def validate(self, answer: LLMAnswer, available_refs: list[str]) -> tuple[bool, list[str]]:
        errors: list[str] = []

        if not answer.answer or not answer.answer.strip():
            errors.append("empty answer")

        if answer.found and not answer.sources:
            errors.append("found=true without sources")

        for ref in answer.sources:
            if ref not in available_refs:
                errors.append(f"source {ref} is not in available references")

        return len(errors) == 0, errors
