# molit-qa — 국토부 질의회신 건축 안전·품질 라이브러리

국토부 계열 질의회신을 건축 안전·품질 중심으로 스크랩해 **경량 MD**로 저장한다.
원본 이미지 대신 텍스트만 남겨 용량을 최소화하고(건당 ~4KB), 언제든 검색·조회한다.

## 사용법 (의존성 없음, Python 3.10+)

```bash
# 수집 (소스①: 국토부 민원마당 건축 FAQ)
python3 scrape_molit.py --pages 3          # 앞 3페이지(30건) 테스트
python3 scrape_molit.py --all              # 건축 전건(≈1,060건)
python3 scrape_molit.py --all --new-only   # 신규 faq_id만 추가(기존은 상세요청도 스킵) — 정기 갱신용
python3 scrape_molit.py --all --sq-only    # 안전·품질 관련만 파일 저장
python3 scrape_molit.py --all --delay 1.0  # 서버 예의를 위해 지연 늘림

# 수집 (소스②: 국민신문고 — 키워드 검색 기반)
python3 scrape_epeople.py --pages 3                       # 기본 건축 키워드 세트
python3 scrape_epeople.py --keywords "방화구획" "내진 건축물" # 키워드 지정
python3 scrape_epeople.py --pages 3 --new-only            # 신규만(월간 갱신)

# 검색 (두 소스 통합)
python3 search.py 방화                       # 제목+본문 검색
python3 search.py 감리 --src epeople          # 국민신문고만
python3 search.py 자재 --tag 품질 --preview   # 품질 태그 + 회신 미리보기
python3 search.py --sq -n 30                 # 안전·품질 관련 상위 30건
```

## 저장 구조
```
qa/
  molit/<faq_id>.md         # YAML frontmatter + 질의/회신 본문
  snapshots/<faq_id>.html.gz # 원문 증빙 스냅샷(gzip, 건당 ~4KB)
  index.json                # 경량 색인 (검색용: 제목·태그·일자·부서·hash)
  browse.html               # 브라우저 검색·열람 페이지(self-contained)
```

## 원문 증빙 스냅샷 (link rot 대비)
정부 게시판은 개편·이관으로 원문이 삭제될 수 있다. 본문 텍스트는 MD에 이미
전량 보존되지만, **"국토부가 그날 이렇게 회신했다"는 증빙**을 위해 각 상세페이지의
질의/회신 원문 골격을 self-contained HTML로 떠서 gzip 보관한다.
- 스크랩 시 자동 생성(`--no-snapshot`으로 끔). 최초 캡처일(`captured`) 유지.
- MD frontmatter의 `snapshot`, `captured` 필드로 연결.
- 열기: `gzcat qa/snapshots/51880.html.gz > /tmp/s.html && open /tmp/s.html`

각 MD frontmatter: `source, faq_id, category, title, agency, dept, posted,
updated, tags[안전|품질], sq_relevant, matched_kw, laws, url, hash, scraped_at`.

- **증분 갱신**: 재실행 시 `hash`가 같으면 스킵, 내용이 바뀐 회신만 갱신.
- **원본 대조**: 각 MD의 `url`로 국토부 원문 확인 가능.

## 옵시디언 내보내기
```bash
python3 export_obsidian.py                       # 기본 볼트(~/Documents/Obsidian Vault)
python3 export_obsidian.py --vault "/경로/볼트"    # 볼트 지정
```
볼트의 `질의회신 아카이브/` 폴더에 항목별 노트(속성: 분류/출처/담당/일자/원문) +
분류별 인덱스 3개(안전/품질/건축 일반) + 홈 MOC를 생성한다. 재실행 시 폴더를 새로 쓴다.
분류는 LLM 결과(`qa/llm_cat.json`)를 반영.

## 정기 자동 갱신 (launchd)
**매주 월요일 04:00**에 `run_update.sh`가 실행: 신규만 수집 → LLM 분류(신규만) →
검색 페이지 + 옵시디언 노트·보관본 재생성. (Mac이 켜져 있을 때. 잠자기·꺼짐 시 다음 실행)
- 등록: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.molitqa.weekly.plist`
- 해제: `launchctl bootout gui/$(id -u)/com.molitqa.weekly`
- 즉시 1회 실행(테스트): `launchctl kickstart -k gui/$(id -u)/com.molitqa.weekly`
- 로그: `logs/update.log`
- 스케줄 변경: plist의 `Weekday`(0=일,1=월…6=토)·`Hour`·`Minute` 수정 후 bootout→bootstrap

## 소스
- ① 국토부 민원마당 `eminwon.molit.go.kr` 건축 FAQ — 구현 완료(전건 1,060)
- ② 국민신문고 `epeople.go.kr` — 구현 완료(키워드 검색·CSRF 2단계 POST)
- ③ 세움터 `eais.go.kr` 건축법 전문질의(로그인) — 예정

소스②는 '건축' 카테고리가 없어 **키워드 검색**으로 필터하며(`scrape_epeople.py`의
`DEFAULT_KEYWORDS`), 유형은 유권해석/유사사례(taol)·민원질의응답(tqapttn)을 함께 수집한다.
출력은 `qa/epeople/`, 별도 색인 `qa/index_epeople.json`, 스냅샷은 `qa/snapshots/ep_*.gz`.

## lh 통합
검증 후 `qa/molit/*.md`를 lh의 표준규칙 라이브러리(`standards/*.md`)와 동일한
경계로 임포트한다. Python(수집) → MD → Next.js(조회)로 책임을 분리한다.
