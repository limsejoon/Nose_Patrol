"""말로 묻는 분석 Agent (F4).
이용자가 일상 언어로 질문하면 Claude가 아래 도구 중 필요한 것을 골라 부르고, 도구가 계산한 숫자로 답한다.
- LLM은 숫자를 만들지 않는다. 모든 수치는 도구(파이썬 함수)가 계산한 값만 쓴다.
- 원인 농장은 추정하거나 이름을 말하지 않는다. 시설 정보는 이름 없이 집계만 준다.
- 화면에 "Agent가 한 일"(어떤 도구를 어떤 조건으로 불렀고 무엇을 받았는지)을 그대로 보여 준다.
"""
import json
import time
from collections import defaultdict
from datetime import datetime

import anthropic

from backend import config, data
from backend.agent import llm
from backend.tools import admin_records, history, report_stats

MAX_STEPS = 6

SYSTEM = """너는 '냄새알림'의 분석 도우미다. 제주빅데이터센터 담당자나 방문자가 애월읍 광령리 악취에 대해 묻는 질문에 도구로 답한다.

자료는 네 종류다. 답에 어느 자료인지 항상 밝힌다.
- 실제 행정 기록: 제주시 정보공개청구 민원 접수 1,778건(2023.1~2026.9), 지도점검·행정처분·액비살포 → complaint_history, inspection_history, coverage_compare
- 실제 실측: 제주악취관리센터 악취조사 DB 정기 실측 391건(2020~2026) → measurement_stats
- 지정 데이터: 제주데이터허브 악취배출시설현황 58행(2019.7 기준) → facility_stats
- 시연용 가상 신고: 냄새알림 카톡 신고·사건·처리 기록(대회판은 실제 주민 신고가 아님) → report_stats, hourly_daily, incident_list
"민원", "실제", "2024년"처럼 과거 실제 기록을 물으면 행정 기록 도구를, "신고", "사건", "이번 달·오늘·최근"처럼 냄새알림 화면의 기록을 물으면 시연 신고 도구를 쓴다. 둘을 한 합계로 더하지 않는다.

규칙
1. 숫자는 도구 결과에 있는 값만 쓴다. 직접 더하거나 비율을 계산하지 않는다. 숫자를 쓸 때 그 값이 어느 범위(전체/특정 읍면·마을, 기간)의 값인지 도구 결과의 키 이름으로 확인하고 밝힌다. 그룹 값(예: 한 읍면의 값)을 전체 값처럼 말하지 않는다.
2. 비율을 말할 때는 분모와 건수를 함께 쓴다(예: 1,761건 중 1,194건, 67.8%).
3. 특정 농장을 원인으로 추정하거나 지목하지 않는다. 농장·사업장 이름을 말하지 않는다.
4. 시연용 가상 신고 도구의 결과를 쓰면 답 끝에 "시연용 가상 신고 기준(실제 주민 신고 아님)"이라고 쓴다.
5. 도구 결과의 cannot_tell·note 에 있는 한계 중 답과 관련된 것을 한 줄로 덧붙인다. 접수 시각을 냄새가 난 시각처럼 말하지 않는다.
6. 실측 기준: 광령리는 악취관리지역이라 부지경계 복합악취 배출허용기준이 희석배수 10이다. "기준 초과"는 10 초과를 말하고, 15 초과는 참고 지표로만 쓴다. 정기 실측의 기준 초과는 행정처분과 같은 것이 아니다.
7. 냄새알림의 전화·문자·민원서는 대회판에서 문안 생성·기록만 하고 실제로 보내지 않는다.
8. 답은 한국어로 짧게: 핵심 2~4문장. 비교가 있으면 마크다운 표 하나. 꾸밈말은 쓰지 않는다.
9. 도구로 답할 수 없는 질문이면 할 수 있는 질문 예를 들어 안내한다.

시연 신고 기간 표현: "오늘·최근 하루"=24h, "이번 주·최근 7일"=7d, "이번 달"=month, "최근 30일·한 달"=30d, "3개월·분기"=3m, "전체"=all.
마을: 광령1리, 광령2리, 광령3리. 시간대: 오전=8~11시, 낮=11~14시, 오후=14~17시, 저녁=18~21시, 밤=21~24시, 새벽=0~6시.
단계 번호: 0 관찰 < 1 주의 < 2 경보 < 3 지속. "경보까지 간·경보 이상" = min_stage 2 (지속 포함), "주의 이상" = 1, "지속" = 3.
기간을 말하지 않으면 전체로 보고, 답에 그렇게 밝힌다."""

