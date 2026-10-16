"""
Discovery pipeline — data-driven, cross-category UK product opportunity finder.

Data sources (all real, no seeding):
  1. Mumsnet         — UK forum discussions, filtered to last 30 days
  2. HotUKDeals      — real-time UK consumer deal interest & purchase intent
  3. Amazon UK        — bestsellers + Movers & Shakers (rising products)
  4. Google Trends UK — rising search queries by category (last 30 days)
  5. Reddit UK        — if REDDIT_CLIENT_ID/SECRET set in .env

No user input needed. AI discovers what product opportunities emerge.
"""
import asyncio
import json
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
from scrapers.mumsnet import scrape_mumsnet
from scrapers.hotukdeals import scrape_hotukdeals
from scrapers.amazon_bestsellers import scrape_amazon_bestsellers, scrape_amazon_movers
from scrapers.google_trends import scrape_google_trends
from scrapers.reddit import scrape_reddit
from scrapers.models import Review
from intelligence.discoverer import discover_opportunities

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent / "data")))
CACHE_FILE = DATA_DIR / "discovery" / "posts.json"
RESULTS_FILE = DATA_DIR / "discovery" / "opportunities.json"


def _load_cache() -> list[Review] | None:
    if CACHE_FILE.exists():
        data = json.loads(CACHE_FILE.read_text())
        return [Review(**r) for r in data]
    return None


def _save_cache(posts: list[Review]):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps([r.__dict__ for r in posts], indent=2))


def _save_results(opportunities: list[dict]):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(opportunities, indent=2))


async def run(use_cache: bool = True, progress_callback=None, **_) -> list[dict]:
    def _p(phase: int, msg: str):
        if progress_callback:
            progress_callback(phase, msg)
        print(f"  [{phase}] {msg}")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        _p(-1, "ERROR: ANTHROPIC_API_KEY not set")
        return []

    # ── Phase 1: Collect real UK consumer data ────────────────────────────────
    _p(1, "Phase 1: Scraping real UK consumer data")
    posts = _load_cache() if use_cache else None

    if posts is not None:
        _p(1, f"Loaded {len(posts)} posts from cache")
    else:
        all_posts: list[Review] = []

        # 1. Mumsnet (UK forum, last 30 days)
        _p(1, "Mumsnet — UK forum (last 30 days)...")
        try:
            mn = scrape_mumsnet(
                max_threads_per_section=10,
                max_days_old=30,
                progress_fn=lambda i, n: _p(1, f"  Mumsnet thread {i}/{n}"),
            )
            all_posts.extend(mn)
            _p(1, f"  ✓ Mumsnet: {len(mn)} posts")
        except Exception as e:
            _p(1, f"  ✗ Mumsnet: {e}")

        # 2. HotUKDeals (real-time UK purchase intent)
        _p(1, "HotUKDeals — real-time UK deal activity...")
        try:
            hd = scrape_hotukdeals(
                n_pages=4,
                min_temperature=30,
                progress_fn=lambda i, n, cat: _p(1, f"  HotUKDeals: {cat}"),
            )
            all_posts.extend(hd)
            _p(1, f"  ✓ HotUKDeals: {len(hd)} deals")
        except Exception as e:
            _p(1, f"  ✗ HotUKDeals: {e}")

        # 3. Amazon UK bestsellers
        _p(1, "Amazon UK — bestsellers...")
        try:
            amz = scrape_amazon_bestsellers(
                progress_fn=lambda i, n, cat: _p(1, f"  Amazon bestsellers: {cat}"),
            )
            all_posts.extend(amz)
            _p(1, f"  ✓ Amazon bestsellers: {len(amz)} products")
        except Exception as e:
            _p(1, f"  ✗ Amazon bestsellers: {e}")

        # 4. Amazon UK Movers & Shakers
        _p(1, "Amazon UK — Movers & Shakers (rising products)...")
        try:
            mv = scrape_amazon_movers(
                progress_fn=lambda i, n, cat: _p(1, f"  Amazon movers: {cat}"),
            )
            all_posts.extend(mv)
            _p(1, f"  ✓ Amazon movers: {len(mv)} products")
        except Exception as e:
            _p(1, f"  ✗ Amazon movers: {e}")

        # 5. Google Trends UK (rising searches, last 30 days)
        _p(1, "Google Trends UK — rising searches (last 30 days)...")
        try:
            gt = scrape_google_trends(
                progress_fn=lambda i, n, cat: _p(1, f"  Google Trends: {cat}"),
            )
            all_posts.extend(gt)
            _p(1, f"  ✓ Google Trends: {len(gt)} rising queries")
        except Exception as e:
            _p(1, f"  ✗ Google Trends: {e}")

        # 6. Reddit UK (optional, needs credentials)
        _p(1, "Reddit UK communities...")
        try:
            rd = scrape_reddit(
                progress_fn=lambda i, n, sub: _p(1, f"  Reddit r/{sub}"),
            )
            if rd:
                all_posts.extend(rd)
                _p(1, f"  ✓ Reddit: {len(rd)} posts")
            else:
                _p(1, "  ⚠ Reddit: skipped (no credentials)")
        except Exception as e:
            _p(1, f"  ✗ Reddit: {e}")

        posts = all_posts
        _save_cache(posts)

        sources: dict[str, int] = {}
        for p in posts:
            sources[p.source] = sources.get(p.source, 0) + 1
        _p(1, f"Total: {len(posts)} data points — {', '.join(f'{s}: {n}' for s, n in sources.items())}")

    if not posts:
        _p(-1, "No data collected. Exiting.")
        return []

    # ── Phase 2 + 3: Embed → Cluster → Discover ──────────────────────────────
    _p(2, f"Phase 2: Embedding {len(posts)} posts...")
    client = Anthropic(api_key=api_key)

    opportunities = discover_opportunities(
        posts=posts,
        client=client,
        n_opportunities=12,
        progress_fn=lambda msg: _p(3, msg),
    )

    _save_results(opportunities)

    # ── Print ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  UK PRODUCT OPPORTUNITIES (data-driven)")
    print(f"  {len(posts)} real data points · Mumsnet + HotUKDeals + Amazon + Google Trends")
    print(f"{'='*65}\n")

    for i, opp in enumerate(opportunities[:10]):
        score = opp.get("opportunity_score", 0)
        icon = "🔥" if score >= 75 else "⚡" if score >= 55 else "💡"
        print(f"  {icon} #{i+1}  {opp['product_name']}  [{opp.get('category','')}]  {score}/100")
        print(f"       {opp.get('pain_point','')}")
        print(f"       Evidence: {opp.get('evidence','')}")
        print()

    print(f"  Full results → {RESULTS_FILE}")
    return opportunities


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(use_cache=not args.no_cache))
