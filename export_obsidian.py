#!/usr/bin/env python3
"""질의회신 아카이브를 옵시디언 볼트로 내보낸다.

- 대상 볼트: 기본 `~/Documents/Obsidian Vault` (그 안에 `질의회신 아카이브/` 폴더)
- 각 항목 = 노트 1개(frontmatter 속성: 분류/출처/부서/일자/원문 + 질의·회신 본문)
- 분류(안전/품질/건축 일반)는 LLM 결과(build_browse.collect가 반영) 사용
- 인덱스 노트: 메인 MOC + 분류별 3개(위키링크 목록)
- 재실행 시 폴더를 새로 쓴다(idempotent). 의존성 없음.
"""
import argparse
import gzip
import hashlib
import re
import shutil
import sys
from pathlib import Path

from build_browse import collect

DEFAULT_VAULT = Path.home() / "Documents" / "Obsidian Vault"
FOLDER = "질의회신 아카이브"
CATS = ["안전", "품질", "건축 일반"]
PROJ = Path(__file__).resolve().parent


def short_id(item):
    i = item["id"]
    return i if i.isdigit() else "EP" + hashlib.sha1(i.encode()).hexdigest()[:6]


def safe_name(item):
    title = re.sub(r'[\\/:*?"<>|#\^\[\]\n\r\t]', " ", item["title"]).strip()
    title = re.sub(r"\s+", " ", title)[:88].strip() or "무제"
    return f"{title} ({short_id(item)})"


def yaml_escape(s):
    return '"' + str(s).replace('"', "'") + '"'