PERIODS = ["24h", "7d", "month", "30d", "3m", "all"]
VILLAGES = ["광령1리", "광령2리", "광령3리"]
nullable = lambda s: {"anyOf": [s, {"type": "null"}]}

TOOLS = [
    {
        "name": "report_stats",
        "description": "[시연용 가상 신고] 냄새알림 카톡 신고와 Agent 처리 집계. 기간·마을·시간대 조건으로 신고 건수, 신고 주민 수, 사건 수, "
                       "단계별 사건 수, 대표 민원 전화·농장 알림·민원서 수, 첫 신고부터 처리까지 걸린 시간(중앙값), "
                       "신고 없는 날 수, 마을별 합계를 돌려준다. hour_from/hour_to 를 주면 그 시간대 신고 건수도 준다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": PERIODS},
                "village": nullable({"type": "string", "enum": VILLAGES}),
                "hour_from": nullable({"type": "integer", "enum": list(range(0, 24))}),
                "hour_to": nullable({"type": "integer", "enum": list(range(1, 25))}),
            },
            "required": ["period", "village", "hour_from", "hour_to"],
            "additionalProperties": False,
        },
    },
    {
        "name": "hourly_daily",
        "description": "[시연용 가상 신고] 냄새알림 신고가 몰리는 때를 본다(접수 시각 기준). 기간·마을 조건으로 시간대별(0~23시) 신고 건수와 날짜별 신고 건수, "
                       "가장 많은 시간대·날짜를 돌려준다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": PERIODS},
                "village": nullable({"type": "string", "enum": VILLAGES}),
            },
            "required": ["period", "village"],
            "additionalProperties": False,
        },
    },
    {
        "name": "incident_list",
        "description": "[시연용 가상 신고] 사건(같은 마을에서 이어진 신고 묶음)별 처리 기록. 첫 신고 시각, 마을, 신고 수, 최고 단계, "
                       "농장 알림·대표 전화·민원서까지 걸린 분, 결과를 최근 순으로 최대 10건 돌려준다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": PERIODS},
                "village": nullable({"type": "string", "enum": VILLAGES}),
                "min_stage": {"type": "integer", "enum": [0, 1, 2, 3]},
            },
            "required": ["period", "village", "min_stage"],
            "additionalProperties": False,
        },
    },
    {
        "name": "measurement_stats",
        "description": "[실제 실측] 제주악취관리센터 악취조사 DB 정기 실측(광령리 A구역 농장 4곳 부지경계, 2020~2026, 분기 1회). "
                       "연도별·시간대별 측정 건수, 기준(희석배수 10) 초과 건수·비율, 참고용 15 초과, 최대값. "
                       "2025년부터 20~22시 측정이 없어 공통 시간대(오전·오후·18~20시)만 맞춘 연도별 값도 준다. 농장별 값은 주지 않는다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "year_from": nullable({"type": "integer", "enum": list(range(2020, 2027))}),
                "year_to": nullable({"type": "integer", "enum": list(range(2020, 2027))}),
            },
            "required": ["year_from", "year_to"],
            "additionalProperties": False,
        },
    },
    {
        "name": "facility_stats",
        "description": "[지정 데이터] 제주데이터허브 「제주특별자치도_악취배출시설현황」(2019.7.19 기준 58행) 집계. "
                       "전체 합계(all_*)와 읍면·리·구분(악취관리지역 여부)별 그룹 값(groups)을 따로 돌려준다. 사업장명은 주지 않는다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "enum": ["읍면", "리", "구분"]},
                "area_filter": nullable({"type": "string", "description": "읍면이나 리 이름 일부, 예: 애월읍, 한림읍, 고성리"}),
            },
            "required": ["group_by", "area_filter"],
            "additionalProperties": False,
        },
    },
    {
        "name": "complaint_history",
        "description": "[실제 행정 기록] 제주시 정보공개청구 광령리 축산 악취 민원 접수(2023.1.1~2026.9.30, 1,778건). "
                       "연도·월·월별(1~12월)·접수 시간대·요일·접수방법별 건수, 민원 있는 날 수, 하루 평균, 처리내용 종류(방제단·농가 저감 요청 등). "
                       "hour_from/hour_to 로 접수 시간대를 거를 수 있다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "year_from": nullable({"type": "integer", "enum": [2023, 2024, 2025, 2026]}),
                "year_to": nullable({"type": "integer", "enum": [2023, 2024, 2025, 2026]}),
                "group_by": {"type": "string", "enum": ["year", "month", "month_of_year", "hour", "weekday", "method"]},
                "hour_from": nullable({"type": "integer", "enum": list(range(0, 24))}),
                "hour_to": nullable({"type": "integer", "enum": list(range(1, 25))}),
            },
            "required": ["year_from", "year_to", "group_by", "hour_from", "hour_to"],
            "additionalProperties": False,
        },
    },
    {
        "name": "inspection_history",
        "description": "[실제 행정 기록] 제주시 정보공개청구 광령리·고성리 지도점검(673행)·행정처분(4사례)·액비살포(9건). "
                       "점검 종류별(민원 현장확인, 포집 시도, 포집·분석 의뢰, 예정·안내 등) 행 수·날 수, 야간 점검, "
                       "처분 사례 수(문서 전체 / 2023년 이후), 액비살포량을 돌려준다. 사업장 이름은 주지 않는다.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "year_from": nullable({"type": "integer", "enum": [2023, 2024, 2025, 2026]}),
                "year_to": nullable({"type": "integer", "enum": [2023, 2024, 2025, 2026]}),
            },
            "required": ["year_from", "year_to"],
            "additionalProperties": False,
        },
    },
    {
        "name": "coverage_compare",
        "description": "[실제 행정 기록 × 실제 실측] 민원 접수 시각·날짜를 정기 실측 시간표·측정일과 비교한다. "
                       "실측 시간대 밖 접수 비율(분모·건수 포함), 민원일과 측정일이 겹친 날, 측정이 없던 달·요일과 그때 민원 수. "
                       "timetable=current 는 지금 시간표를 모든 해에, by_year 는 해마다 그 해 시간표(2024년까지 20~22시 포함)를 적용.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "year_from": nullable({"type": "integer", "enum": [2023, 2024, 2025, 2026]}),
                "year_to": nullable({"type": "integer", "enum": [2023, 2024, 2025, 2026]}),
                "timetable": {"type": "string", "enum": ["current", "by_year"]},
            },
            "required": ["year_from", "year_to", "timetable"],
            "additionalProperties": False,
        },
    },
]
TOOL_LABEL = {"complaint_history": "실제 민원 접수(정보공개)", "inspection_history": "지도점검·처분(정보공개)",
              "coverage_compare": "민원 × 정기 실측 비교",
              "report_stats": "시연 신고·처리 집계", "hourly_daily": "시연 신고 시간대·날짜별", "incident_list": "시연 사건별 처리 기록",
              "measurement_stats": "실측 통계(악취조사 DB)", "facility_stats": "악취배출시설 집계(데이터허브)"}


