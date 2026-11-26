# Comparison of prompt strategies

This folder compares three configurations:

1. fuzzy request: a plain user message with a one-line instruction, no schema and no stored history.
2. structured prompt: a full instruction and examples, but without store rules or conversation memory.
3. context engineering: system prompt + context rules + history in budget + schema validation.

The goal is to evaluate:
- schema validity,
- category correctness,
- whether the model invents information,
- whether it remembers earlier order numbers,
- token and time cost,
- failure handling.

Each result should be classified into one of the typical model error types:
- syntax error,
- semantic mismatch,
- factual hallucination,
- contextual forgetfulness,
- behavioral violation.

The comparison logic is implemented in `comparison.py`.
