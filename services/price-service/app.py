import os
import sqlite3
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import Flask, request, jsonify
from scrapers import ALL_SCRAPERS

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "/data/prices.db")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "300"))  # 5 min default


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS price_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            platform TEXT NOT NULL,
            result_json TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cache_query ON price_cache(query, platform);

        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            user_id TEXT,
            searched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_history_query ON search_history(query);

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            query TEXT NOT NULL,
            target_price REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, query)
        );
    """)
    conn.commit()
    conn.close()


def get_cached(conn, query: str, platform: str):
    cutoff = int(time.time()) - CACHE_TTL
    row = conn.execute(
        "SELECT result_json FROM price_cache WHERE query = ? AND platform = ? AND fetched_at > ?",
        (query.lower(), platform, cutoff),
    ).fetchone()
    return json.loads(row["result_json"]) if row else None


def set_cache(conn, query: str, platform: str, results: list):
    conn.execute("DELETE FROM price_cache WHERE query = ? AND platform = ?", (query.lower(), platform))
    conn.execute(
        "INSERT INTO price_cache (query, platform, result_json, fetched_at) VALUES (?, ?, ?, ?)",
        (query.lower(), platform, json.dumps(results), int(time.time())),
    )
    conn.commit()


def fetch_platform(scraper, query: str):
    # Each thread needs its own connection — SQLite objects aren't thread-safe
    conn = get_db()
    try:
        cached = get_cached(conn, query, scraper.platform)
        if cached is not None:
            return scraper.platform, cached, True
        results = scraper.search(query)
        data = [r.to_dict() for r in results]
        set_cache(conn, query, scraper.platform, data)
        return scraper.platform, data, False
    except Exception as e:
        app.logger.error(f"Scraper {scraper.platform} failed: {e}")
        return scraper.platform, [], False
    finally:
        conn.close()


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "price"})


@app.route("/search")
def search():
    query = (request.args.get("q") or "").strip()
    user_id = request.args.get("user_id")
    platforms = request.args.getlist("platform") or [s.platform for s in ALL_SCRAPERS]

    if not query:
        return jsonify({"error": "query parameter 'q' is required"}), 400
    if len(query) < 2:
        return jsonify({"error": "query too short"}), 400

    scrapers = [s for s in ALL_SCRAPERS if s.platform in platforms]
    conn = get_db()
    try:
        # Log search
        conn.execute(
            "INSERT INTO search_history (query, user_id) VALUES (?, ?)",
            (query.lower(), user_id),
        )
        conn.commit()

        all_results = []
        cache_hits = 0

        with ThreadPoolExecutor(max_workers=len(scrapers)) as pool:
            futures = {pool.submit(fetch_platform, s, query): s for s in scrapers}
            for future in as_completed(futures):
                platform, results, from_cache = future.result()
                all_results.extend(results)
                if from_cache:
                    cache_hits += 1

        # Sort by price ascending, out-of-stock last
        all_results.sort(key=lambda r: (not r["in_stock"], r["price"]))

        best = all_results[0] if all_results else None

        return jsonify({
            "query": query,
            "results": all_results,
            "total": len(all_results),
            "best_deal": best,
            "cache_hits": cache_hits,
            "timestamp": datetime.utcnow().isoformat(),
        })
    finally:
        conn.close()


@app.route("/trending")
def trending():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT query, COUNT(*) as cnt FROM search_history
               WHERE searched_at > datetime('now', '-7 days')
               GROUP BY query ORDER BY cnt DESC LIMIT 10"""
        ).fetchall()
        return jsonify({"trending": [{"query": r["query"], "count": r["cnt"]} for r in rows]})
    finally:
        conn.close()


@app.route("/watchlist", methods=["GET"])
def get_watchlist():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM watchlist WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return jsonify({"watchlist": [dict(r) for r in rows]})
    finally:
        conn.close()


@app.route("/watchlist", methods=["POST"])
def add_watchlist():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    query = (data.get("query") or "").strip().lower()
    target_price = data.get("target_price")

    if not user_id or not query:
        return jsonify({"error": "user_id and query required"}), 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (user_id, query, target_price) VALUES (?, ?, ?)",
            (user_id, query, target_price),
        )
        conn.commit()
        return jsonify({"status": "added", "query": query}), 201
    finally:
        conn.close()


@app.route("/watchlist/<int:item_id>", methods=["DELETE"])
def remove_watchlist(item_id: int):
    user_id = request.args.get("user_id")
    conn = get_db()
    try:
        conn.execute("DELETE FROM watchlist WHERE id = ? AND user_id = ?", (item_id, user_id))
        conn.commit()
        return jsonify({"status": "removed"})
    finally:
        conn.close()


@app.route("/platforms")
def platforms():
    return jsonify({
        "platforms": [
            {"id": s.platform, "name": s.platform_display} for s in ALL_SCRAPERS
        ]
    })


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5002, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
