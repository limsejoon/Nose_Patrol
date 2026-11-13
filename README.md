# 냄새알림 — 주민 카톡 신고 기반 악취 대응 AI Agent

「제주 AI·빅데이터 활용 AI Agent 개발 챌린지」 제출작 · 팀 **애월주민**

주민이 카톡으로 평소 말처럼 냄새를 신고하면 Agent가 같은 마을 신고를 사건으로 묶어 단계(관찰·주의·경보·지속)를 정하고, 농장 주의 알림·시청 대표 민원 전화·민원서 초안을 대신 처리합니다. 센터 방문자는 **💬 Agent에게 묻기**로 신고·처리·실측·악취배출시설 통계를 말로 묻고, Claude가 고른 도구가 계산한 숫자로 근거와 함께 답을 받습니다.

## 문서 (docs/)
| 문서 | 내용 |
|---|---|
| [1_설치_실행_매뉴얼.md](docs/1_설치_실행_매뉴얼.md) | 센터 담당자용 설치·실행, 키 설정, 외부 접속 주소, 데이터 삭제, 오류·제약, 평가용 키 |
| [2_사용자_매뉴얼.md](docs/2_사용자_매뉴얼.md) | 화면별 사용법, 말로 묻기 예시, 5분 시연 순서 |
| [3_데이터_활용_명세.md](docs/3_데이터_활용_명세.md) | 필수 데이터(악취배출시설현황)·함께 쓰는 데이터의 출처·이용조건·전처리·분석 흐름, 외부 API, 오픈소스 |
| [4_결과_설명자료.md](docs/4_결과_설명자료.md) | 문제 정의, Agent 구조, 기능·실행 결과, 검증, 한계, 센터 활용 방안 |
| [6_질문_평가_결과.md](docs/6_질문_평가_결과.md) | 말로 묻는 분석 질문 15개 자동 채점 결과와 답 원문 |
| [5_AI_활용_명세.md](docs/5_AI_활용_명세.md) | 사용 모델(분석 Claude Sonnet 5.5, 신고 해석 Claude Haiku 5.5), 프롬프트 위치, AI 활용 범위, 개발에 쓴 AI 도구 |
| 냄새알림_기획서.html | 기획서 원본(15쪽). PDF는 `scripts/make_submission.py` 로 만듦 |

## 실행 (Windows)
1. Python 3.12 이상 설치 (설치할 때 "Add python.exe to PATH" 체크)
2. 이 폴더에서 `run.bat` 더블클릭 → 브라우저가 `http://127.0.0.1:8000` 을 엽니다
3. Claude를 쓰려면 `.env` 에 `ANTHROPIC_API_KEY` 를 넣고 다시 실행 (모델 기본값: 분석 `claude-sonnet-5-5`, 신고 해석 `claude-haiku-5-5`). 키가 없으면 신고 해석은 규칙 기반으로 동작하고, 말로 묻는 분석만 꺼집니다

VS Code에서는 터미널에 아래를 입력해도 됩니다.
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

## 화면
| 주소 | 내용 |
|---|---|
| `/index.html` | 센터 화면: 지도(배경 회색·지도·위성, 리·동 경계, 마을 신고 단계, 악취배출시설, 실측 대상 농장), 마을별 단계, 최근 신고 현황(24시간·이번 달·3개월), Agent 행동 기록. 마을을 누르면 요약과 [이 마을 통계 보기] |
| `/stats.html` | 💬 Agent에게 묻기(말로 묻는 분석) + 신고·처리 통계: 마을 × 시간대 신고 수, 날짜별 신고, 사건 단계, 마을별 처리 합계, 사건별 처리 경과 |
| `/chat.html` | 주민 카톡 시뮬레이터 (대회판. 현장판은 카카오 챗봇 연결) |
| `/farm.html` | 농장주 알림 화면 시뮬레이터 |

## 시연 순서
1. 센터 화면에서 **▶ 시연: 아침 신고 12건** → 광령2리가 주의 → 경보로 올라가고, 농장 알림과 대표 민원 전화(🔊 듣기)가 기록됨
2. 농장주 화면에서 [저감시설 가동함] → 센터 행동 기록에 농장 응답
3. **⏩ 3시간 뒤** → **▶ 3시간 뒤 신고** → 지속 단계, 민원서 초안 → [마을 대표 승인]
4. 주민 카톡 화면에서 직접 "냄새 심하다" → 동네 1회 등록 흐름 확인
5. **📊 통계** → [가상 한 달 기록 불러오기] → 마을·시간대별 신고와 처리 경과 확인 (기존 기록은 지워짐. 불러온 뒤 1~3을 다시 하면 오늘 기록이 더해짐)

