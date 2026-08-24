#!/usr/bin/env python3
"""
국토부 민원마당(eminwon.molit.go.kr) 건축 카테고리 FAQ 질의회신 스크래퍼.

- 소스: 국토교통부 민원마당 자주하는질문(FAQ), 카테고리 '건축'(category=2102)
- 목록: GET  /faqList.do?category=2102&pageIndex=N        (정적 HTML, 세션 쿠키)
- 상세: POST /faqContents.do  (faqId=ID)                  (구조화 테이블)
- 저장: qa/molit/{id}.md  (YAML frontmatter + 질의/회신 본문, 초경량)

의존성 없음(stdlib). 원본 이미지 대신 텍스트 MD만 남겨 용량을 최소화한다.
안전·품질 관련 여부는 키워드로 태깅(sq_relevant)하되, 건축 전건을 보존한다
(MD는 건당 수 KB로 무시할 수준이며, 과도한 필터링으로 유실되는 것을 막기 위함).
"""
import argparse
import hashlib
import html
import http.cookiejar
import gzip
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://eminwon.molit.go.kr"
CATEGORY_ARCH = "2102"  # 건축
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "qa" / "molit"
SNAP_DIR = ROOT / "qa" / "snapshots"   # 원문 증빙 스냅샷(gzip)
INDEX_PATH = ROOT / "qa" / "index.json"

# 건축 안전·품질 관련 태깅 키워드
SAFETY_KW = [
    "안전관리", "안전점검", "건설안전", "산업안전", "안전보건", "재해", "붕괴",
    "추락", "가설", "흙막이", "해체공사", "위험", "유해위험", "안전관리계획",
    "정밀안전", "구조안전", "내진", "방화", "내화", "피난", "소방",
]
QUALITY_KW = [
    "품질관리", "품질시험", "품질검사", "시험성적", "복합자재", "마감재료",
    "콘크리트", "강도", "배합", "자재", "레미콘", "철근", "감리", "감독",
    "부실시공", "하자", "시공상세", "구조계산", "구조도서",
]


def make_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA), ("Referer", BASE + "/faqList.do")]
    return op


