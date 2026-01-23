
# =========================================================
# VidIntel — YouTube + RSS Article Discovery (Multilingual)
# Fully Integrated Streamlit Application
# =========================================================

import re
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Optional dependencies
try:
    from langdetect import detect
except Exception:
    detect = None

try:
    from docx import Document
except Exception:
    Document = None


# -------------------------
# Streamlit Configuration
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


# =========================================================
# YOUTUBE SEARCH (your existing logic, preserved)
# =========================================================

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
        dur_iso = item.get("contentDetails", {}).get("duration")
        duration_sec = iso8601_to_seconds(dur_iso) if dur_iso else 0
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


def youtube_to_dataframe(items, details):
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
    doc.add_heading("VidIntel YouTube Results", level=1)
    for _, r in df.iterrows():
        p = doc.add_paragraph()
        p.add_run(r["Title"] + "\n").bold = True
        p.add_run(r["Channel"] + "\n")
        p.add_run(f"Published: {r['Published']} | {r['Duration (min)']} min\n")
        p.add_run(r["URL"])
    return doc


# =========================================================
# ARTICLE SEARCH (RSS)
# =========================================================

CURATED_RSS = {
    "en": {
        "BBC": "https://feeds.bbci.co.uk/news/rss.xml",
        "Reuters": "https://feeds.reuters.com/reuters/worldNews",
        "AP News": "https://apnews.com/rss",
    },
    "es": {
        "El País": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
        "La Nación (AR)": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
        "El Universal (MX)": "https://www.eluniversal.com.mx/rss.xml",
    },
    "fr": {
        "Le Monde": "https://www.lemonde.fr/rss/une.xml",
        "France 24": "https://www.france24.com/fr/rss",
    },
    "de": {
        "Der Spiegel": "https://www.spiegel.de/international/index.rss",
        "DW": "https://rss.dw.com/xml/rss-en-all",
    },
    "ru": {
        "Meduza": "https://meduza.io/rss/all",
        "Kommersant": "https://www.kommersant.ru/RSS/news.xml",
    },
    "ar": {
        "Al Jazeera": "https://www.aljazeera.net/aljazeera/rss",
        "Al Arabiya": "https://english.alarabiya.net/feed/rss",
    },
    "fa": {"BBC Persian": "https://feeds.bbci.co.uk/persian/rss.xml"},
    "ja": {"NHK": "https://www3.nhk.or.jp/rss/news/cat0.xml"},
    "ko": {"Yonhap": "https://en.yna.co.kr/rss/all.xml"},
}


