import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"


class Embedder:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.model = SentenceTransformer(MODEL_NAME)

    def embed(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        return self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=self.verbose,
            normalize_embeddings=True,
        )
