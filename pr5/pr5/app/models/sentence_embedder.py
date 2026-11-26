from __future__ import annotations

import os

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import APP_CONFIG
from app.models.base_model import BaseEmbedder


class SentenceEmbedder(BaseEmbedder):
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or APP_CONFIG["model_name"]
        self.model = SentenceTransformer(self.model_name)

    def encode(self, texts: list[str], normalize: bool = True):
        vectors = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=normalize)
        return np.asarray(vectors, dtype=np.float32)

    def encode_query(self, text: str):
        text = text.strip()
        if not text:
            raise ValueError("Query cannot be empty")
        return self.model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0].astype(np.float32)
