# 냄새알림 — 주민 카톡 신고 기반 악취 대응 AI Agent

제주 AI·빅데이터 활용 AI Agent 개발 챌린지 제출용 (대회판 뼈대).

## 실행 (Windows)
1. Python 3.11 설치 (설치할 때 "Add python.exe to PATH" 체크)
2. 이 폴더에서 `run.bat` 더블클릭 → 브라우저가 `http://127.0.0.1:8000` 을 엽니다
3. LLM을 쓰려면 `.env` 에 `LLM_PROVIDER` 와 API 키를 넣고 다시 실행 (안 넣어도 규칙 기반으로 동작)

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
| `/index.html` | 센터 화면: 지도(마을 신고 단계 · 악취배출시설 · 실측 대상 농장), 마을별 단계, Agent 행동 기록, 실측 통계 |
| `/stats.html` | 신고·처리 통계: 마을 × 시간대 신고 수, 날짜별 신고, 사건 단계, 마을별 처리 합계, 사건별 처리 경과 |
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
  agent/llm.py         외부 LLM 호출 (실패 시 None)
  tools/parse_report.py  자연어 신고 해석 (LLM → 실패 시 규칙)
  tools/geo.py         지명 좌표, 풍향, 주의 알림 보낼 바람 위쪽 농장 고르기(내부용)
  tools/history.py     실측 이력·통계
  tools/drafts.py      민원 전화 문안, 문자, 농장 알림, 민원서
  tools/report_stats.py  지역·시간별 신고·처리 통계
  tools/sim_history.py   가상 신고 기록(시연용, 시드 고정)
  fallback/rule_parser.py  규칙 기반 해석기 (LLM 막힐 때)
frontend/              index.html, stats.html, chat.html, farm.html
scripts/prepare_facilities.py  필수 데이터 전처리: 주소 → 좌표, 중복 의심 표시
data/raw/              실측 CSV(실제), 악취배출시설현황(실제), farms(3곳 실제 위치·1곳 미확인), villages(리사무소 좌표, 인구 임시값)
data/processed/        facilities.csv(전처리 결과), geocode_cache.json
data/demo/             시연 시나리오
```

## 남은 일 (TODO)
- [x] 「악취배출시설현황」 58곳을 `data/raw/` 에 넣고 지도에 표시 (리 단위로 묶음)
- [ ] 브이월드 키(`VWORLD_API_KEY`)로 지번 좌표 받기 → 지금은 리 중심 근사값
- [ ] 주의 알림 대상 고르기(`rank_sources`)에 악취배출시설 목록도 쓰기 (지금은 광령리 실측 농장 4곳만)
- [ ] 농장·마을 좌표를 실제 주소 지오코딩 값으로 교체
- [ ] 기상청 API 연결(`tools/geo.py get_wind`) + 오프라인용 `data/raw/wind.csv`
- [ ] 말로 묻는 통계(F4): 질문 → 집계 (LLM + history 도구)
- [ ] 입지 리스크 보고서 PDF(F8), 농장 성적표(F9) 화면
- [ ] 유동인구 가상 CSV로 인구 보정
- [ ] 허위·중복 필터(F5)
- [ ] 설치 매뉴얼·데이터 명세서(`docs/`)

## 원칙
- 숫자는 도구가 계산하고 LLM은 숫자를 만들지 않는다
- 특정 농장을 원인으로 단정하거나 추정해서 보여 주지 않는다
- 원인 농장은 추정해서 보여 주지 않는다 (명예훼손 위험). 센터 화면·통계·전화 문안·문자·민원서에는 신고 집계와 바람 정보, 처리 사실만 쓴다
- 풍향 계산은 주의 알림을 보낼 바람 위쪽 농장을 고르는 데만 내부적으로 쓰고, 화면·문안에 표시하지 않는다
- 신고자 정보는 농장에 보내지 않는다, LLM에는 신고 문장만 보낸다
- 대회판은 실제 전화·문자·민원 제출을 하지 않고 기록만 남긴다