# ---------------------------------------------------------------- 도구 구현 (숫자는 모두 여기서 계산)
def _range(S, period, village):
    now = S.now()
    if period == "month":
        return report_stats.build(S, None, village, now.strftime("%Y-%m-01"))
    days = {"24h": 1, "7d": 7, "30d": 30, "3m": 90, "all": None}[period]
    return report_stats.build(S, days, village)


def t_report_stats(S, period, village, hour_from, hour_to):
    s = _range(S, period, village)
    k = s["kpi"]
    out = {"period": period, "from": s["daily"][0]["date"] if s["daily"] else None, "to": s["now"][:10],
           "village": village or "전체", "simulated": s["simulated"], "data_kind": "시연용 가상 신고",
           "reports": k["reports"], "people": k["people"], "incidents": k["incidents"],
           "incidents_by_stage": {x["name"]: x["n"] for x in s["stage_counts"]},
           "farm_alerts": k["farm_alerts"], "city_calls": k["calls"],
           "complaints_written": k["complaints"], "complaints_submitted": k["complaints_done"],
           "median_min_first_report_to_farm_alert": k["med_min_to_alert"],
           "median_min_first_report_to_city_call": k["med_min_to_call"],
           "days_total": k["days_total"], "days_without_reports": k["quiet_days"],
           "by_village": [{"village": v["village"], "reports": v["reports"], "people": v["people"],
                           "incidents": v["incidents"], "city_calls": v["calls"]} for v in s["by_village"]]}
    if hour_from is not None or hour_to is not None:
        a, b = hour_from or 0, hour_to or 24
        n = sum(sum(r["hours"][a:b]) for r in s["heat"])
        out["hour_range"] = f"{a}~{b}시"
        out["reports_in_hour_range"] = n
        out["share_of_reports_in_hour_range_pct"] = round(100 * n / k["reports"], 1) if k["reports"] else None
    return out


