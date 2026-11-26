from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LLMAnswer(BaseModel):
    answer: str = Field(..., min_length=1)
    sources: list[str] = Field(default_factory=list)
    found: bool = Field(default=True)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            item_str = str(item).strip()
            if item_str:
                cleaned.append(item_str)
        return cleaned

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: str) -> str:
        return value.strip()