def discover_rss_feeds(site_url, timeout=10):
    feeds = []
    try:
        r = requests.get(site_url, timeout=timeout, headers={"User-Agent": "VidIntelBot/1.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("link", type=["application/rss+xml", "application/atom+xml"]):
            href = link.get("href")
            if href:
                feeds.append(urljoin(site_url, href))
    except Exception:
        pass

    # fallback guesses
    for path in ["/rss", "/rss.xml", "/feed"]:
        feeds.append(urljoin(site_url, path))

    return list(set(feeds))


def get_article_sources(language_code, user_url=None):
    sources = {}
    sources.update(CURATED_RSS.get(language_code, {}))

    if user_url:
        attempts = discover_rss_feeds(user_url)
        for i, feed in enumerate(attempts[:3]):
            sources[f"User Source {i+1}"] = feed

    return sources


@st.cache_data(ttl=600)
def fetch_articles(sources, days_back=7, keyword=None):
    from dateutil import parser as dateparser
    rows = []

    cutoff = datetime.now(timezone.utc).timestamp() - days_back * 86400

    for name, url in sources.items():
        try:
            feed = requests.get(url, timeout=10).text
        except Exception:
            continue

        parsed = BeautifulSoup(feed, "xml")
        items = parsed.find_all("item")

        for entry in items:
            title = entry.title.text if entry.title else ""
            link = entry.link.text if entry.link else ""
            pub = entry.pubDate.text if entry.pubDate else ""
            summary_html = entry.description.text if entry.description else ""

            try:
                ts = dateparser.parse(pub).timestamp()
            except Exception:
                ts = None

            if ts and ts < cutoff:
                continue

            blob = f"{title} {summary_html}".lower()
            if keyword and keyword.lower() not in blob:
                continue

            rows.append({
                "Title": title,
                "Source": name,
                "Published": pub,
                "URL": link,
                "Summary": BeautifulSoup(summary_html, "html.parser").get_text().strip()
            })

    return pd.DataFrame(rows)


def export_articles_docx(df):
    if not Document:
        return None
    doc = Document()
    doc.add_heading("VidIntel Article Results", level=1)
    for _, r in df.iterrows():
        p = doc.add_paragraph()
        p.add_run(r["Title"] + "\n").bold = True
        p.add_run(f"{r['Source']} — {r['Published']}\n")
        p.add_run(r["URL"] + "\n")
        p.add_run("\nSummary:\n")
        p.add_run(r["Summary"] + "\n")
    return doc


# =========================================================
# UI — Main App
# =========================================================

st.title("🎯 VidIntel — YouTube + Article Discovery")

with st.sidebar:
    st.header("🔎 Search Filters")

    content_type = st.selectbox(
        "Content Type",
        ["Videos", "Articles", "Both"]
    )

    keyword = st.text_input("Keyword / Query", "")

    # YouTube filters
    lang = st.selectbox(
        "Video Language",
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

    region = st.selectbox(
        "Region",
        [
            ("Any region", None),
            ("US", "US"), ("GB", "GB"), ("CA", "CA"), ("AU", "AU"),
            ("MX", "MX"), ("ES", "ES"), ("AR", "AR"), ("CO", "CO"),
            ("RU", "RU"), ("KZ", "KZ"), ("UA", "UA"),
            ("EG", "EG"), ("SA", "SA"),
            ("JP", "JP"), ("KR", "KR"),
        ],
        format_func=lambda x: x[0]
    )[1]

    date_filter = st.selectbox(
        "Video Date Range",
        ["No filter", "Last 24 hours", "Last 72 hours", "Last 7 days", "This month", "This year"]
    )

    duration_filter = st.selectbox(
        "Duration",
        ["Any", "< 4 min", "5–10 min", "> 10 min"]
    )

    strict_lang = st.checkbox("Strict language filtering")
    max_results = st.slider("Max video results", 5, 50, 20, step=5)

    st.markdown("---")

    # Article settings
    st.subheader("Article Settings")
    article_lang = st.selectbox(
        "Article Language",
        list(CURATED_RSS.keys()),
        index=0
    )

    days_back = st.slider("Article Days Back", 1, 30, 7)
    user_site = st.text_input("Auto-discover RSS from site (optional)", "")

    run = st.button("🔍 Search")


# =========================================================
# Execution
# =========================================================

if run and not keyword.strip():
    st.warning("Please enter a keyword.")
    st.stop()

videos_df = None
articles_df = None

if run:
    # -------------------------
    # VIDEOS
    # -------------------------
    if content_type in ["Videos", "Both"]:
        with st.spinner("Searching YouTube…"):
            published_after = compute_published_after(date_filter)
            items = search_youtube(keyword, lang, region, max_results, published_after)

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

            videos_df = youtube_to_dataframe(items, details)

    # -------------------------
    # ARTICLES
    # -------------------------
    if content_type in ["Articles", "Both"]:
        with st.spinner("Fetching articles…"):
            sources = get_article_sources(article_lang, user_site or None)
            articles_df = fetch_articles(
                sources,
                days_back=days_back,
                keyword=keyword
            )


# =========================================================
# OUTPUT TABS
# =========================================================

tabs = st.tabs(["📺 Videos", "📰 Articles"])

# -------------------------
# VIDEOS TAB
# -------------------------
with tabs[0]:
    if videos_df is None:
        st.info("⚠️ Choose 'Videos' or 'Both' to search for YouTube content.")
    elif videos_df.empty:
        st.warning("No YouTube results.")
    else:
        st.success(f"Found {len(videos_df)} videos")

        st.dataframe(
            videos_df,
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("YouTube Link")
            }
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                "⬇️ CSV",
                videos_df.to_csv(index=False).encode("utf-8"),
                "videos.csv",
                "text/csv"
            )
        with col2:
            st.download_button(
                "⬇️ TXT",
                export_txt(videos_df).encode("utf-8"),
                "videos.txt",
                "text/plain"
            )
        with col3:
            doc = export_docx(videos_df)
            if doc:
                from io import BytesIO
                buf = BytesIO()
                doc.save(buf)
                st.download_button(
                    "⬇️ Word",
                    buf.getvalue(),
                    "videos.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )

# -------------------------
# ARTICLES TAB
# -------------------------
with tabs[1]:
    if articles_df is None:
        st.info("⚠️ Choose 'Articles' or 'Both' to search for news content.")
    elif articles_df.empty:
        st.warning("No article results.")
    else:
        st.success(f"Found {len(articles_df)} articles")

        # Pagination
        page_size = 10
        total_pages = max(1, (len(articles_df) - 1) // page_size + 1)
        page = st.number_input("Page", 1, total_pages, 1)
        start = (page - 1) * page_size
        end = start + page_size

        for _, row in articles_df.iloc[start:end].iterrows():
            with st.container(border=True):
                st.markdown(f"### {row['Title']}")
                st.markdown(f"**{row['Source']} — {row['Published']}**")
                with st.expander("Summary"):
                    st.write(row["Summary"])
                st.link_button("Open Article ↗", row["URL"])

        st.markdown("---")

        # Article exports
        col1, col2, col3 = st.columns(3)

        with col1:
            st.download_button(
                "⬇️ CSV",
                articles_df.to_csv(index=False).encode("utf-8"),
                "articles.csv",
                "text/csv"
            )

        with col2:
            txt = "\n\n".join(
                f"{r['Title']} ({r['Source']})\n{r['Published']}\n{r['URL']}\n\n{r['Summary']}"
                for _, r in articles_df.iterrows()
            )
            st.download_button(
                "⬇️ TXT",
                txt.encode("utf-8"),
                "articles.txt",
                "text/plain"
            )

        with col3:
            doc = export_articles_docx(articles_df)
            if doc:
                from io import BytesIO
                buf = BytesIO()
                doc.save(buf)
                st.download_button(
                    "⬇️ Word",
                    buf.getvalue(),
                    "articles.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
