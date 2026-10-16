"""
Clusters review embeddings using KMeans.
Finds optimal K via silhouette score.
"""
import numpy as np
from dataclasses import dataclass, field
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scrapers.models import Review


@dataclass
class Cluster:
    id: int
    indices: list[int]
    count: int
    percentage: float
    label: str = ""
    summary: str = ""
    severity: int = 5
    is_pain_point: bool = True
    product_improvement: str = ""
    sample_texts: list[str] = field(default_factory=list)


def _find_optimal_k(embeddings: np.ndarray, k_min: int = 4, k_max: int = 12) -> int:
    k_max = min(k_max, len(embeddings) - 1)
    best_k, best_score = k_min, -1.0
    for k in range(k_min, k_max + 1):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(embeddings)
        score = silhouette_score(embeddings, labels, sample_size=min(2000, len(embeddings)))
        if score > best_score:
            best_score, best_k = score, k
    return best_k


def cluster_reviews(
    embeddings: np.ndarray,
    n_clusters: int = None,
    k_min: int = 4,
    k_max: int = 12,
) -> list[int]:
    """Returns raw cluster label list (one per embedding)."""
    if n_clusters is None:
        n_clusters = _find_optimal_k(embeddings, k_min, k_max)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    return km.fit_predict(embeddings).tolist()


def build_clusters_from_labels(
    items: list[Review],
    labels: list[int],
    n_samples: int = 15,
) -> list[Cluster]:
    """Build Cluster objects from raw labels, sorted by size descending."""
    total = len(labels)
    cluster_map: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        cluster_map.setdefault(int(label), []).append(i)

    clusters = []
    for cid, indices in sorted(cluster_map.items(), key=lambda x: -len(x[1])):
        clusters.append(Cluster(
            id=cid,
            indices=indices,
            count=len(indices),
            percentage=len(indices) / total * 100,
            sample_texts=[items[i].text[:400] for i in indices[:n_samples]],
        ))
    return clusters
