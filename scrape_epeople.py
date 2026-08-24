#!/usr/bin/env python3
"""
국민신문고(epeople.go.kr) 건축 안전·품질 질의응답 스크래퍼 (소스②).

소스①과 달리 '건축' 카테고리가 없어 **키워드 검색**으로 필터한다.
- 세션: GET 목록 → _csrf 토큰 + 쿠키 확보
- 목록: POST pttnSmlrCaseList.npaid (searchWord=건축 키워드, pageIndex) → 행 파싱
- 상세: 2단계 — ① crtfAjax 인증(X-CSRF-TOKEN 헤더) → ② smlrCaseDetail POST
        → .samBox(질의/답변) 파싱
- 저장: 소스①과 동일 스키마의 MD(`qa/epeople/`) + 증빙 스냅샷(`qa/snapshots/`)
        + 별도 색인 `qa/index_epeople.json`

소스①의 순수 헬퍼(분류·정규화·스냅샷)를 재사용한다. 의존성 없음(stdlib).
"""
import argparse
import hashlib
import html
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from scrape_molit import classify, html_to_text, norm_date, yaml_list

BASE = "https://www.epeople.go.kr"
LIST_URL = f"{BASE}/nep/pttn/gnrlPttn/pttnSmlrCaseList.npaid"
CRTF_URL = f"{BASE}/nep/pttn/gnrlPttn/pttnSmlrCaseCrtfAjax.npaid"
DETAIL_URL = f"{BASE}/nep/pttn/gnrlPttn/pttnSmlrCaseDetail.npaid"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "qa" / "epeople"
SNAP_DIR = ROOT / "qa" / "snapshots"
INDEX_PATH = ROOT / "qa" / "index_epeople.json"

# 건축 안전·품질 검색 키워드(기본) — 필요시 --keywords로 교체
DEFAULT_KEYWORDS = [
    "건축 안전", "건축물 구조안전", "건축 품질관리", "건축 감리",
    "가설건축물 안전", "방화구획", "피난 건축", "내진 건축물",
    "건축공사 품질", "해체공사 안전", "건축자재 품질",
]


def make_session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Referer", LIST_URL)]
    # 세션 쿠키 + CSRF 토큰 확보
    home = op.open(LIST_URL, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r'name="_csrf" value="([^"]+)"', home)
    csrf = m.group(1) if m else ""
    return op, csrf


def post(op, url, data, csrf, retries=3):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("X-CSRF-TOKEN", csrf)
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("Referer", LIST_URL)
    for i in range(retries):
        try:
            with op.open(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 — 시스템 경계, 재시도
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return ""


def search_page(op, csrf, keyword, page):
    data = {
        "_csrf": csrf, "pageIndex": page, "recordCountPerPage": 10,
        "searchWord": keyword, "searchWordType": "1",
    }
    htmltxt = post(op, LIST_URL, data, csrf)
    rows = re.findall(
        r"fn_detail\(this,'([^']+)','([^']+)'\);\">(.*?)</a>", htmltxt, re.S)
    out = []
    for sn, ty, ti in rows:
        ti = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", ti))).strip()
        out.append((sn, ty, ti))
    return out


def fetch_detail(op, csrf, sn, ty):
    data = {
        "_csrf": csrf, "pageIndex": 1, "recordCountPerPage": 10,
        "epUnionSn": sn, "dutySctnNm": ty, "searchWord": "",
    }
    crtf = post(op, CRTF_URL, data, csrf)
    if '"returnMsg":"success"' not in crtf:
        return None
    return post(op, DETAIL_URL, data, csrf)


def parse_detail(detail_html):
    """.samBox 블록(질의/답변)에서 제목·질의·답변·날짜 추출."""
    if not detail_html:
        return {}
    blocks = re.findall(
        r'<div class="samBox([^"]*)">.*?<span>([^<]+)</span>.*?<div class="sam_cont">(.*?)</div>\s*</div>',
        detail_html, re.S)
    d = {"title": "", "q": "", "a": "", "date": ""}
    for cls, label, cont in blocks:
        dm = re.search(r'class="samC_date">([^<]+)<', cont)
        tm = re.search(r'class="samC_top"><strong>(.*?)</strong>', cont, re.S)
        text = html_to_text(re.sub(r'<span class="samC_date".*?</span>', "", cont, flags=re.S))
        if "ans" in cls or "답변" in label:
            d["a"] = text
        else:
            if tm and not d["title"]:
                d["title"] = html_to_text(tm.group(1))
            if dm and not d["date"]:
                d["date"] = dm.group(1).strip()
            d["q"] = text
    return d if (d["q"] or d["a"]) else {}


def to_md(sn, ty, list_title, d, snapshot, captured):
    title = d.get("title") or list_title
    q, a = d.get("q", ""), d.get("a", "")
    full = f"{title}\n{q}\n{a}"
    tags, hits = classify(full)
    posted = norm_date(d.get("date", ""))
    h = hashlib.sha1(full.encode("utf-8")).hexdigest()[:12]
    type_nm = {"taol": "유권해석/유사사례", "tqapttn": "민원질의응답"}.get(ty, ty)
    meta = {
        "source": "epeople", "faq_id": sn, "ep_type": ty, "type_nm": type_nm,
        "category": "건축(검색)", "title": title, "dept": "", "agency": "국민신문고",
        "posted": posted, "updated": posted, "tags": tags, "sq_relevant": bool(tags),
        "matched_kw": hits, "url": LIST_URL, "snapshot": snapshot,
        "captured": captured, "hash": h, "scraped_at": date.today().isoformat(),
    }
    fm = [
        "---", "source: epeople", f'faq_id: "{sn}"', f"ep_type: {ty}",
        f'type_nm: "{type_nm}"', "category: 건축(검색)",
        f'title: "{title.replace(chr(34), chr(39))}"', 'agency: "국민신문고"',
        f"posted: {posted}", f"tags: {yaml_list(tags)}",
        f"sq_relevant: {str(meta['sq_relevant']).lower()}",
        f"matched_kw: {yaml_list(hits)}", f"url: {LIST_URL}",
        f"snapshot: {snapshot}", f"captured: {captured}", f"hash: {h}",
        f"scraped_at: {meta['scraped_at']}", "---", "",
        f"# {title}", "", f"> 출처: 국민신문고 · 유형: {type_nm} · epUnionSn `{sn}`", "",
        "## 질의내용", "", q or "_(없음)_", "",
        "## 답변내용", "", a or "_(없음)_", "",
    ]
    return "\n".join(fm), meta


def snapshot(sn, title, detail_html, captured):
    import gzip
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z_-]", "_", sn)
    gz = SNAP_DIR / f"ep_{safe}.html.gz"
    rel = f"snapshots/ep_{safe}.html.gz"
    if gz.exists():
        return rel
    m = re.search(r'<article id="txt">.*?</article>', detail_html, re.S)
    frag = m.group(0) if m else "<p>(본문 추출 실패)</p>"
    doc = (f'<!doctype html><meta charset="utf-8"><title>[보관본] {html.escape(title)}</title>'
           f'<div style="max-width:820px;margin:24px auto;font-family:sans-serif">'
           f'<p style="background:#eef1f6;padding:10px">출처: 국민신문고 · epUnionSn {html.escape(sn)} · '
           f'캡처일: {captured} · 원문 삭제 대비 로컬 보관본</p>{frag}</div>')
    with gzip.open(gz, "wt", encoding="utf-8") as f:
        f.write(doc)
    return rel


