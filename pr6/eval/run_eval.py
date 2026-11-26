from __future__ import annotations

from app.rag.pipeline import RAGPipeline
from eval.questions import QUESTIONS


def run_eval() -> None:
    pipeline = RAGPipeline()
    for index, item in enumerate(QUESTIONS, start=1):
        result = pipeline.ask(item["question"])
        print(f"Q{index}: {item['question']}")
        print("  answer:", result["answer_text"])
        print("  found:", result["found"])
        print("  sources:", result["source_refs"])
        print("  validation:", result.get("validation_errors", []))
        print()


if __name__ == "__main__":
    run_eval()
