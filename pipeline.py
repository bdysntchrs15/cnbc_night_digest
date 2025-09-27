import os, re
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
import feedparser
from dateutil import parser as dtp
import pytz

# 설정
KST = pytz.timezone("Asia/Seoul")
WINDOW_START_HHMM = (22, 0)  # 전날 22:00
WINDOW_END_HHMM   = (6, 0)   # 당일 06:00

def last_night_window(now=None):
    """전날 22:00 ~ 오늘 06:00 (KST) 절대 구간 반환"""
    now = now or datetime.now(KST)
    end = KST.localize(datetime.combine(now.date(), time(*WINDOW_END_HHMM)))
    start = end - timedelta(hours=8)
    return start, end

def to_kst(dt_any):
    """문자열/naive datetime을 KST로 변환, 실패 시 None"""
    if not dt_any:
        return None
    if isinstance(dt_any, datetime):
        if dt_any.tzinfo is None:
            dt_any = pytz.utc.localize(dt_any)
        return dt_any.astimezone(KST)
    try:
        dt = dtp.parse(dt_any)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(KST)
    except Exception:
        return None

def source_name(feed, fallback_url):
    return (feed.get("title") or urlparse(fallback_url).netloc).strip()

def load_feeds(path="feeds.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

def main():
    os.makedirs("out", exist_ok=True)
    start_kst, end_kst = last_night_window()
    items = []

    # 수집
    for url in load_feeds():
        fp = feedparser.parse(url)
        src = source_name(fp.feed, url)
        for e in fp.entries:
            title = (e.get("title") or "").strip()
            link  = (e.get("link")  or "").strip()
            if not title or not link:
                continue
            # 발행시각 후보
            dt_raw = e.get("published") or e.get("updated") or e.get("created") or e.get("pubDate")
            pub_kst = to_kst(dt_raw)
            if pub_kst is None:
                continue
            # 절대 구간 필터
            if not (start_kst <= pub_kst <= end_kst):
                continue
            items.append({
                "title": re.sub(r"\s+", " ", title),
                "link": link.split("#")[0],
                "src": src,
                "ts": pub_kst,
            })

    # 중복 제거(링크+제목 보조)
    seen = set()
    uniq = []
    for it in sorted(items, key=lambda x: x["ts"], reverse=True):
        key = (it["link"].split("?")[0].lower(), it["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # 출력 HTML 생성
    today = end_kst.strftime("%Y-%m-%d")
    window_str = f'{start_kst.strftime("%m/%d %H:%M")}∼{end_kst.strftime("%m/%d %H:%M")} KST'

    def row(i):
        t = i["ts"].strftime("%H:%M")
        return f'<li><span>{t}</span> · <strong>{i["src"]}</strong> · <a href="{i["link"]}">{i["title"]}</a></li>'

    if uniq:
        body = "\n".join(row(i) for i in uniq)
    else:
        body = '<li>수집된 항목이 없습니다. (간밤 창: 전날 22:00∼당일 06:00 KST)</li>'

    html = f"""<!doctype html><meta charset="utf-8">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto;max-width:840px;margin:40px auto;line-height:1.6}}
h1{{margin-bottom:.2rem}} ul{{padding-left:1.2rem}} li{{margin:.45rem 0}}
small{{color:#666}}
</style>
<h1>간밤 CNBC 주요 뉴스 — {today}</h1>
<small>윈도: {window_str} · 피드 6종 · 중복 제거</small>
<ul>
{body}
</ul>
"""
    # 최신본과 날짜본 저장
    with open("out/daily.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(f"out/{today}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: {len(uniq)} items → out/daily.html, out/{today}.html")

if __name__ == "__main__":
    main()