def load_index():
    return json.loads(INDEX_PATH.read_text("utf-8")) if INDEX_PATH.exists() else {}


def save_index(idx):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2), "utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=2, help="키워드당 목록 페이지 수")
    ap.add_argument("--keywords", nargs="*", help="검색 키워드(미지정 시 기본 세트)")
    ap.add_argument("--new-only", action="store_true", help="색인에 있는 건은 상세요청 스킵")
    ap.add_argument("--no-snapshot", action="store_true", help="증빙 스냅샷 저장 안 함")
    ap.add_argument("--delay", type=float, default=0.8, help="요청 간 지연(초)")
    args = ap.parse_args()

    kws = args.keywords or DEFAULT_KEYWORDS
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    idx = load_index()
    op, csrf = make_session()
    print(f"[epeople] 키워드 {len(kws)}개 × {args.pages}p, csrf={'OK' if csrf else '실패'}")

    seen, new, upd, skip, snapped = set(), 0, 0, 0, 0
    for kw in kws:
        print(f"  검색: '{kw}'")
        for pg in range(1, args.pages + 1):
            rows = search_page(op, csrf, kw, pg)
            if not rows:
                break
            for sn, ty, list_title in rows:
                if sn in seen:
                    continue
                seen.add(sn)
                if args.new_only and sn in idx:
                    skip += 1
                    continue
                detail = fetch_detail(op, csrf, sn, ty)
                d = parse_detail(detail)
                if not d:
                    skip += 1
                    time.sleep(args.delay)
                    continue
                snap, captured = "", ""
                if not args.no_snapshot:
                    captured = idx.get(sn, {}).get("captured") or date.today().isoformat()
                    snap = snapshot(sn, d.get("title") or list_title, detail, captured)
                    snapped += 1
                md, meta = to_md(sn, ty, list_title, d, snap, captured)
                fpath = OUT_DIR / f"ep_{re.sub(r'[^0-9A-Za-z_-]', '_', sn)}.md"
                prev = idx.get(sn, {})
                if prev.get("hash") == meta["hash"] and fpath.exists():
                    skip += 1
                else:
                    fpath.write_text(md, "utf-8")
                    upd += (sn in idx)
                    new += (sn not in idx)
                idx[sn] = {k: meta[k] for k in
                           ("title", "tags", "sq_relevant", "posted", "type_nm",
                            "hash", "snapshot", "captured", "matched_kw")}
                time.sleep(args.delay)
            save_index(idx)
    save_index(idx)
    sq = sum(1 for v in idx.values() if v["sq_relevant"])
    print(f"\n완료: 신규 {new} / 갱신 {upd} / 스킵 {skip} | 색인 총 {len(idx)}건 "
          f"(안전·품질 {sq}) | 스냅샷 {snapped}")
    print(f"저장: {OUT_DIR} · 색인: {INDEX_PATH}")


if __name__ == "__main__":
    sys.exit(main())
