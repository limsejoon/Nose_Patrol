"""냄새알림 자동 점검 (재현성 확인용). Claude API 키 없이도 돌아간다.

실행: .venv\\Scripts\\python scripts\\check.py
하는 일: 시연 시나리오를 처음부터 돌려 단계·행동·통계가 규칙대로 나오는지, 원칙(농장 이름·풍향 비표시)을
지키는지 확인하고 결과를 표로 출력한다. 하나라도 틀리면 종료 코드 1.
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config, data  # noqa: E402
from backend.agent import analyst, engine  # noqa: E402
from backend.fallback import rule_parser  # noqa: E402
from backend.tools import admin_records, history, report_stats, sim_history  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def play(name):
    steps = json.loads((config.DATA_DEMO / f"{name}.json").read_text(encoding="utf-8"))
    engine.S.rule_only = True
    out = []
    try:
        for s in steps:
            if s.get("advance_min"):
                engine.S.clock_offset += timedelta(minutes=s["advance_min"])
                continue
            out.append(engine.handle_message(s["user"], s["text"], s.get("place_village"), source="demo_script")["reply"])
    finally:
        engine.S.rule_only = False
    return out


S = engine.S
S.reset()

# 1. 아침 신고 12건 → 경보, 대표 전화 1통, 농장 알림
replies = play("gwangryeong_morning")
st = {v["village"]: v for v in engine.snapshot()["villages"]}
types = [a["type"] for a in S.actions]
check("아침 신고 12건 → 광령2리 경보(2)", st["광령2리"]["stage"] == 2, f"단계 {st['광령2리']['stage']}")
check("대표 민원 전화 1통 + 문자 1통", types.count("city_call") == 1 and types.count("sms") == 1, str(types))
check("농장 주의 알림 대상 3곳(위치 확인된 바람 위쪽 농장)", sum(len(v) for v in S.farm_inbox.values()) == 3,
      str({k: len(v) for k, v in S.farm_inbox.items()}))

# 2. 3시간 뒤 신고 → 지속, 민원서 1건(승인 대기)
S.clock_offset += timedelta(minutes=180)
replies += play("gwangryeong_3h_later")
st = {v["village"]: v for v in engine.snapshot()["villages"]}
comps = [a for a in S.actions if a["type"] == "complaint"]
check("3시간 뒤 신고 → 지속(3)", st["광령2리"]["stage"] == 3, f"단계 {st['광령2리']['stage']}")
check("민원서 1건, 마을 대표 승인 대기", len(comps) == 1 and "대기" in comps[0]["status"])
types = [a["type"] for a in S.actions]          # 3시간 뒤 신고까지 반영해 다시 센다
check("같은 사건에 대표 전화 3시간 안에 다시 안 걸기", types.count("city_call") <= 2 and
      all(abs((engine.datetime.fromisoformat(x["ts"]) - engine.datetime.fromisoformat(y["ts"])).total_seconds()) >= 3 * 3600
          for i, x in enumerate([a for a in S.actions if a["type"] == "city_call"])
          for y in [a for a in S.actions if a["type"] == "city_call"][i + 1:]), str(types.count("city_call")) + "통")
sr = report_stats.build(S, 1)
check("시연 신고는 가상으로 표시(simulated, 출처)", sr["simulated"] and "시연 대본" in sr["sources"], str(sr["sources"]))
sent = [r for r in replies if "전화" in r or "민원서" in r]
check("주민 답장: 전화·민원서는 '실제 발신·제출 안 함' 표시", len(sent) >= 2 and all("실제" in r and "안 함" in r for r in sent),
      f"해당 답장 {len(sent)}개")

# 3. 원칙: 문안·기록에 농장 이름·풍향 없음
farm_names = [f["name"] for f in data.farms()] + ["피그랜드"]
blob = json.dumps([a["payload"] for a in S.actions], ensure_ascii=False)
check("전화·문자·민원서·알림에 농장 이름 없음", not any(n in blob for n in farm_names))
check("전화·문자·민원서·알림에 풍향 없음", not any(w in blob for w in ["남풍", "북서풍", "m/s", "미터입니다"]))

# 3-1. 같은 사람이 여러 번 보내면 평균 강도에 한 번만 (가장 최근 값)
S.reset()
for t in ["냄새 아주 심해요 숨을 못 쉬겠어"] * 3:
    engine.handle_message("u_a", t, "광령1리")
engine.handle_message("u_b", "냄새 조금 나요", "광령1리")
vs = engine.village_status("광령1리")
lat = {}
for r in S.reports:
    lat[r["user"]] = r["intensity"]
check("평균 강도는 사람별 최근 값으로 (반복 신고 1번만)", vs["avg"] == round(sum(lat.values()) / len(lat), 1) and vs["n"] == 2,
      f"평균 {vs['avg']}, {vs['n']}명, 신고 {vs['reports_window']}건")
S.reset()

# 3-2. 처음 신고 → 동네 묻기 → 동네만 답함: 먼저 보낸 신고(강도 포함)가 접수돼야 한다
S.reset(); S.rule_only = True
engine.handle_message("u_new", "냄새 심하다")
engine.handle_message("u_new", "광령 3리요")
S.rule_only = False
got = [(r["village"], r["intensity"], r["text"]) for r in S.reports]
check("동네만 답하면 먼저 보낸 신고를 접수 (강도 유지)", got == [("광령3리", 4, "냄새 심하다")], str(got))
S.reset()

# 4. 규칙 해석기
cases = {"3시간째 계속 냄새 심함": "지금", "아침 7시부터 냄새 엄청 나네": "07시", "밤 11시 냄새": "23시"}
for text, want in cases.items():
    got = rule_parser.time_expr(text)
    check(f"시각 해석: '{text}' → {want}", got == want, f"결과 {got}")

# 5. 가상 한 달 기록 재현성(시드 고정)
S.reset()
a = sim_history.generate(S, engine.handle_message, engine.farm_respond, engine.approve_complaint)
S.reset()
b = sim_history.generate(S, engine.handle_message, engine.farm_respond, engine.approve_complaint)
check("가상 한 달 기록: 두 번 만들어도 같음", (a["reports"], a["incidents"]) == (b["reports"], b["incidents"]),
      f"신고 {a['reports']}건, 사건 {a['incidents']}건")
s30 = report_stats.build(S, 30)
check("가상 기록: 신고 없는 날 40~70%", 0.4 <= s30["kpi"]["quiet_days"] / s30["kpi"]["days_total"] <= 0.7,
      f"{s30['kpi']['quiet_days']}/{s30['kpi']['days_total']}일")

# 6. 말로 묻는 분석 도구 (Claude 없이 도구만 직접 호출해 숫자 대조)
t = analyst.t_report_stats(S, "30d", None, None, None)
check("report_stats 도구 = 통계 화면 집계", t["reports"] == s30["kpi"]["reports"], f"{t['reports']} = {s30['kpi']['reports']}")
f = analyst.t_facility_stats(S, "읍면", None)
check("facility_stats: 58행 합계·관리지역 46 (전체와 그룹 구분)", f["all_facilities"] == 58 and f["all_in_odor_control_area"] == 46
      and sum(g["facilities"] for g in f["groups"]) == 58)
biz_names = {x["사업장명"] for x in data.facilities()}
check("facility_stats: 사업장명 58곳 중 하나도 미포함", not any(n in json.dumps(f, ensure_ascii=False) for n in biz_names))
m = analyst.t_measurement_stats(S, None, None)
check("measurement_stats: 391건, 농장 이름 없음", m["all"]["n"] == 391 and not any(n in json.dumps(m, ensure_ascii=False) for n in farm_names))
ov = history.overview()
check("실측 기준 10 초과: 2023 15/64, 2024 16/64, 2026 6/23", (ov["by_year"]["2023"]["over10"], ov["by_year"]["2024"]["over10"],
      ov["by_year"]["2026"]["over10"], ov["by_year"]["2026"]["n"]) == (15, 16, 6, 23))

# 7. 실제 행정 기록(정보공개청구) — 정규화 결과가 원문 검산과 같은지
if data.admin_complaints():
    c = admin_records.complaint_history()
    check("민원 1,778건 · 접수시각 있는 1,761건 · 민원 있는 날 652일",
          (c["complaints"], c["complaints_with_time"], c["days_with_complaints"]) == (1778, 1761, 652),
          f"{c['complaints']}, {c['complaints_with_time']}, {c['days_with_complaints']}")
    cc, cy = admin_records.coverage_compare(timetable="current"), admin_records.coverage_compare(timetable="by_year")
    check("정기 실측 시간 밖 접수: 지금 시간표 1,194(67.8%) / 해마다 시간표 957(54.3%)",
          (cc["outside_measurement_hours"], cc["outside_pct"], cy["outside_measurement_hours"], cy["outside_pct"]) == (1194, 67.8, 957, 54.3))
    check("민원일과 정기 측정일이 겹친 날 9일", cc["overlap_days"] == 9, ", ".join(cc["overlap_dates"]))
    ins = admin_records.inspection_history()
    check("지도점검 673행·210일, 포집·분석 의뢰 25행·13일, 처분 4사례(2023년 이후 1)",
          (ins["inspection_rows"], ins["inspection_days"], ins["by_kind"]["포집·분석 의뢰"]["rows"], ins["by_kind"]["포집·분석 의뢰"]["days"],
           ins["administrative_actions"]["cases_in_document"], ins["administrative_actions"]["cases_in_requested_period_2023_2026"])
          == (673, 210, 25, 13, 4, 1))
    blob2 = json.dumps([c, ins, cc], ensure_ascii=False)
    check("행정 기록 도구에 농장·사업장 이름 없음", not any(n in blob2 for n in farm_names + ["성신", "백록"]))
else:
    check("행정 기록 CSV 있음 (data/processed/admin_*.csv)", False, "scripts/prepare_admin_records.py 로 만드세요")

S.reset()
w = max(len(r[0]) for r in results)
fails = 0
for name, ok, detail in results:
    fails += not ok
    print(f"{'✅' if ok else '❌'} {name.ljust(w)}  {detail}")
print(f"\n{len(results) - fails}/{len(results)} 통과")
sys.exit(1 if fails else 0)