## 구조
```
backend/
  main.py              API·화면 서버
  config.py            설정 (.env)
  data.py              CSV 읽기
  agent/engine.py      판단 엔진: 해석 → 사건 묶기 → 단계 → 행동
  agent/llm.py         Claude 호출 (공식 anthropic SDK, 실패 시 None → 규칙 기반)
  agent/analyst.py     말로 묻는 분석 Agent(F4): 프롬프트, 도구 8개, 도구 호출 루프
  tools/parse_report.py  자연어 신고 해석 (Claude 구조화된 출력 → 실패 시 규칙)
  tools/geo.py         지명 좌표, 풍향, 주의 알림 보낼 바람 위쪽 농장 고르기(내부용)
  tools/history.py     실측 이력·통계
  tools/drafts.py      민원 전화 문안, 문자, 농장 알림, 민원서
  tools/report_stats.py  지역·시간별 신고·처리 통계
  tools/sim_history.py   가상 신고 기록(시연용, 시드 고정)
  fallback/rule_parser.py  규칙 기반 해석기 (LLM 막힐 때)
frontend/              index.html, stats.html, chat.html, farm.html
scripts/prepare_facilities.py  필수 데이터 전처리: 주소 → 좌표, 중복 의심 표시
scripts/prepare_boundaries.py  광령리 주변 리·동 경계 (OpenStreetMap → data/processed/boundaries.geojson)
scripts/check.py               자동 점검 27개 (시나리오·원칙·재현성·원자료 검산값, 키 없이 실행)
scripts/eval_questions.py      말로 묻는 분석 질문 15개 평가 (키 필요, 약 500원)
scripts/prepare_admin_records.py  정보공개청구 PDF 4개 → data/processed/admin_*.csv (날짜·시각·분류만)
scripts/make_submission.py     제출물 만들기 (기획서 PDF + 최종 결과물 ZIP → dist/)
frontend/vendor/leaflet/       지도 라이브러리 Leaflet 1.9.4 (인터넷 없이 동작)
data/raw/              실측 CSV(실제), 악취배출시설현황(실제), farms(3곳 실제 위치·1곳 미확인), villages(리사무소 좌표, 인구 임시값)
data/processed/        facilities.csv(전처리 결과), geocode_cache.json, boundaries.geojson, tiles/(브이월드 배경지도 저장, 제출물 제외)
data/demo/             시연 시나리오
```

## 점검과 제출물
```
.venv\Scripts\python scripts\check.py            # 자동 점검 (27/27 통과해야 함)
.venv\Scripts\python scripts\make_submission.py  # dist/ 에 기획서 PDF와 최종 결과물 ZIP
```
평가용 Claude 키를 ZIP에 넣으려면 프로젝트 폴더에 `평가용_키.txt` (한 줄: `sk-ant-...`)를 만든 뒤 `make_submission.py` 를 실행합니다. 이 파일과 `dist/` 는 git에 올라가지 않습니다.

## 향후 계획 (현장판)
- 카카오톡 채널 연결, 실제 전화·문자 발송
- 기상청 풍향 API 연결 (지금은 기본값)
- 센터 CSV(유동인구 등)를 넣어 함께 분석, 분석 보고서 내보내기(10 미만 값 가림)
- 센서 연계는 후속 계획입니다. 입지 리스크 점수·농가별 성적표·독자 확산 예측은 이번 제출 범위에서 제외합니다.
- 주의 알림 대상에 악취배출시설 목록도 사용, 마을 인구 실제값

## 원칙
- 숫자는 도구가 계산하고 LLM은 숫자를 만들지 않는다
- 특정 농장을 원인으로 단정하거나 추정해서 보여 주지 않는다
- 원인 농장은 추정해서 보여 주지 않는다 (명예훼손 위험). 센터 화면·통계·전화 문안·문자·민원서에는 신고 집계와 처리 사실만 쓴다 (풍향도 표시하지 않음)
- 풍향 계산은 주의 알림을 보낼 바람 위쪽 농장을 고르는 데만 내부적으로 쓰고, 화면·문안에 표시하지 않는다
- 농장에는 마을·집계 인원·점검 요청만 보냅니다. 분석 LLM에는 질문·집계, 신고 해석 LLM에는 신고 문장을 전송합니다. 별도 ID·연락처 필드는 전송하지 않지만 자유문장 속 개인정보 마스킹은 현장 운영 전 보완해야 합니다.
- 대회판은 실제 전화·문자·민원 제출을 하지 않고 기록만 남긴다

