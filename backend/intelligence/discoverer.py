"""
Product opportunity discoverer.

Takes raw forum posts + bestseller data (no product specified by user),
embeds everything, clusters it, then asks Claude:
  "What product opportunities emerge from these real UK consumer discussions?"

Output: ranked list of product opportunities with evidence.
"""
import json
import numpy as np
from anthropic import Anthropic
from .clusterer import cluster_reviews, Cluster, build_clusters_from_labels
from .embedder import Embedder
from scrapers.models import Review


def discover_opportunities(
    posts: list[Review],
    client: Anthropic,
    n_opportunities: int = 10,
    progress_fn=None,
) -> list[dict]:
    """
    Main discovery function.
    1. Embed all posts
    2. Cluster into themes
    3. Claude identifies product opportunities per cluster
    4. Return ranked opportunities
    """
    if not posts:
        return []

    def _p(msg: str):
        if progress_fn:
            progress_fn(msg)

    _p(f"Embedding {len(posts)} posts...")
    embedder = Embedder(verbose=False)
    embeddings = embedder.embed([p.text for p in posts])

    _p("Clustering into themes...")
    labels = cluster_reviews(embeddings, k_min=8, k_max=20)
    clusters = build_clusters_from_labels(posts, labels, n_samples=15)
    _p(f"Found {len(clusters)} discussion clusters")

    opportunities = []

    for i, cluster in enumerate(clusters):
        _p(f"Analysing cluster {i+1}/{len(clusters)} ({cluster.count} posts)...")

        # Source breakdown for this cluster
        sources = {}
        for idx in cluster.indices:
            s = posts[idx].source
            sources[s] = sources.get(s, 0) + 1
        source_str = ", ".join(f"{s}: {n}" for s, n in sources.items())

        samples = "\n".join(f"- {t}" for t in cluster.sample_texts)

        prompt = f"""你正在分析来自英国消费者的 {cluster.count} 条真实帖子（数据来源：{source_str}）。

帖子样本：
{samples}

你的任务：识别这里是否存在一个具体的产品机会，适合中国跨境卖家进入英国市场。

产品机会的定义：
- 消费者对某个品类明显不满意
- 或者消费者在问"有没有能做X的产品"
- 或者现有产品和消费者需求之间存在明显缺口
- 不包括对生活、人际关系或服务的泛泛抱怨

仔细推理：消费者具体对什么不满？有没有可以制造的产品来解决这个问题？帖子里有哪些直接证据支持这个判断？需求信号有多强？

然后仅输出以下 JSON（不要任何其他文字）：
{{
  "has_opportunity": true 或 false,
  "product_name": "具体产品名称（用中文，例如：'带定量功能的自动猫粮投喂器'）",
  "category": "大类目（用中文，例如：'宠物用品'、'家居厨房'、'母婴产品'）",
  "pain_point": "一句话：消费者遇到的具体痛点是什么？",
  "evidence": "一句话：引用帖子中的直接证据，要有具体细节",
  "why_now": "一句话：为什么现在是进入这个市场的好时机？",
  "estimated_price_range": "例如：'£20-50'",
  "opportunity_score": 1-100,
  "confidence": "high / medium / low"
}}

如果没有真实的产品机会，将 has_opportunity 设为 false。"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                thinking={"type": "enabled", "budget_tokens": 5000},
                messages=[{"role": "user", "content": prompt}],
            )
            # Extract text block (skip thinking blocks)
            raw = next(
                (b.text for b in response.content if b.type == "text"),
                ""
            ).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)

            if result.get("has_opportunity") and result.get("product_name"):
                result["cluster_size"] = cluster.count
                result["cluster_pct"] = round(cluster.percentage, 1)
                result["sample_posts"] = cluster.sample_texts[:5]
                result["sources"] = sources
                opportunities.append(result)

        except Exception:
            continue

    # Sort by opportunity score descending
    opportunities.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)

    # Deduplicate similar product names
    seen_names: set[str] = set()
    unique = []
    for opp in opportunities:
        name_key = opp["product_name"].lower().split()[0:3]
        key = " ".join(name_key)
        if key not in seen_names:
            seen_names.add(key)
            unique.append(opp)
        if len(unique) >= n_opportunities:
            break

    return unique
