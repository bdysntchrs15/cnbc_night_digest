import os, re
from datetime import datetime, time
from urllib.parse import urlparse
import feedparser
from dateutil import parser as dtp
import pytz

KST = pytz.timezone("Asia/Seoul")
NIGHT_START = time(22, 0)  # 포함
NIGHT_END   = time(6, 0)   # 포함

def in_night_kst(dt_kst: datetime) -> bool:
    t = dt_kst.timetz()
    return (t >= NIGHT_START) or (t <= NIGHT_END)

def to_kst(dt_any) -> datetime:
    try:
        dt = dtp.parse(dt_any)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(KST)
    except Exception:
        return datetime.now(KST)

def source_name(feed, fallback_url):
    return feed.get("title") or urlparse(fallback_url).netloc

def load_feeds(path="feeds.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

def main():
    os.makedirs("out", exist_ok=True)
    items = []
    for url in load_feeds():
        fp = feedparser.parse(url)
        src = source_name(fp.feed, url)
        for e in fp.entries:
            title = (e.get("title") or "").strip()
            link  = (e.get("link")  or "").strip()
            if not title or not link:
                continue
            # 발행 시각 후보
            dt = e.get("published") or e.get("updated") or e.get("created") or e.get("pubDate")
            dt_kst = to_kst(dt)
            if not in_night_kst(dt_kst):
                continue
            items.append({
                "title": re.sub(r"\s+", " ", title),
                "link": link,
                "src": src,
                "ts": dt_kst
            })

    # 중복 제거: 링크 기준 → 제목 보조
    seen = set()
    uniq = []
    for it in sorted(items, key=lambda x: x["ts"], reverse=True):
        key = (it["link"].split("?")[0], it["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # HTML 출력
    today = datetime.now(KST).strftime("%Y-%m-%d")
    def row(i):
        return f'<li><span>{i["ts"].strftime("%H:%M")}</span> · <strong>{i["src"]}</strong> · <a href="{i["link"]}">{i["title"]}</a></li>'

    html = f"""<!doctype html><meta charset="utf-8">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto;max-width:840px;margin:40px auto;line-height:1.6}}
h1{{margin-bottom:.2rem}} ul{{padding-left:1.2rem}} li{{margin:.4rem 0}}
small{{color:#666}}
</style>
<h1>간밤 CNBC 주요 뉴스 — {today}</h1>
<small>윈도: 22:00∼06:00 KST · 피드 6종 · 중복 제거</small>
<ul>
{''.join(row(i) for i in uniq)}
</ul>
"""
    # 최신본과 날짜본 둘 다 저장
    with open("out/daily.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(f"out/{today}.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: {len(uniq)} items → out/daily.html, out/{today}.html")

if __name__ == "__main__":
    main()
