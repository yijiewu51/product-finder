"""
AI Product Opportunity Finder — main pipeline.

Usage:
    python pipeline.py "automatic cat feeder"           # uses seeded reviews (fast, no scraping)
    python pipeline.py "slow feeder bowl" --no-cache    # re-run fresh seeds
    python pipeline.py "cat water fountain" --live      # attempt real Amazon/Reddit scraping
    python pipeline.py "cat feeder" --n-reviews 300     # more reviews for better clusters
"""
import asyncio
import json
import os
import sys
import argparse
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
from scrapers.models import Review
from scrapers.seeder import generate_seeded_reviews
from intelligence.embedder import Embedder
from intelligence.clusterer import cluster_reviews, build_clusters_from_labels, Cluster
from intelligence.analyzer import analyze_clusters, generate_opportunity

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent / "data")))


# ── helpers ───────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower())[:50]

def _bar(pct: float, width: int = 25) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def _load_cache(query: str) -> list[Review] | None:
    cache = DATA_DIR / _slug(query) / "reviews.json"
    if cache.exists():
        data = json.loads(cache.read_text())
        reviews = [Review(**r) for r in data]
        return reviews
    return None

def _save_cache(query: str, reviews: list[Review]):
    d = DATA_DIR / _slug(query)
    d.mkdir(parents=True, exist_ok=True)
    (d / "reviews.json").write_text(json.dumps([r.__dict__ for r in reviews], indent=2))

def _save_results(query: str, result: dict):
    d = DATA_DIR / _slug(query)
    d.mkdir(parents=True, exist_ok=True)
    (d / "analysis.json").write_text(json.dumps(result, indent=2))


# ── display (CLI only) ────────────────────────────────────────────────────────

def _print_clusters(clusters: list[Cluster], total: int):
    print(f"\n{'='*65}")
    print(f"  PAIN POINT ANALYSIS  ({total} reviews embedded & clustered)")
    print(f"{'='*65}")
    pain = [c for c in clusters if c.is_pain_point]
    pos  = [c for c in clusters if not c.is_pain_point]
    print("\n  Pain Points:")
    for c in sorted(pain, key=lambda x: -x.severity):
        icon = "🔴" if c.severity >= 7 else "🟡"
        label = c.label or f"Cluster {c.id}"
        print(f"\n  {icon} {label:<40} {c.percentage:>5.1f}%  {_bar(c.percentage)}")
        if c.summary:
            print(f"     {c.summary}")
        if c.product_improvement:
            print(f"     Fix: {c.product_improvement}")
    if pos:
        print("\n  Positive Themes:")
        for c in pos:
            label = c.label or f"Cluster {c.id}"
            print(f"\n  ✅ {label:<40} {c.percentage:>5.1f}%  {_bar(c.percentage)}")
            if c.summary:
                print(f"     {c.summary}")

def _print_opportunity(opp: dict):
    if not opp:
        return
    print(f"\n{'='*65}")
    print("  OPPORTUNITY ANALYSIS")
    print(f"{'='*65}\n")
    if opp.get("top_pain_points"):
        print("  Top Pain Points:")
        for p in opp["top_pain_points"]:
            print(f"    • {p}")
    if opp.get("product_gaps"):
        print("\n  Product Gaps (missing in market):")
        for g in opp["product_gaps"]:
            print(f"    • {g}")
    if opp.get("target_product_concept"):
        print(f"\n  Target Product Concept:")
        print(f"    {opp['target_product_concept']}")
    if opp.get("opportunity_summary"):
        print(f"\n  Opportunity Summary:")
        print(f"    {opp['opportunity_summary']}")
    if opp.get("key_risks"):
        print(f"\n  Key Risks:")
        for r in opp["key_risks"]:
            print(f"    • {r}")
    score = opp.get("opportunity_score")
    if score is not None:
        grade = "STRONG" if score >= 75 else "MODERATE" if score >= 50 else "WEAK"
        print(f"\n  {'─'*40}")
        print(f"  Opportunity Score: {score}/100  [{grade}]")
        print(f"  {'─'*40}")


# ── pipeline ──────────────────────────────────────────────────────────────────

