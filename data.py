# utils.py
import os
import time
import logging
import requests
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CSE_API_KEY = os.getenv("CSE_API_KEY")
CSE_CX = os.getenv("CSE_CX")

analyzer = SentimentIntensityAnalyzer()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def text_sentiment(text):
    if not text:
        return {"compound": 0.0, "label": "neutral"}
    s = analyzer.polarity_scores(text)
    c = s["compound"]
    if c >= 0.05:
        label = "positive"
    elif c <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return {"compound": c, "label": label, "detail": s}

# Google CSE
def google_cse_search(query, num_results=10, api_key=None, cx=None):
    api_key = api_key or CSE_API_KEY
    cx = cx or CSE_CX
    if not api_key or not cx:
        raise RuntimeError("CSE API key or CX not configured.")
    results = []
    per_page = 10
    start = 1
    while len(results) < num_results:
        params = {
            "key": api_key,
            "cx": cx,
            "q": query,
            "start": start,
        }
        r = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=20)
        if r.status_code != 200:
            logger.warning("CSE request failed: %s %s", r.status_code, r.text[:300])
            break
        j = r.json()
        items = j.get("items", [])
        for it in items:
            results.append({
                "title": it.get("title"),
                "snippet": it.get("snippet"),
                "link": it.get("link"),
                "displayLink": it.get("displayLink")
            })
            if len(results) >= num_results:
                break
        if "nextPage" not in j.get("queries", {}):
            break
        start += per_page
        time.sleep(0.1)
    return results[:num_results]

# YouTube helper
from googleapiclient.discovery import build

def get_youtube_service(api_key=None):
    api_key = api_key or YOUTUBE_API_KEY
    if not api_key:
        raise RuntimeError("YouTube API key not set.")
    return build("youtube", "v3", developerKey=api_key)

def youtube_search_videos(q, max_results=10, api_key=None):
    youtube = get_youtube_service(api_key)
    videos = []
    page_token = None
    collected = 0
    per_call = 50 if max_results > 50 else max_results
    while collected < max_results:
        m = per_call if (max_results - collected) >= per_call else (max_results - collected)
        try:
            res = youtube.search().list(q=q, part="snippet", type="video", maxResults=m, pageToken=page_token).execute()
        except Exception as e:
            logger.warning("YouTube search failed: %s", e)
            break
        for item in res.get("items", []):
            videos.append({
                "videoId": item["id"]["videoId"],
                "title": item["snippet"].get("title",""),
                "description": item["snippet"].get("description",""),
                "channelTitle": item["snippet"].get("channelTitle"),
                "publishedAt": item["snippet"].get("publishedAt")
            })
            collected += 1
            if collected >= max_results:
                break
        page_token = res.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.1)
    return videos

def youtube_get_video_stats(video_ids, api_key=None):
    youtube = get_youtube_service(api_key)
    stats = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        try:
            res = youtube.videos().list(id=",".join(chunk), part="statistics,snippet").execute()
        except Exception as e:
            logger.warning("youtube.videos().list failed: %s", e)
            continue
        for it in res.get("items",[]):
            vid = it["id"]
            st = it.get("statistics",{})
            stats[vid] = {
                "viewCount": int(st.get("viewCount", 0)),
                "likeCount": int(st.get("likeCount", 0)),
                "commentCount": int(st.get("commentCount", 0)),
                "title": it.get("snippet",{}).get("title",""),
                "description": it.get("snippet",{}).get("description",""),
                "channelTitle": it.get("snippet",{}).get("channelTitle","")
            }
    return stats

def youtube_get_comments(video_id, max_comments=30, api_key=None):
    youtube = get_youtube_service(api_key)
    comments = []
    page_token = None
    collected = 0
    while collected < max_comments:
        m = 100 if (max_comments - collected) >= 100 else (max_comments - collected)
        try:
            res = youtube.commentThreads().list(part="snippet", videoId=video_id, textFormat="plainText", maxResults=m, pageToken=page_token).execute()
        except Exception:
            break
        for item in res.get("items", []):
            top = item.get("snippet",{}).get("topLevelComment",{}).get("snippet",{})
            text = top.get("textDisplay","")
            author = top.get("authorDisplayName","")
            comments.append({"text": text, "author": author})
            collected += 1
            if collected >= max_comments:
                break
        page_token = res.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.05)
    return comments

# Analysis helpers
def mentions_and_sentiment_from_text(text, brands):
    t = (text or "").lower()
    out = {b: {"mentions":0,"positive":0,"negative":0,"neutral":0} for b in brands}
    for b in brands:
        if b.lower() in t:
            out[b]["mentions"] += 1
            s = text_sentiment(text)
            if s["label"] == "positive":
                out[b]["positive"] += 1
            elif s["label"] == "negative":
                out[b]["negative"] += 1
            else:
                out[b]["neutral"] += 1
    return out

def merge_brand_counts(acc, new):
    for b,v in new.items():
        if b not in acc:
            acc[b] = {"mentions":0,"positive":0,"negative":0,"neutral":0,"engagement":0}
        acc[b]["mentions"] += v.get("mentions",0)
        acc[b]["positive"] += v.get("positive",0)
        acc[b]["negative"] += v.get("negative",0)
        acc[b]["neutral"] += v.get("neutral",0)
    return acc

def compute_engagement_score(viewCount, likeCount, commentCount):
    try:
        return int(viewCount) + 25 * int(likeCount) + 60 * int(commentCount)
    except Exception:
        return 0
