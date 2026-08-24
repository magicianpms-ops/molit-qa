#!/bin/bash
# 정기 자동 갱신: 신규 항목만 추가(기존은 상세요청 없이 스킵) → 분류 → 페이지·볼트 재생성.
# launchd(com.molitqa.weekly)가 매주 월요일 04:00에 실행.
set -euo pipefail
cd "$(dirname "$0")"
PY=/opt/homebrew/bin/python3
STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p logs
export PYTHONUNBUFFERED=1
echo "[$STAMP] update start" >> "logs/update.log"
# 소스① 국토부 민원마당(건축 전건) 신규만
"$PY" scrape_molit.py --all --new-only --delay 1.0 >> "logs/update.log" 2>&1
# 소스② 국민신문고(건축 키워드) 신규만
"$PY" scrape_epeople.py --pages 5 --new-only --delay 0.8 >> "logs/update.log" 2>&1
# 신규 항목만 LLM 분류(캐시된 건 건너뜀) → 열람 페이지 + 옵시디언 노트·보관본 재생성
"$PY" classify_llm.py --batch 25 >> "logs/update.log" 2>&1
"$PY" build_browse.py >> "logs/update.log" 2>&1
"$PY" export_obsidian.py >> "logs/update.log" 2>&1
echo "[$STAMP] update done" >> "logs/update.log"
