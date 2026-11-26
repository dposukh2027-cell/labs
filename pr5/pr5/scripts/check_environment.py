from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentence_transformers import SentenceTransformer


def main():
    model_name = "intfloat/multilingual-e5-small"
    print(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)
    sentences = [
        "return money for damaged headphones",
        "refund for defective item",
        "how to charge the device"
    ]
    vectors = model.encode(sentences, convert_to_numpy=True, normalize_embeddings=True)
    print(f"Encoded {len(sentences)} sentences, shape={vectors.shape}")
    print("Environment check passed")


if __name__ == "__main__":
    main()
