"""
Claude-powered analysis: names clusters, identifies pain points, generates opportunity summary.
"""
import json
from typing import Callable
from anthropic import Anthropic
from .clusterer import Cluster


def _parse_json(text: str) -> dict | list:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def analyze_clusters(
    clusters: list[Cluster],
    product_query: str,
    client: Anthropic,
    progress_fn: Callable[[int, int, str], None] | None = None,
) -> list[Cluster]:
    n = len(clusters)
    for i, cluster in enumerate(clusters):
        samples_text = "\n".join(f"- {t}" for t in cluster.sample_texts)

        prompt = f"""You are analyzing customer reviews for "{product_query}" (UK market).

Cluster of {cluster.count} reviews ({cluster.percentage:.1f}% of total). Sample reviews:

{samples_text}

Respond in JSON only:
{{
  "label": "2-5 word theme name (e.g. 'Food jam issues', 'Easy setup praise')",
  "summary": "One sentence describing the core theme of this cluster",
  "is_pain_point": true or false,
  "severity": 1-10 (10 = critical pain point customers hate, 1 = minor or positive),
  "product_improvement": "One specific product feature that would address this (if pain point), else empty string"
}}"""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            result = _parse_json(response.content[0].text)
            cluster.label = result.get("label", f"Cluster {cluster.id}")
            cluster.summary = result.get("summary", "")
            cluster.is_pain_point = result.get("is_pain_point", True)
            cluster.severity = result.get("severity", 5)
            cluster.product_improvement = result.get("product_improvement", "")
        except (json.JSONDecodeError, IndexError, AttributeError):
            cluster.label = f"Cluster {cluster.id}"

        if progress_fn:
            progress_fn(i + 1, n, cluster.label)

    return clusters


def generate_opportunity(clusters: list[Cluster], product_query: str, client: Anthropic) -> dict:
    pain_points = [c for c in clusters if c.is_pain_point]
    positives = [c for c in clusters if not c.is_pain_point]

    pain_str = "\n".join(
        f"- {c.label} ({c.percentage:.1f}%, severity {c.severity}/10): {c.summary}"
        for c in sorted(pain_points, key=lambda x: -x.severity)
    )
    positive_str = "\n".join(
        f"- {c.label} ({c.percentage:.1f}%): {c.summary}"
        for c in positives
    ) or "None identified"

    improvements = [c.product_improvement for c in pain_points if c.product_improvement]
    improvements_str = "\n".join(f"- {imp}" for imp in improvements)

    prompt = f"""Market: UK | Product category: {product_query}

CUSTOMER PAIN POINTS:
{pain_str}

WHAT CUSTOMERS LIKE:
{positive_str}

SUGGESTED PRODUCT IMPROVEMENTS FROM ANALYSIS:
{improvements_str}

Based on this real review data, provide a market opportunity analysis in JSON:
{{
  "top_pain_points": ["top 3 most impactful unresolved pain points"],
  "product_gaps": ["2-3 specific product features missing in current market"],
  "target_product_concept": "One sentence describing an ideal product that wins in this market",
  "opportunity_summary": "2-3 sentences on the size and nature of the opportunity",
  "key_risks": ["2-3 key risks (e.g. certification, returns, competition)"],
  "opportunity_score": 1-100
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return _parse_json(response.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError):
        return {}