async def run(
    query: str,
    market: str = "UK",
    n_reviews: int = 200,
    use_cache: bool = True,
    live_scrape: bool = False,
    n_samples_per_cluster: int = 12,
    progress_callback: Callable[[int, str], None] | None = None,
    verbose: bool = True,
) -> dict | None:

    def _p(phase: int, message: str):
        if progress_callback:
            progress_callback(phase, message)
        if verbose:
            print(message)

    _p(0, f"Starting analysis: {query}")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        _p(-1, "ERROR: ANTHROPIC_API_KEY not set in .env")
        return None

    # ── Phase 1: data ─────────────────────────────────────────────────────────
    _p(1, "Phase 1: Data Collection")
    reviews = _load_cache(query) if use_cache else None

    if reviews is not None:
        _p(1, f"Loaded {len(reviews)} reviews from cache")
    else:
        if live_scrape:
            from scrapers.amazon import scrape_amazon
            from scrapers.reddit import scrape_reddit
            all_reviews: list[Review] = []
            _p(1, "Scraping Amazon UK...")
            try:
                amazon = await scrape_amazon(query, max_products=6, max_pages_per_product=4)
                all_reviews.extend(amazon)
                _p(1, f"Amazon: {len(amazon)} reviews")
            except Exception as e:
                _p(1, f"Amazon failed: {e}")
            _p(1, "Scraping Reddit...")
            try:
                reddit = scrape_reddit(query)
                all_reviews.extend(reddit)
                _p(1, f"Reddit: {len(reddit)} mentions")
            except Exception as e:
                _p(1, f"Reddit failed: {e}")
            if not all_reviews:
                _p(1, "Live scraping returned 0, falling back to seeds...")
                all_reviews = generate_seeded_reviews(query, market, n_reviews, api_key)
            reviews = all_reviews
        else:
            _p(1, f"Generating {n_reviews} seeded reviews with Claude...")
            reviews = generate_seeded_reviews(
                query, market, n_reviews, api_key,
                progress_fn=lambda i, n: _p(1, f"Generating reviews: batch {i}/{n}"),
            )
        _save_cache(query, reviews)

    if not reviews:
        _p(-1, "No reviews collected. Exiting.")
        return None

    sources: dict[str, int] = {}
    for r in reviews:
        sources[r.source] = sources.get(r.source, 0) + 1
    _p(1, f"Total: {len(reviews)} reviews collected")

    # ── Phase 2: embed + cluster ──────────────────────────────────────────────
    _p(2, "Phase 2: Embedding reviews...")
    embedder = Embedder(verbose=False)
    embeddings = embedder.embed([r.text for r in reviews])

    _p(2, "Finding optimal clusters...")
    labels = cluster_reviews(embeddings)
    clusters = build_clusters_from_labels(reviews, labels)
    _p(2, f"Found {len(clusters)} clusters")

    for c in clusters:
        c.sample_texts = [reviews[i].text[:400] for i in c.indices[:n_samples_per_cluster]]

    # ── Phase 3: Claude analysis ───────────────────────────────────────────────
    client = Anthropic(api_key=api_key)

    _p(3, f"Phase 3: Naming {len(clusters)} clusters with Claude...")
    clusters = analyze_clusters(
        clusters, query, client,
        progress_fn=lambda i, n, label: _p(3, f"Cluster {i}/{n}: {label}"),
    )

    _p(3, "Generating opportunity summary...")
    opportunity = generate_opportunity(clusters, query, client)

    # ── Build result dict ──────────────────────────────────────────────────────
    result = {
        "query": query,
        "market": market,
        "total_reviews": len(reviews),
        "sources": sources,
        "clusters": [
            {
                "id": c.id,
                "label": c.label,
                "summary": c.summary,
                "percentage": round(c.percentage, 1),
                "count": c.count,
                "severity": c.severity,
                "is_pain_point": c.is_pain_point,
                "product_improvement": c.product_improvement,
            }
            for c in clusters
        ],
        "opportunity": opportunity,
    }

    _save_results(query, result)
    _p(0, "Analysis complete")

    if verbose:
        _print_clusters(clusters, len(reviews))
        _print_opportunity(opportunity)

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Product Opportunity Finder")
    parser.add_argument("query", nargs="+")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--n-reviews", type=int, default=200)
    args = parser.parse_args()

    asyncio.run(run(
        query=" ".join(args.query),
        use_cache=not args.no_cache,
        live_scrape=args.live,
        n_reviews=args.n_reviews,
        verbose=True,
    ))
