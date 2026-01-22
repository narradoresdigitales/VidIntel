
# =========================================================
# VidIntel — Multilingual YouTube Discovery
# Streamlit App (Production Version)
# =========================================================

import re
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone

# Optional dependency used for language filtering
try:
    from langdetect import detect
except Exception:
    detect = None

# Optional dependency for Word export
try:
    from docx import Document
except Exception:
    Document = None


# -------------------------
# Configuration & Secrets
# -------------------------
st.set_page_config(
    page_title="VidIntel",
    page_icon="📺",
    layout="wide"
)

API_KEY = st.secrets.get("YOUTUBE_API_KEY", None)

if not API_KEY:
    st.error(
        "❌ YouTube API key not found.\n\n"
        "Please add it in **Streamlit → App settings → Secrets** as:\n\n"
        "`YOUTUBE_API_KEY = \"your_key_here\"`"
    )
    st.stop()


SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


# -------------------------
# Helper Functions
# -------------------------
def iso8601_to_seconds(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h = int(m.group(1) or 0)
    mnt = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mnt * 60 + s


def compute_published_after(choice):
    now = datetime.now(timezone.utc)
    if choice == "No filter":
        return None
    if choice == "Last 24 hours":
        return now - timedelta(hours=24)
    if choice == "Last 72 hours":
        return now - timedelta(hours=72)
    if choice == "Last 7 days":
        return now - timedelta(days=7)
    if choice == "This month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if choice == "This year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def search_youtube(query, lang, region, max_results, published_after):
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "relevanceLanguage": lang,
        "key": API_KEY,
    }

    if region:
        params["regionCode"] = region

    if published_after:
        params["publishedAfter"] = published_after.isoformat().replace("+00:00", "Z")
        params["order"] = "date"

    r = requests.get(SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("items", [])



def fetch_video_details(video_ids):
    params = {
        "part": "contentDetails,statistics",
        "id": ",".join(video_ids),
        "key": API_KEY,
    }

    r = requests.get(VIDEOS_URL, params=params, timeout=30)
    r.raise_for_status()

    details = {}

    for item in r.json().get("items", []):
        vid = item.get("id")

        # ✅ Safely extract duration
        dur_iso = (
            item.get("contentDetails", {}).get("duration")
        )

        if dur_iso:
            duration_sec = iso8601_to_seconds(dur_iso)
        else:
            # Unknown or unavailable duration
            duration_sec = 0

        details[vid] = {
            "duration_sec": duration_sec,
            "views": int(item.get("statistics", {}).get("viewCount", 0)),
        }

    return details



def strict_language_filter(items, target_lang):
    if not detect:
        return items
    filtered = []
    for it in items:
        text = it["snippet"]["title"] + " " + it["snippet"].get("description", "")
        try:
            if detect(text) == target_lang:
                filtered.append(it)
        except Exception:
            pass
    return filtered


def to_dataframe(items, details):
    rows = []
    for it in items:
        s = it["snippet"]
        vid = it["id"]["videoId"]
        mins = round(details.get(vid, {}).get("duration_sec", 0) / 60, 1)
        rows.append({
            "Title": s["title"],
            "Channel": s["channelTitle"],
            "Published": s["publishedAt"][:10],
            "Duration (min)": mins,
            "URL": f"https://www.youtube.com/watch?v={vid}",
        })
    return pd.DataFrame(rows)


def export_txt(df):
    lines = []
    for i, r in df.iterrows():
        lines += [
            f"{i+1}. {r['Title']}",
            f"   Channel: {r['Channel']}",
            f"   Published: {r['Published']}",
            f"   Duration: {r['Duration (min)']} min",
            f"   URL: {r['URL']}",
            ""
        ]
    return "\n".join(lines)


def export_docx(df):
    if not Document:
        return None
    doc = Document()
    doc.add_heading("VidIntel Results", level=1)
    for _, r in df.iterrows():
        p = doc.add_paragraph()
        p.add_run(r["Title"] + "\n").bold = True
        p.add_run(r["Channel"] + "\n")
        p.add_run(f"Published: {r['Published']} | {r['Duration (min)']} min\n")
        p.add_run(r["URL"])
    return doc


# -------------------------
# UI
# -------------------------
st.title("🎯 VidIntel — Multilingual YouTube Discovery")

st.markdown(
    "Search and filter YouTube videos by **language**, **region**, **date**, "
    "**duration**, and export results for research or monitoring."
)

with st.sidebar:
    st.header("🔎 Search Filters")

    query = st.text_input("Topic / Query", " ")

    lang = st.selectbox(
        "Language",
        [
            ("English", "en"),
            ("Spanish", "es"),
            ("French", "fr"),
            ("German", "de"),
            ("Russian", "ru"),
            ("Arabic", "ar"),
            ("Persian (Farsi)", "fa"),
            ("Japanese", "ja"),
            ("Korean", "ko"),
        ],
        format_func=lambda x: x[0]
    )[1]

    REGIONS = [
        ("Any region", None),

        # Spanish-speaking
        ("ES (Spain — Europe)", "ES"),
        ("MX (Mexico — North America)", "MX"),
        ("AR (Argentina — South America)", "AR"),
        ("CO (Colombia — South America)", "CO"),
        ("CL (Chile — South America)", "CL"),
        ("PE (Peru — South America)", "PE"),
        ("DO (Dominican Republic — Caribbean)", "DO"),

        # Russian-speaking
        ("RU (Russia)", "RU"),
        ("KZ (Kazakhstan)", "KZ"),
        ("BY (Belarus)", "BY"),
        ("UA (Ukraine)", "UA"),

        # Arabic-speaking
        ("EG (Egypt)", "EG"),
        ("SA (Saudi Arabia)", "SA"),
        ("AE (United Arab Emirates)", "AE"),

        # Persian-speaking
        ("IR (Iran)", "IR"),
        ("AF (Afghanistan)", "AF"),

        # East Asia
        ("JP (Japan)", "JP"),
        ("KR (South Korea)", "KR"),

        # English-dominant
        ("US (United States)", "US"),
        ("GB (United Kingdom)", "GB"),
        ("CA (Canada)", "CA"),
        ("AU (Australia)", "AU"),
    ]

    region = st.selectbox(
        "Region",
        REGIONS,
        format_func=lambda x: x[0]
    )[1]

    date_filter = st.selectbox(
        "Date range",
        ["No filter", "Last 24 hours", "Last 72 hours", "Last 7 days", "This month", "This year"]
    )

    duration_filter = st.selectbox(
        "Duration",
        ["Any", "< 4 min", "5–10 min", "> 10 min"]
    )

    strict_lang = st.checkbox("Strict language filtering")
    max_results = st.slider("Max results", 5, 50, 20, step=5)

    run = st.button("🔍 Search")


# -------------------------
# Execution
# -------------------------
if run:
    with st.spinner("Searching YouTube…"):
        published_after = compute_published_after(date_filter)
        items = search_youtube(query, lang, region, max_results, published_after)

        if not items:
            st.warning("No results returned.")
            st.stop()

        ids = [it["id"]["videoId"] for it in items]
        details = fetch_video_details(ids)

        # Duration filtering
        if duration_filter != "Any":
            def ok(d):
                m = d / 60
                return (
                    (duration_filter == "< 4 min" and m < 4) or
                    (duration_filter == "5–10 min" and 5 <= m <= 10) or
                    (duration_filter == "> 10 min" and m > 10)
                )
            items = [
                it for it in items
                if ok(details.get(it["id"]["videoId"], {}).get("duration_sec", 0))
            ]

        if strict_lang:
            items = strict_language_filter(items, lang)

        df = to_dataframe(items, details)

    if df.empty:
        st.warning("No results after filtering.")
    else:
        st.success(f"✅ {len(df)} results")

        st.dataframe(
            df,
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("YouTube Link")
            }
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                "⬇️ Download CSV",
                df.to_csv(index=False).encode("utf-8"),
                "vidintel_results.csv",
                "text/csv"
            )

        with col2:
            st.download_button(
                "⬇️ Download TXT",
                export_txt(df).encode("utf-8"),
                "vidintel_results.txt",
                "text/plain"
            )

        with col3:
            doc = export_docx(df)
            if doc:
                from io import BytesIO
                buf = BytesIO()
                doc.save(buf)
                st.download_button(
                    "⬇️ Download Word",
                    buf.getvalue(),
                    "vidintel_results.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
