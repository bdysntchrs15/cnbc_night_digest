import os, re
from datetime import datetime, time, timedelta
from urllib.parse import urlparse
import feedparser
from dateutil import parser as dtp
import pytz

# ---- 설정 ----
KST = pytz.timezone("Asia/Seoul")
WINDOW_END = time(6, 0)     # 오늘 06:00 KST
WINDOW_HOURS = 24           # 전날 06:00 ~ 오늘 06:00

# ---- 유틸 ----
def day_window_6to6(now: datetime | None = None):
    """
    KST 기준 '전날 06:00 ~ 오늘 06:00' 절대 구간.
    언제 실행해도 '오늘 06:00'을 end로 고정해 24시간 창을 만든다.
    """
    now = now.astimezone(KST) if now else datetime.now(KST)
    end = KST.localize(datetime.combine(now.date(), WINDOW_END))
    start = end - timedelta(hours=WINDOW_HOURS)
    return start, end

def to_kst(dt_any):
    """문자열/naive datetime을 KST로 변환. 실패 시 None."""
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

def clean_summary(raw: str, limit: int = 600) -> str:
    """
    RSS summary/description을 요약 힌트로 사용하기 위해
    - HTML 태그 제거
    - 공백 정리
    - 길이 컷
    """
    if not raw:
        return ""
    # 태그 제거
    txt = re.sub(r"<[^>]+>", " ", raw)
    # HTML 엔터티 간단 정리
    txt = (txt.replace("&nbsp;", " ")
              .replace("&amp;", "&")
              .replace("&lt;", "<")
              .replace("&gt;", ">")
              .replace("&quot;", '"')
              .replace("&#39;", "'"))
    # 공백 정규화
    txt = re.sub(r"\s+", " ", txt).strip()
    # 길이 컷
    if limit and len(txt) > limit:
        txt = txt[:limit].rstrip() + "…"
    return txt

# ---- 메인 ----
def main():
    os.makedirs("out", exist_ok=True)
    start_kst, end_kst = day_window_6to6()

    items = []
    for url in load_feeds():
        fp = feedparser.parse(url)
        src = source_name(fp.feed, url)
        for e in fp.entries:
            title = (e.get("title") or "").strip()
            link  = (e.get("link")  or "").strip()
            if not title or not link:
                continue

            # 발행 시각 후보 → KST 변환
            dt_raw = (
                e.get("published")
                or e.get("updated")
                or e.get("created")
                or e.get("pubDate")
                or None
            )
            pub_kst = to_kst(dt_raw)
            if pub_kst is None:
                continue

            # 절대 구간 필터: 전날 06:00 ~ 오늘 06:00
            if not (start_kst <= pub_kst <= end_kst):
                continue

            # RSS summary/description 추출(요약 힌트로 사용)
            summary_raw = (
                e.get("summary")
                or e.get("description")
                or (e.get("summary_detail", {}) or {}).get("value")
                or ""
            )
            summary = clean_summary(summary_raw, limit=600)

            items.append({
                "title": re.sub(r"\s+", " ", title),
                "link": link.split("#")[0],
                "src": src,
                "ts": pub_kst,
                "date_str": pub_kst.strftime("%Y-%m-%d"),
                "time_str": pub_kst.strftime("%H:%M"),
                "summary": summary,
            })

    # 중복 제거(링크+제목 보조) 및 최신순 정렬
    seen = set()
    uniq = []
    for it in sorted(items, key=lambda x: x["ts"], reverse=True):
        key = (it["link"].split("?")[0].lower(), it["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # 헤더 날짜(오늘 날짜) 및 윈도 문자열
    header_date = end_kst.strftime("%Y-%m-%d")
    window_str  = f'{start_kst.strftime("%m/%d %H:%M")}∼{end_kst.strftime("%m/%d %H:%M")} KST'

    def row(i):
        # 항목에 KST 시간/날짜를 명시(프롬프트 규칙 6(d)와 호환)
        desc = f'<div class="desc">{i["summary"]}</div>' if i.get("summary") else ""
        return (
            f'<li>'
            f'<span class="t">{i["time_str"]}</span> '
            f'<span class="d">{i["date_str"]}</span> · '
            f'<strong>{i["src"]}</strong> · '
            f'<a href="{i["link"]}">{i["title"]}</a>'
            f'{desc}'
            f'</li>'
        )

    body = "\n".join(row(i) for i in uniq) if uniq else \
           '<li>수집된 항목이 없습니다. (창: 전날 06:00∼오늘 06:00 KST)</li>'

    html = f"""<!doctype html><meta charset="utf-8">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto;max-width:860px;margin:40px auto;line-height:1.6}}
h1{{margin-bottom:.2rem}} ul{{padding-left:1.2rem}} li{{margin:.55rem 0}}
small{{color:#666}} .t{{font-variant-numeric:tabular-nums}} .d{{margin-left:.35rem;color:#555}}
.desc{{margin:.35rem 0 .1rem;color:#333}}
a{{text-decoration:none}} a:hover{{text-decoration:underline}}
</style>
<h1>간밤 CNBC 주요 뉴스 — {header_date}</h1>
<small>윈도: {window_str} · 피드 6종 · 중복 제거</small>
<ul>
{body}
</ul>
"""

    with open("out/daily.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(f"out/{header_date}.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"OK: {len(uniq)} items → out/daily.html, out/{header_date}.html")
    print(f"Window: {start_kst.isoformat()} ∼ {end_kst.isoformat()}")

if __name__ == "__main__":
    main()