def t_hourly_daily(S, period, village):
    s = _range(S, period, village)
    hours = [0] * 24
    for r in s["heat"]:
        for i, n in enumerate(r["hours"]):
            hours[i] += n
    daily = [d for d in s["daily"]]
    top_h = sorted(range(24), key=lambda i: -hours[i])[:3]
    top_d = sorted(daily, key=lambda d: -d["n"])[:3]
    out = {"period": period, "village": village or "전체", "simulated": s["simulated"], "data_kind": "시연용 가상 신고",
           "reports_by_hour": {f"{i}시": hours[i] for i in range(24) if hours[i]},
           "top_hours": [{"hour": f"{i}시", "reports": hours[i]} for i in top_h if hours[i]],
           "top_days": [d for d in top_d if d["n"]],
           "days_total": len(daily), "days_without_reports": sum(1 for d in daily if d["n"] == 0)}
    if len(daily) <= 31:
        out["reports_by_day"] = {d["date"][5:]: d["n"] for d in daily if d["n"]}
    return out


def t_incident_list(S, period, village, min_stage):
    s = _range(S, period, village)
    rows = [i for i in s["incidents"] if i["stage"] >= min_stage][:10]

    def after(i, t):
        return next((x["after_min"] for x in i["steps"] if x["type"] == t), None)

    return {"period": period, "village": village or "전체", "simulated": s["simulated"], "data_kind": "시연용 가상 신고",
            "count_matching": sum(1 for i in s["incidents_all"] if i["stage"] >= min_stage),
            "incidents": [{"start": i["start"].replace("T", " "), "village": i["village"], "reports": i["reports"],
                           "people": i["people"], "max_stage": i["stage_name"], "duration_min": i["duration_min"],
                           "min_to_farm_alert": after(i, "farm_alert"), "min_to_city_call": after(i, "city_call"),
                           "min_to_complaint": after(i, "complaint"), "outcome": i["outcome"]} for i in rows]}


def t_measurement_stats(S, year_from, year_to):
    rows = [r for r in data.measurements()
            if (year_from is None or int(r["year"]) >= year_from) and (year_to is None or int(r["year"]) <= year_to)]
    ov = history.overview(rows)
    mx = max(rows, key=lambda r: float(r["value"]), default=None)
    return {"data_kind": "실제 실측", "source": "제주악취관리센터 악취조사 DB, 광령리 A구역 정기 실측(농장 4곳 부지경계 합산)",
            "period": f"{min(r['date'] for r in rows)}~{max(r['date'] for r in rows)}" if rows else None,
            "standard": "악취관리지역 부지경계 복합악취 배출허용기준 희석배수 10 (일반지역 15)",
            "all": ov["all"], "by_year": ov["by_year"], "by_year_common_slots": ov["by_year_common_slots"],
            "by_time_slot": ov["by_slot"],
            "max": {"value": float(mx["value"]), "date": mx["date"], "slot": mx["slot_label"]} if mx else None,
            "note": "over10 = 기준(10) 초과, over15 = 참고 지표. 분기 1회라 연도별 건수가 적다. 2025년부터 20~22시 측정이 없고 "
                    "2026년은 상반기만 있다. 정기 실측의 기준 초과는 행정처분 건수와 같은 것이 아니다."}


