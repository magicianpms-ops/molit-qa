# PROGRESS

## 2026-08-07 — MVP(소스① 국토부 민원마당) 구축·검증 완료
- 스크래퍼 `scrape_molit.py`, 검색 `search.py` 작성 (stdlib만, 의존성 0).
- **실증 근거**:
  - 건축 카테고리 = `category=2102`, 목록 GET `faqList.do?category=2102&pageIndex=N`,
    총 106페이지 ≈ 1,060건 감지.
  - 상세 = **POST** `faqContents.do` + `faqId=ID` (세션 쿠키 필요).
    GET·tbody는 비어 옴 → POST여야 table_view가 채워짐 [핵심 함정].
  - 2페이지(20건) 시범 수집 → 20 MD 생성, 8건 안전·품질 태깅.
  - 용량: 건당 ~4KB, 전건 추정 ~4MB (이미지 대비 수백 배 절감).
  - 검색 CLI로 `--sq`, `--tag`, 키워드+미리보기 정상 동작 확인.
- **알려진 한계**: 키워드 태깅 오탐 존재(예: '가설건축물'의 '가설'이 안전으로 매칭).
  → 추후 LLM 재분류 또는 문맥 키워드로 보정.

## 2026-08-07 (추가) — 전건 크롤 + 월간 자동화
- `--new-only` 모드 추가: 색인에 있는 faq_id는 상세 POST 없이 스킵(월간 갱신 효율).
- 페이지마다 `save_index` — 중단돼도 진행분 보존.
- **전건 크롤 실행 중**(`--all --delay 1.0`, 백그라운드, ≈18분).
- **월간 자동 갱신 launchd 등록**: `com.molitqa.monthly`, 매월 1일 04:00,
  `update_monthly.sh` → `--all --new-only`. plist=`~/Library/LaunchAgents/`.

## 2026-08-08 — 전건 크롤 완료 + 원문 증빙 스냅샷
- 건축 전건 **1,060건** 수집 완료. 안전·품질 **336건**(안전253/품질117), 4.2MB.
- 브라우저 열람·검색 페이지 `qa/browse.html` + 아티팩트 게시.
- **link rot 대비**: 사용자 지적("원문이 삭제될 수 있다")→ 경량 HTML 스냅샷 도입.
  `make_snapshot`이 상세 table_view를 self-contained HTML로 gzip 보관
  (`qa/snapshots/<id>.html.gz`, 건당 ~4KB). frontmatter `snapshot`,`captured`.
  최초 캡처일 유지(재실행해도 덮어쓰지 않음). 전건 백필 실행 중.

## 2026-08-08 (추가) — 소스② 국민신문고 어댑터
- `scrape_epeople.py`: 건축 카테고리가 없어 **키워드 검색** 기반.
- 세션: GET로 `_csrf`+쿠키 확보. 상세는 **2단계** — crtfAjax 인증(X-CSRF-TOKEN 헤더)
  → smlrCaseDetail POST. id=`epUnionSn`(compound), 유형 dutySctnNm(taol/tqapttn).
- 본문은 `.samBox`(질의/답변)에서 추출. 소스①의 classify·norm_date 등 재사용.
- 검증: 기본 키워드 11개×3p → 85건(안전·품질 84), 답변 401~2527자 전문, 스냅샷 무결.
- `search.py`를 **두 소스 통합 검색**으로 확장(--src 옵션).

## 다음
- [ ] 소스② 키워드 세트 확대 + 대량 수집(현재 85건 샘플).
- [ ] browse.html(아티팩트)에 소스② 병합.
- [ ] 소스③ 세움터(로그인).
- [ ] 소스③ 세움터 로그인·전문질의 어댑터.
- [ ] lh 통합(standards/*.md 방식 임포트).
