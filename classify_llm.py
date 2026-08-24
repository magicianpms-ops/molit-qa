#!/usr/bin/env python3
"""수집된 건축 질의를 LLM(gpt-5.4-nano)로 안전/품질/건축 일반 단일 분류.

- 결과는 `qa/llm_cat.json`(id→분류)에 캐시. 이미 있는 id는 건너뜀(재실행·증분 저렴).
- build_browse.py가 이 캐시를 우선 사용(없으면 키워드 폴백).
- OpenAI 키는 lh `.env.local`에서 로드. 배치(기본 25건/호출)로 토큰 절약.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from build_browse import collect  # id·title·q·a 재사용

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "qa" / "llm_cat.json"
MODEL = "gpt-5.4-nano"

# 키 탐색 순서: 환경변수(CI에서는 이 경로) → 프로젝트 로컬 .openai_key
#              → MOLITQA_KEY_FILE로 지정한 외부 파일(로컬 폴백)
import os
KEY_SOURCES = [ROOT / ".openai_key"]
if os.environ.get("MOLITQA_KEY_FILE"):
    KEY_SOURCES.append(Path(os.environ["MOLITQA_KEY_FILE"]))

SYS = ("너는 대한민국 건축 관련 민원/질의를 정확히 하나로 분류한다.\n"
       "- 안전: 시공·건설 안전, 재해/붕괴/추락, 안전관리계획, 구조안전, "
       "방화·피난·내화·소방, 해체·가설·흙막이 등 인명·구조 안전.\n"
       "- 품질: 자재·시험·품질관리, 감리·감독, 시공 품질, 하자, "
       "콘크리트·강도·복합자재 등 품질/감리.\n"
       "- 건축일반: 그 외 인허가·면적·용도·이격거리·일조·대수선 등 일반 건축법 문의.\n"
       "안전과 품질 둘 다 걸치면 질의의 '핵심 목적'이 인명·구조 안전이면 안전, "
       "자재·시공품질·감리면 품질으로 정한다.\n"
       'JSON 객체로만 답한다: {"results":[{"i":번호,"cat":"안전|품질|건축일반"}]}')

NORM = {"안전": "안전", "품질": "품질", "건축일반": "건축 일반", "건축 일반": "건축 일반"}


def load_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"].strip()
    for p in KEY_SOURCES:
        if p.exists():
            txt = p.read_text()
            m = re.search(r'(?:OPENAI_API_KEY\s*=\s*)?"?(sk-[^"\s\n]+)', txt)
            if m:
                return m.group(1).strip()
    raise SystemExit("OPENAI_API_KEY 없음: 환경변수나 프로젝트의 .openai_key 파일에 넣어주세요.")


def call(key, batch, retries=3):
    payload = [{"i": b["i"], "t": b["title"][:80], "q": b["q"][:220]} for b in batch]
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    for i in range(retries):
        try:
            r = urllib.request.urlopen(req, timeout=90)
            out = json.loads(r.read())
            content = out["choices"][0]["message"]["content"]
            usage = out.get("usage", {})
            return json.loads(content).get("results", []), usage
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
            if i == retries - 1:
                print(f"    배치 실패: {e}")
                return [], {}
            time.sleep(2 * (i + 1))
    return [], {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0, help="처리 상한(0=전체)")
    ap.add_argument("--redo", action="store_true", help="캐시 무시하고 전량 재분류")
    args = ap.parse_args()

    key = load_key()
    cache = {} if args.redo else (json.loads(CACHE.read_text("utf-8")) if CACHE.exists() else {})
    data = collect()
    todo = [d for d in data if d["id"] not in cache]
    if args.limit:
        todo = todo[: args.limit]
    print(f"전체 {len(data)} · 캐시 {len(cache)} · 이번 분류 대상 {len(todo)} (batch {args.batch})")

    tin = tout = done = 0
    for s in range(0, len(todo), args.batch):
        chunk = todo[s:s + args.batch]
        for n, d in enumerate(chunk):
            d["i"] = n
        results, usage = call(key, chunk)
        by_i = {r["i"]: r for r in results if isinstance(r, dict) and "i" in r}
        for n, d in enumerate(chunk):
            cat = NORM.get((by_i.get(n) or {}).get("cat", ""), "건축 일반")
            cache[d["id"]] = cat
        tin += usage.get("prompt_tokens", 0)
        tout += usage.get("completion_tokens", 0)
        done += len(chunk)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
        print(f"  {done}/{len(todo)} 완료 (누적 토큰 in {tin:,} / out {tout:,})")
        time.sleep(0.3)

    from collections import Counter
    c = Counter(cache.values())
    # gpt-5.4-nano 대략 단가(가정): in $0.05/1M, out $0.40/1M
    cost = tin / 1e6 * 0.05 + tout / 1e6 * 0.40
    print(f"\n완료 · 캐시 총 {len(cache)}건 · 분포 {dict(c)}")
    print(f"이번 토큰 in {tin:,} / out {tout:,} · 추정비용 약 ${cost:.4f} (≈{cost*1400:.0f}원)")
    print(f"캐시: {CACHE}")


if __name__ == "__main__":
    sys.exit(main())