def t_facility_stats(S, group_by, area_filter):
    fs = data.facilities()
    if area_filter:
        fs = [f for f in fs if area_filter in f["읍면"] or area_filter in f["리"] or area_filter in f["주소"]]
    g = defaultdict(lambda: {"facilities": 0, "in_odor_control_area": 0, "site_area_m2": 0.0})
    for f in fs:
        key = {"읍면": f["읍면"], "리": f"{f['읍면']} {f['리']}", "구분": f["구분"]}[group_by]
        g[key]["facilities"] += 1
        g[key]["in_odor_control_area"] += f["구분"] == "악취관리지역"
        g[key]["site_area_m2"] += float(f["부지면적"] or 0)
    rows = sorted(({"group": k, **{**v, "site_area_m2": round(v["site_area_m2"])}} for k, v in g.items()),
                  key=lambda x: -x["facilities"])
    return {"data_kind": "지정 데이터(제주데이터허브)", "source": "제주데이터허브 「제주특별자치도_악취배출시설현황」(2019.7.19 기준)",
            "filter": area_filter or "없음(제주 전체 목록)",
            "all_facilities": len(fs), "all_in_odor_control_area": sum(f["구분"] == "악취관리지역" for f in fs),
            "groups_are": f"{group_by}별 값. 그룹 값은 그 그룹만의 수다.", "groups": rows,
            "note": "58행은 이 파일(2019.7.19 기준)의 행 수로, 지금 제주 전체 시설 수와 같다고 볼 수 없다. "
                    "광령리 실측 농장은 이 목록에 없어 목록 시점·범위 확인이 필요하다."}


IMPL = {"complaint_history": lambda S, **k: admin_records.complaint_history(**k),
        "inspection_history": lambda S, **k: admin_records.inspection_history(**k),
        "coverage_compare": lambda S, **k: admin_records.coverage_compare(**k),
        "report_stats": t_report_stats, "hourly_daily": t_hourly_daily, "incident_list": t_incident_list,
        "measurement_stats": t_measurement_stats, "facility_stats": t_facility_stats}


# ---------------------------------------------------------------- Agent 루프
def ask(S, question: str, history_turns: list[dict] | None = None) -> dict:
    t0 = time.time()
    if not llm.available():
        return {"answer": "말로 묻는 분석은 Claude API 키가 있어야 동작합니다(.env 의 ANTHROPIC_API_KEY). "
                          "키가 없어도 아래 표와 그래프는 그대로 쓸 수 있습니다.", "steps": [], "ok": False}
    messages = []
    for h in (history_turns or [])[-3:]:      # 이어 묻기: 앞선 질문·답(글자만) 3개까지
        messages += [{"role": "user", "content": h["q"]}, {"role": "assistant", "content": h["a"]}]
    messages.append({"role": "user", "content": f"(오늘: {S.now():%Y-%m-%d %H:%M})\n{question}"})
    steps, usage = [], {"input": 0, "output": 0}
    try:
        for _ in range(MAX_STEPS):
            resp = llm.client().messages.create(
                model=llm.model(), max_tokens=4000, system=SYSTEM, tools=TOOLS,
                output_config={"effort": "medium"}, messages=messages)
            usage["input"] += resp.usage.input_tokens
            usage["output"] += resp.usage.output_tokens
            if resp.stop_reason == "refusal":
                return {"answer": "이 질문에는 답할 수 없습니다.", "steps": steps, "ok": False}
            calls = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not calls:
                answer = llm._text(resp) or "답을 만들지 못했습니다. 질문을 조금 바꿔 다시 해 주세요."
                return {"answer": answer, "steps": steps, "ok": True, "model": llm.model(), "usage": usage,
                        "seconds": round(time.time() - t0, 1)}
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for c in calls:
                try:
                    out = IMPL[c.name](S, **c.input)
                    results.append({"type": "tool_result", "tool_use_id": c.id,
                                    "content": json.dumps(out, ensure_ascii=False, default=str)})
                    steps.append({"tool": c.name, "label": TOOL_LABEL.get(c.name, c.name), "input": c.input, "output": out})
                except Exception as e:  # 도구 오류는 Claude에게 알려 고쳐 부르게 한다
                    results.append({"type": "tool_result", "tool_use_id": c.id, "content": f"오류: {e}", "is_error": True})
                    steps.append({"tool": c.name, "label": TOOL_LABEL.get(c.name, c.name), "input": c.input, "error": str(e)})
            messages.append({"role": "user", "content": results})
        return {"answer": "도구를 너무 많이 불러 멈췄습니다. 질문을 나눠서 해 주세요.", "steps": steps, "ok": False}
    except anthropic.APIConnectionError:
        return {"answer": "Claude에 연결하지 못했습니다(인터넷 또는 보안 프로그램 확인). 아래 표와 그래프는 그대로 쓸 수 있습니다.",
                "steps": steps, "ok": False}
    except anthropic.APIStatusError as e:
        return {"answer": f"Claude API 오류({e.status_code}): 키나 사용 한도를 확인해 주세요.", "steps": steps, "ok": False}