def fetch(op, url, data=None, retries=3):
    body = urllib.parse.urlencode(data).encode() if data else None
    for i in range(retries):
        try:
            with op.open(url, data=body, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - 시스템 경계, 재시도
            if i == retries - 1:
                raise
            time.sleep(1.5 * (i + 1))
    return ""


def html_to_text(frag: str) -> str:
    """블록 태그를 개행으로 바꾼 뒤 태그 제거."""
    frag = re.sub(r"(?i)<\s*br\s*/?>", "\n", frag)
    frag = re.sub(r"(?i)</\s*(p|div|li|tr|h[1-6])\s*>", "\n", frag)
    frag = re.sub(r"<!--.*?-->", "", frag, flags=re.S)
    frag = re.sub(r"<[^>]+>", "", frag)
    frag = html.unescape(frag)
    lines = [ln.strip() for ln in frag.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def parse_list(page_html: str):
    """목록 페이지에서 (faq_id, title) 추출."""
    items = []
    for m in re.finditer(
        r"fn_select_faqContents\('(\d+)'\);\s*return false;\">([^<]+)</a>",
        page_html,
    ):
        items.append((m.group(1), html.unescape(m.group(2)).strip()))
    return items


def parse_last_page(page_html: str) -> int:
    nums = [int(n) for n in re.findall(r"fn_paging_faqList\((\d+)\)", page_html)]
    return max(nums) if nums else 1


LABELS = ["담당기관", "카테고리", "관련법령", "담당부서", "등록일자", "수정일자",
          "첨부파일", "질의내용", "회신내용"]


def parse_detail(detail_html: str) -> dict:
    """상세 table_view에서 라벨→값 매핑."""
    m = re.search(r'<table class="table_view".*?</table>', detail_html, flags=re.S)
    if not m:
        return {}
    blk = m.group(0)
    # th/td 셀을 순서대로 추출 (원본 HTML 보존)
    cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", blk, flags=re.S)
    # (label_text, raw_html) 시퀀스로 정리하되 빈 셀 제거
    seq = [(html_to_text(re.sub(r"<[^>]+>", "", c)).strip(), c) for c in cells]
    out = {}
    for i, (txt, _raw) in enumerate(seq):
        if txt in LABELS and i + 1 < len(seq):
            # 다음 셀이 값 (질의/회신은 개행 보존)
            out[txt] = html_to_text(seq[i + 1][1])
    return out


def make_snapshot(faq_id, title, url, detail_html, captured):
    """상세 원문(table_view)만 추린 self-contained HTML 증빙본을 gzip 저장.

    원문이 삭제/이관돼도 '그날 국토부가 이렇게 회신했다'를 보존한다.
    이미 있으면 덮어쓰지 않아 최초 캡처 시점을 유지한다.
    """
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    gz = SNAP_DIR / f"{faq_id}.html.gz"
    if gz.exists():
        return f"snapshots/{faq_id}.html.gz"
    m = re.search(r'<table class="table_view".*?</table>', detail_html, flags=re.S)
    table = m.group(0) if m else "<p>(본문 추출 실패)</p>"
    t = html.escape(title)
    doc = (
        "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        f"<title>[보관본] {t}</title>"
        "<style>body{font-family:'Apple SD Gothic Neo',sans-serif;max-width:820px;"
        "margin:24px auto;padding:0 16px;color:#1a2230;line-height:1.6}"
        ".cap{background:#eef1f6;border:1px solid #dde3ec;border-radius:8px;padding:10px 14px;"
        "font-size:13px;color:#54607a;margin-bottom:16px}"
        "table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #dde3ec;padding:8px 10px;text-align:left;vertical-align:top;font-size:14px}"
        "th{background:#f4f6f9;white-space:nowrap}</style></head><body>"
        f"<h2>{t}</h2>"
        f"<div class=\"cap\">출처: 국토교통부 민원마당 · 원문 URL: {html.escape(url)} · "
        f"캡처일: {captured} · faq_id: {faq_id}<br>"
        "※ 국토부 원문이 삭제·이관되어도 대조 가능한 로컬 보관본입니다.</div>"
        f"{table}</body></html>"
    )
    with gzip.open(gz, "wt", encoding="utf-8") as f:
        f.write(doc)
    return f"snapshots/{faq_id}.html.gz"


def classify(text: str):
    tags = []
    hit_s = [k for k in SAFETY_KW if k in text]
    hit_q = [k for k in QUALITY_KW if k in text]
    if hit_s:
        tags.append("안전")
    if hit_q:
        tags.append("품질")
    return tags, sorted(set(hit_s + hit_q))


def norm_date(s: str) -> str:
    m = re.search(r"(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})", s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def yaml_list(xs):
    return "[" + ", ".join(xs) + "]" if xs else "[]"


def to_md(faq_id, title, d, snapshot="", captured="") -> tuple[str, dict]:
    q = d.get("질의내용", "")
    a = d.get("회신내용", "")
    full = f"{title}\n{q}\n{a}"
    tags, hits = classify(full)
    laws = d.get("관련법령", "").strip()
    laws = "" if laws in ("-->", "-", "") else laws
    posted = norm_date(d.get("등록일자", ""))
    updated = norm_date(d.get("수정일자", ""))
    h = hashlib.sha1(full.encode("utf-8")).hexdigest()[:12]
    meta = {
        "source": "molit_eminwon",
        "faq_id": faq_id,
        "category": d.get("카테고리", "건축"),
        "title": title,
        "agency": d.get("담당기관", ""),
        "dept": d.get("담당부서", ""),
        "posted": posted,
        "updated": updated,
        "tags": tags,
        "sq_relevant": bool(tags),
        "matched_kw": hits,
        "laws": laws,
        "url": f"{BASE}/faqContents.do?faqId={faq_id}",
        "snapshot": snapshot,
        "captured": captured,
        "hash": h,
        "scraped_at": date.today().isoformat(),
    }
    fm = [
        "---",
        f"source: {meta['source']}",
        f"faq_id: {faq_id}",
        f"category: {meta['category']}",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f'agency: "{meta["agency"]}"',
        f'dept: "{meta["dept"]}"',
        f"posted: {posted}",
        f"updated: {updated}",
        f"tags: {yaml_list(tags)}",
        f"sq_relevant: {str(meta['sq_relevant']).lower()}",
        f"matched_kw: {yaml_list(hits)}",
        f'laws: "{laws}"',
        f"url: {meta['url']}",
        f"snapshot: {snapshot}",
        f"captured: {captured}",
        f"hash: {h}",
        f"scraped_at: {meta['scraped_at']}",
        "---",
        "",
        f"# {title}",
        "",
        "## 질의내용",
        "",
        q or "_(없음)_",
        "",
        "## 회신내용",
        "",
        a or "_(없음)_",
        "",
    ]
    return "\n".join(fm), meta


def load_index():
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text("utf-8"))
    return {}


def save_index(idx):
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(idx, ensure_ascii=False, indent=2), "utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=1, help="스크랩할 목록 페이지 수")
    ap.add_argument("--start", type=int, default=1, help="시작 페이지")
    ap.add_argument("--all", action="store_true", help="전체 페이지")
    ap.add_argument("--sq-only", action="store_true",
                    help="안전·품질 관련(sq_relevant)만 파일 저장")
    ap.add_argument("--new-only", action="store_true",
                    help="색인에 이미 있는 faq_id는 상세요청 없이 건너뜀(월간 갱신용)")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="원문 증빙 HTML 스냅샷(gzip) 저장 안 함")
    ap.add_argument("--delay", type=float, default=0.7, help="요청 간 지연(초)")
    args = ap.parse_args()

    op = make_opener()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    idx = load_index()

    # 세션 쿠키 확보 + 마지막 페이지 계산
    first = fetch(op, f"{BASE}/faqList.do?category={CATEGORY_ARCH}&pageIndex={args.start}")
    last = parse_last_page(first)
    end = last if args.all else min(last, args.start + args.pages - 1)
    print(f"[molit/건축] 목록 {args.start}~{end} 페이지 (감지된 마지막={last})")

    new, upd, skip, saved_sq, snapped = 0, 0, 0, 0, 0
    for pg in range(args.start, end + 1):
        page_html = first if pg == args.start else fetch(
            op, f"{BASE}/faqList.do?category={CATEGORY_ARCH}&pageIndex={pg}")
        items = parse_list(page_html)
        print(f"  p{pg}: {len(items)}건")
        for faq_id, title in items:
            if args.new_only and faq_id in idx:
                skip += 1  # 기존 항목 — 상세요청 없이 스킵(월간 갱신 효율)
                continue
            detail = fetch(op, f"{BASE}/faqContents.do", data={"faqId": faq_id})
            d = parse_detail(detail)
            if not d:
                skip += 1
                continue
            # 원문 증빙 스냅샷 — 최초 캡처일 유지, 없을 때만 생성
            snap, captured = "", ""
            if not args.no_snapshot:
                url = f"{BASE}/faqContents.do?faqId={faq_id}"
                captured = idx.get(faq_id, {}).get("captured") or date.today().isoformat()
                existed = (SNAP_DIR / f"{faq_id}.html.gz").exists()
                snap = make_snapshot(faq_id, title, url, detail, captured)
                if not existed:
                    snapped += 1
            md, meta = to_md(faq_id, title, d, snap, captured)
            if args.sq_only and not meta["sq_relevant"]:
                skip += 1
                time.sleep(args.delay)
                continue
            fpath = OUT_DIR / f"{faq_id}.md"
            prev = idx.get(faq_id, {})
            # 내용·스냅샷 경로가 모두 그대로일 때만 스킵(스냅샷 신규 부착 시 MD 갱신)
            if (prev.get("hash") == meta["hash"] and fpath.exists()
                    and prev.get("snapshot", "") == snap):
                skip += 1
            else:
                fpath.write_text(md, "utf-8")
                if faq_id in idx:
                    upd += 1
                else:
                    new += 1
            if meta["sq_relevant"]:
                saved_sq += 1
            idx[faq_id] = {k: meta[k] for k in
                           ("title", "tags", "sq_relevant", "posted", "updated",
                            "dept", "hash", "url", "snapshot", "captured", "matched_kw")}
            time.sleep(args.delay)
        save_index(idx)  # 페이지마다 저장 — 중단돼도 진행분 보존
    save_index(idx)
    print(f"\n완료: 신규 {new} / 갱신 {upd} / 스킵 {skip} "
          f"| 안전·품질 {saved_sq}건 | 신규 스냅샷 {snapped}건 | 색인 총 {len(idx)}건")
    print(f"저장 위치: {OUT_DIR}")
    print(f"색인: {INDEX_PATH}")


if __name__ == "__main__":
    sys.exit(main())