def note_body(item, name):
    src = "국토부 민원마당" if item["src"] == "molit" else "국민신문고"
    ans_h = "회신내용" if item["src"] == "molit" else "답변내용"
    date = item["updated"] or item["posted"] or ""
    fm = [
        "---",
        f"분류: {item['cat']}",
        f"출처: {src}",
        f"담당: {yaml_escape(item['dept'])}" if item["dept"] else "담당: ",
        f"등록일: {item['posted']}" if item["posted"] else "등록일: ",
        f"수정일: {item['updated']}" if item["updated"] else "수정일: ",
        f"원문: {item['url']}",
        f"항목ID: {yaml_escape(item['id'])}",
        "aliases:",
        f"  - {item['title'][:100]}",
        "---",
        "",
        f"# {item['title']}",
        "",
        f"> [!info] {src} · **{item['cat']}**"
        + (f" · {item['dept']}" if item["dept"] else "")
        + (f" · {date}" if date else ""),
        f"> [원문 보기(라이브)]({item['url']})" if item["url"] else "",
        (f"> [[{short_id(item)}.html|📄 원문 보관본 — 삭제돼도 열림]]"
         if item.get("_snap") else "> _(보관본 없음)_"),
        "",
        "## 질의내용",
        "",
        item["q"] or "_(없음)_",
        "",
        f"## {ans_h}",
        "",
        item["a"] or "_(없음)_",
        "",
        "---",
        f"관련 분류: [[분류 - {item['cat']}]]",
        "",
    ]
    return "\n".join(fm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=str(DEFAULT_VAULT), help="옵시디언 볼트 경로")
    args = ap.parse_args()

    vault = Path(args.vault)
    if not (vault / ".obsidian").exists():
        print(f"경고: {vault} 는 옵시디언 볼트가 아닌 듯(.obsidian 없음). 그래도 진행합니다.")
    root = vault / FOLDER
    notes_dir = root / "노트"
    snap_dir = root / "보관본"
    if root.exists():
        shutil.rmtree(root)  # 재생성(idempotent)
    notes_dir.mkdir(parents=True)
    snap_dir.mkdir(parents=True)

    data = collect()
    # 원문 보관본(gzip 스냅샷)을 바로 열리는 .html로 풀어 볼트에 저장
    n_snap = 0
    for d in data:
        rel = d.get("snapshot", "")
        gz = PROJ / "qa" / rel if rel else None
        if gz and gz.exists():
            html = gzip.open(gz, "rt", encoding="utf-8").read()
            (snap_dir / f"{short_id(d)}.html").write_text(html, "utf-8")
            d["_snap"] = True
            n_snap += 1
    # 노트 파일명 미리 계산(링크 일관성)
    for d in data:
        d["_name"] = safe_name(d)
    # 파일명 충돌 방지
    seen = {}
    for d in data:
        n = d["_name"]
        if n in seen:
            seen[n] += 1
            d["_name"] = f"{n[:-1]}-{seen[n]})"
        else:
            seen[n] = 0

    # 노트 쓰기
    for d in data:
        (notes_dir / f"{d['_name']}.md").write_text(note_body(d, d["_name"]), "utf-8")

    # 분류별 인덱스
    from collections import Counter
    cnt = Counter(d["cat"] for d in data)
    for cat in CATS:
        rows = sorted([d for d in data if d["cat"] == cat],
                      key=lambda x: x["updated"] or x["posted"] or "", reverse=True)
        lines = [f"# 분류 - {cat}", "",
                 f"> {len(rows)}건 · [[{FOLDER}|← 아카이브 홈]]", ""]
        cur = ""
        for d in rows:
            yr = (d["updated"] or d["posted"] or "----")[:4]
            if yr != cur:
                cur = yr
                lines.append(f"\n### {yr}")
            src = "국토부" if d["src"] == "molit" else "신문고"
            lines.append(f"- [[{d['_name']}|{d['title']}]] <small>({src}{' · ' + d['dept'] if d['dept'] else ''})</small>")
        (root / f"분류 - {cat}.md").write_text("\n".join(lines) + "\n", "utf-8")

    # 메인 MOC
    total = len(data)
    n_molit = sum(1 for d in data if d["src"] == "molit")
    moc = [
        f"# {FOLDER}", "",
        "> 국토부 민원마당 · 국민신문고의 **건축** 질의회신 아카이브. "
        "안전/품질/건축 일반으로 분류(LLM)했습니다.", "",
        "## 분류", "",
        f"- [[분류 - 안전]] — **{cnt['안전']}**건",
        f"- [[분류 - 품질]] — **{cnt['품질']}**건",
        f"- [[분류 - 건축 일반]] — **{cnt['건축 일반']}**건 (안전·품질 외 일반 건축 문의)", "",
        f"합계 **{total}**건 (국토부 {n_molit} · 국민신문고 {total - n_molit})", "",
        "## 사용법", "",
        "- 위 분류 노트에서 연도별로 훑어보거나, 옵시디언 검색(⌘⇧F)으로 본문까지 전문 검색.",
        "- 각 노트 상단 속성의 `분류`·`출처`·`담당`으로 필터(속성 검색) 가능.",
        "- 각 노트의 **원문 보관본** 링크(📄)는 볼트 `보관본/`에 저장된 HTML — "
        "국토부/신문고에서 원문이 삭제돼도 그 형태 그대로 열립니다(오프라인 가능).",
        "- `원문(라이브)` 링크는 국토부/신문고 실서버 — 삭제되면 404, 대신 보관본을 보세요.", "",
        f"> 자동 생성: `export_obsidian.py` · 항목 {total}건", "",
    ]
    (root / f"{FOLDER}.md").write_text("\n".join(moc), "utf-8")

    print(f"내보내기 완료 → {root}")
    print(f"  노트 {total}건 (안전 {cnt['안전']} / 품질 {cnt['품질']} / 건축 일반 {cnt['건축 일반']})")
    print(f"  원문 보관본 HTML {n_snap}건 → 보관본/ (원문 삭제돼도 열림)")
    print(f"  인덱스: {FOLDER}.md + 분류 - (안전|품질|건축 일반).md")


if __name__ == "__main__":
    sys.exit(main())