## 지도
- 배경지도: 브이월드(회색·지도·위성). `.env` 의 `VWORLD_API_KEY` 가 있으면 서버가 타일을 대신 받아 PC에 저장하고(`/tiles/...`), 키는 화면에 드러나지 않습니다. 키가 없으면 OpenStreetMap.
- 리·동 경계: OpenStreetMap 행정경계(광령리 진하게). `python scripts/prepare_boundaries.py` 로 다시 만듭니다.
- 주소로 바로 열기: `/index.html?village=광령2리` (그 마을로 이동), `/index.html?view=all` (제주 전체 시설), `/stats.html?village=광령2리`
- 3D 지도는 넣지 않았습니다(시연 PC에서 화면이 뜨지 않음). 참고한 jeju-map-demo 에서는 경계 처리 방식, 멀리서 이름표 숨기기, 주소로 상태 공유를 가져왔습니다.

## 말로 묻는 분석 (Claude Agent)
- 화면: 통계 화면 맨 위 **💬 Agent에게 묻기** (센터 화면 위쪽 [📊 통계 · Agent에게 묻기] 버튼으로 이동)
- 모델: `claude-sonnet-5-5` (`.env` 의 `LLM_MODEL` 로 변경). 질문 1건에 도구 1~2번, 평균 약 4초, 비용 약 30원(입력 1만·출력 4백 토큰 안팎). 신고 해석은 `claude-haiku-5-5` (`LLM_PARSE_MODEL`)
- 도구 8개 (숫자는 모두 도구가 계산, Claude는 도구 선택과 설명만):
  | 도구 | 하는 일 | 데이터 |
  |---|---|---|
  | `complaint_history` | 실제 민원 1,778건의 연·월·접수 시간대·요일·접수방법별 건수, 처리 종류 | 제주시 정보공개청구 (실제) |
  | `coverage_compare` | 민원 접수 시각·날짜 × 정기 실측 시간표·측정일 (시간표 밖 비율, 겹친 날, 측정 없던 달·요일) | 정보공개청구 × 악취조사 DB (실제) |
  | `inspection_history` | 지도점검 종류별(현장확인·포집 시도·포집·분석 의뢰 등), 행정처분 사례(이름 없음), 액비살포 | 제주시 정보공개청구 (실제) |
  | `measurement_stats` | 연도·시간대별 기준(희석배수 10) 초과 건수·비율, 참고용 15 초과 (농장 합산, 이름 없음) | 악취조사 DB (실제) |
  | `facility_stats` | 전체 합계와 읍면·리·구분별 시설 수·부지면적 (이름 없음) | 제주데이터허브 악취배출시설현황 (지정) |
  | `report_stats` | 기간·마을·시간대별 신고·처리 집계 | 냄새알림 신고 (시연용 가상) |
  | `hourly_daily` | 접수 시간대별·날짜별 신고, 가장 몰린 때 | 냄새알림 신고 (시연용 가상) |
  | `incident_list` | 사건별 처리 경과와 걸린 시간 | 냄새알림 신고 (시연용 가상) |
- 도구 결과에는 자료 종류(실제/지정/가상), 출처, 기간, 분모, 계산 정의, 이 자료로 알 수 없는 것(cannot_tell)이 함께 들어가 Claude가 범위를 틀리지 않게 합니다
- 질문 평가: `scripts/eval_questions.py` (질문 15개, 기대 도구·정답 값·금지 표현 자동 채점) → [docs/6_질문_평가_결과.md](docs/6_질문_평가_결과.md) **15/15**
- 답 아래 **Agent가 한 일**을 펼치면 어떤 도구를 어떤 조건으로 불렀고 무엇을 받았는지 그대로 보입니다
- Claude에 보내는 것: 질문 문장, 도구가 계산한 집계값. 별도 신고자 ID·연락처 필드와 행정 원문 행은 보내지 않습니다. 신고 해석의 자유문장 전송은 별개이며 개인정보 마스킹은 현장 운영 전 보완합니다
- 시연 버튼(아침 신고 12건 등)은 빠르게 돌도록 규칙으로 해석하고, 주민 카톡 화면에 직접 쓴 문장만 Claude로 해석합니다


## 기획서 15쪽 수정본 및 PDF 빌드

주민 화면 6쪽, 농장주 알림 8쪽, 행정 담당자 검토 화면 9쪽으로 구성했습니다. 실제 분석 응답과 전체 수정 내역은 `docs/7_기획서_수정_및_시연명세.md`와 `docs/evidence/analysis_run_2026-11-11.json`을 참고하세요.

PDF를 다시 만들려면 선택적 문서 의존성 `pip install -r requirements-build.txt` 설치 후 `python scripts/render_proposal_pdf.py`를 실행합니다. `make_submission.py`도 해당 의존성이 있으면 같은 렌더러를 사용합니다. Agent 실행에는 문서 빌드 패키지가 필요하지 않습니다.
