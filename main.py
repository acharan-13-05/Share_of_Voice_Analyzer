# app.py
import os
import json
import logging
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from utils import (
    google_cse_search, youtube_search_videos, youtube_get_video_stats,
    youtube_get_comments, mentions_and_sentiment_from_text, merge_brand_counts,
    compute_engagement_score
)

load_dotenv()
app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PER_PLATFORM = int(os.getenv("PER_PLATFORM", "10"))
BRANDS = [b.strip().lower() for b in os.getenv("BRANDS", "atomberg,havells,crompton,orient").split(",")]
WEIGHTS = [float(x) for x in os.getenv("WEIGHTS", "0.4,0.4,0.2").split(",")]
MAX_COMMENTS_PER_VIDEO = int(os.getenv("MAX_COMMENTS_PER_VIDEO", "30"))

@app.route("/")
def index():
    return render_template("index.html", brands=BRANDS, per_platform=PER_PLATFORM)

@app.route("/analyze", methods=["POST"])
def analyze():
    payload = request.json or {}
    query = payload.get("query", "smart fan")
    per_platform = int(payload.get("per_platform", PER_PLATFORM))
    brands = [b.lower() for b in payload.get("brands", BRANDS)]

    agg = {b: {"mentions": 0, "positive": 0, "negative": 0, "neutral": 0, "engagement": 0} for b in brands}

    # 1) Google CSE
    try:
        web_results = google_cse_search(query, num_results=per_platform)
        logger.info("Got %d web results", len(web_results))
    except Exception as e:
        logger.warning("Google CSE failed: %s", e)
        web_results = []

    for item in web_results:
        text = "{}. {}".format(item.get("title", ""), item.get("snippet", ""))
        counts = mentions_and_sentiment_from_text(text, brands)
        merge_brand_counts(agg, counts)
        for b in brands:
            if counts[b]["mentions"] > 0:
                agg[b]["engagement"] += 1

    # 2) YouTube
    try:
        videos = youtube_search_videos(query, max_results=per_platform)
        logger.info("Got %d YouTube videos", len(videos))
    except Exception as e:
        logger.warning("YouTube search failed: %s", e)
        videos = []

    video_ids = [v["videoId"] for v in videos]
    try:
        stats = youtube_get_video_stats(video_ids)
    except Exception as e:
        logger.warning("youtube_get_video_stats failed: %s", e)
        stats = {}

    for v in videos:
        vid = v["videoId"]
        meta_text = " ".join([v.get("title", "") or "", v.get("description", "") or ""])
        counts = mentions_and_sentiment_from_text(meta_text, brands)

        # Fetch comments
        try:
            comments = youtube_get_comments(vid, max_comments=MAX_COMMENTS_PER_VIDEO)
        except Exception:
            comments = []
        for c in comments:
            c_counts = mentions_and_sentiment_from_text(c.get("text", ""), brands)
            for b in brands:
                counts[b]["mentions"] += c_counts[b]["mentions"]
                counts[b]["positive"] += c_counts[b]["positive"]
                counts[b]["negative"] += c_counts[b]["negative"]
                counts[b]["neutral"] += c_counts[b]["neutral"]

        s = stats.get(vid, {"viewCount": 0, "likeCount": 0, "commentCount": 0})
        eng = compute_engagement_score(s.get("viewCount", 0), s.get("likeCount", 0), s.get("commentCount", 0))
        for b in brands:
            if counts[b]["mentions"] > 0:
                agg[b]["mentions"] += counts[b]["mentions"]
                agg[b]["positive"] += counts[b]["positive"]
                agg[b]["negative"] += counts[b]["negative"]
                agg[b]["neutral"] += counts[b]["neutral"]
                agg[b]["engagement"] += eng

    # 3) Compute SoV
    M_total = sum(agg[b]["mentions"] for b in brands) or 0
    E_total = sum(agg[b]["engagement"] for b in brands) or 0
    P_total = sum(agg[b]["positive"] for b in brands) or 0

    results = []
    for b in brands:
        M = agg[b]["mentions"]
        E = agg[b]["engagement"]
        P = agg[b]["positive"]
        M_norm = (M / M_total) if M_total > 0 else 0
        E_norm = (E / E_total) if E_total > 0 else 0
        S_norm = (P / P_total) if P_total > 0 else ((P / M) if M > 0 else 0)
        SoV = WEIGHTS[0] * M_norm + WEIGHTS[1] * E_norm + WEIGHTS[2] * S_norm
        positive_rate = (P / M) if M > 0 else 0
        SoPV = (P / P_total) if P_total > 0 else 0
        results.append({
            "brand": b,
            "mentions": M,
            "engagement": E,
            "positive_mentions": P,
            "positive_rate": round(positive_rate, 3),
            "SoV_score": round(SoV, 6),
            "SoPV": round(SoPV, 6)
        })

    results = sorted(results, key=lambda x: x["SoV_score"], reverse=True)

    all_zero = all(r["mentions"] == 0 and r["engagement"] == 0 for r in results)
    meta = {
        "query": query,
        "per_platform": per_platform,
        "brands": brands,
        "all_zero": all_zero
    }

    return jsonify({"meta": meta, "summary": results, "raw": agg})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
