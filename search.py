#!/usr/bin/env python3
"""수집된 질의회신 MD 라이브러리 통합 검색 CLI (의존성 없음).

소스① 국토부 민원마당 + 소스② 국민신문고를 함께 검색한다.

예)
  python3 search.py 방화                 # 제목+본문에 '방화'
  python3 search.py 자재 --tag 품질       # 품질 태그 + '자재'
  python3 search.py --sq                  # 안전·품질 관련 전체
  python3 search.py 감리 --src epeople    # 국민신문고만
  python3 search.py 안전관리계획 --preview # 답변 미리보기
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {
    "molit": {"index": ROOT / "qa" / "index.json", "dir": ROOT / "qa" / "molit",
              "name": "국토부", "fname": lambda k: f"{k}.md"},
    "epeople": {"index": ROOT / "qa" / "index_epeople.json", "dir": ROOT / "qa" / "epeople",
                "name": "신문고", "fname": lambda k: "ep_" + re.sub(r"[^0-9A-Za-z_-]", "_", k) + ".md"},
}


def read_body(src, key):
    cfg = SOURCES[src]
    p = cfg["dir"] / cfg["fname"](key)
    return p.read_text("utf-8") if p.exists() else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="", help="검색어(제목+본문)")
    ap.add_argument("--tag", choices=["안전", "품질"], help="태그 필터")
    ap.add_argument("--sq", action="store_true", help="안전·품질 관련만")
    ap.add_argument("--src", choices=["molit", "epeople"], help="특정 소스만")
    ap.add_argument("-n", type=int, default=20, help="최대 결과 수")
    ap.add_argument("--preview", action="store_true", help="답변 미리보기 표시")
    args = ap.parse_args()

    q = args.query.strip()
    hits = []
    srcs = [args.src] if args.src else list(SOURCES)
    for src in srcs:
        idxp = SOURCES[src]["index"]
        if not idxp.exists():
            continue
        idx = json.loads(idxp.read_text("utf-8"))
        for key, m in idx.items():
            if args.sq and not m.get("sq_relevant"):
                continue
            if args.tag and args.tag not in m.get("tags", []):
                continue
            body = read_body(src, key) if q else ""
            if q and q not in (m.get("title", "") + " " + body):
                continue
            hits.append((src, key, m, body))

    if not hits and not any(SOURCES[s]["index"].exists() for s in srcs):
        print("색인이 없습니다. 먼저 scrape_molit.py / scrape_epeople.py 를 실행하세요.")
        return

    hits.sort(key=lambda x: x[2].get("updated") or x[2].get("posted") or "", reverse=True)
    print(f"검색결과 {len(hits)}건" + (f" (상위 {args.n})" if len(hits) > args.n else ""))
    print("-" * 74)
    for src, key, m, body in hits[: args.n]:
        tags = "".join(f"#{t} " for t in m.get("tags", []))
        label = SOURCES[src]["name"]
        meta2 = m.get("dept") or m.get("type_nm") or ""
        print(f"[{label}] {m.get('title', '')}")
        print(f"    {meta2} | {m.get('updated') or m.get('posted', '')} | {tags}")
        if args.preview and body:
            ans = re.split(r"## (?:회신내용|답변내용)", body, 1)
            if len(ans) == 2:
                print(f"    → {re.sub(r'\\s+', ' ', ans[1]).strip()[:160]}")
        print()


if __name__ == "__main__":
    main()
