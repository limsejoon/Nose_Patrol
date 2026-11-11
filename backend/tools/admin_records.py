"""실제 행정 자료(제주시 정보공개청구) 집계. 숫자는 모두 여기서 계산한다.

자료 범위와 한계 (도구 결과에 항상 같이 준다)
- 민원: 광령리 축산 악취 민원 '접수' 기록. 접수시각이지 냄새가 난 시각이 아니다. 민원인 식별 정보가 없어 사람 수는 모른다.
- 지도점검·행정처분·액비살포: 광령리와 고성리 합계라 민원(광령리)과 바로 나누면 안 된다.
- 정기 실측(악취조사 DB)은 광령리 A구역 농장 4곳 부지경계, 분기 1회.
"""
from collections import Counter, defaultdict
from datetime import date

from backend import data

SOURCE_C = "제주시 정보공개청구 「애월읍 광령리 축산 악취 민원접수(2023.1.1~2026.9.30)」"
SOURCE_I = "제주시 정보공개청구 「애월읍 광령리 및 고성리 지도점검」·「행정처분 내역」·「액비살포 내역」(2023.1.1~2026.9.30 요청)"
SOURCE_M = "제주악취관리센터 악취조사 DB, 광령리 A구역 정기 실측"
WEEKDAY = "월화수목금토일"

# 정기 실측 시간대. 2020~2024년은 야간2(20~22시)가 있었고 2025년부터 없다 (악취조사 DB 시간표).
SLOTS_CURRENT = [(8, 11), (14, 17), (18, 20)]
SLOTS_TO_2024 = SLOTS_CURRENT + [(20, 22)]


def _year_ok(d, year_from, year_to):
    y = int(d[:4])
    return (year_from is None or y >= year_from) and (year_to is None or y <= year_to)


def _complaints(year_from=None, year_to=None):
    """오류 시각(24:14) 1행은 원문만 남기고 건수에서 뺀다 → 전체 1,778건."""
    return [r for r in data.admin_complaints()
            if r["time_status"] != "invalid" and _year_ok(r["date"], year_from, year_to)]


def _hour(r):
    h, m = r["time"].split(":")
    return int(h) + int(m) / 60


def _in_slots(r, timetable):
    slots = SLOTS_TO_2024 if timetable == "by_year" and r["date"] < "2025" else SLOTS_CURRENT
    x = _hour(r)
    return any(a <= x < b for a, b in slots)


def _period(rows, key="date"):
    ds = sorted(r[key] for r in rows)
    return f"{ds[0]}~{ds[-1]}" if ds else None


def complaint_history(year_from=None, year_to=None, group_by="year", hour_from=None, hour_to=None):
    rows = _complaints(year_from, year_to)
    timed = [r for r in rows if r["time_status"] == "ok"]
    if hour_from is not None or hour_to is not None:
        a, b = hour_from or 0, hour_to or 24
        rows = timed = [r for r in timed if a <= int(r["time"][:2]) < b]
    span_from = max(date(2023, 1, 1), date(year_from or 2023, 1, 1))
    span_to = min(date(2026, 9, 30), date(year_to or 2026, 12, 31))
    n_days = (span_to - span_from).days + 1
    key = {"year": lambda r: r["date"][:4], "month": lambda r: r["date"][:7],
           "month_of_year": lambda r: f"{int(r['date'][5:7])}월",
           "hour": lambda r: f"{int(r['time'][:2]):02d}시", "weekday": lambda r: WEEKDAY[date.fromisoformat(r['date']).weekday()],
           "method": lambda r: r["method"]}[group_by]
    base = timed if group_by == "hour" else rows
    groups = Counter(key(r) for r in base)
    if group_by in ("year", "month", "hour"):
        ordered = dict(sorted(groups.items()))
    elif group_by == "weekday":
        ordered = {d: groups.get(d, 0) for d in WEEKDAY}
    elif group_by == "month_of_year":
        ordered = {f"{m}월": groups.get(f"{m}월", 0) for m in range(1, 13)}
    else:
        ordered = dict(groups.most_common())
    acts = {"방제단 요청·연락": "act_spray", "농가 악취저감 요청·연락": "act_reduce", "저감 문자 발송": "act_sms",
            "현장확인·점검": "act_site", "민원인 통화·답변": "act_reply"}
    days = {r["date"] for r in rows}
    return {
        "data_kind": "실제 행정 기록", "source": SOURCE_C, "period": _period(rows),
        "filter": {"year_from": year_from, "year_to": year_to, "hour_range": f"{hour_from or 0}~{hour_to or 24}시"
                   if hour_from is not None or hour_to is not None else None},
        "complaints": len(rows), "complaints_with_time": len(timed),
        "days_with_complaints": len(days), "calendar_days_in_range": n_days,
        "per_day": round(len(rows) / n_days, 2),
        "group_by": group_by, "counts": ordered,
        "group_base": "접수시각이 있는 민원" if group_by == "hour" else "민원 전체",
        "handling_mentions": {k: sum(r[v] == "1" for r in rows) for k, v in acts.items()},
        "definition": "접수시각 1개 = 민원 1건. 한 칸에 시각이 여러 개면 각각 셈. 시각 '-' 17건은 건수에 넣고 시간대 분석에서 뺌. "
                      "있을 수 없는 시각 1건(24:14)은 건수에서도 뺌. 처리 종류는 처리내용 문구에 그 말이 들어 있는지로 분류(한 건에 여러 개 가능).",
        "cannot_tell": "접수 시각이지 냄새가 난 시각이 아님. 민원인 식별 정보가 없어 사람 수·반복 민원 여부는 알 수 없음. 원인 농장은 이 자료로 정할 수 없음.",
    }


def inspection_history(year_from=None, year_to=None):
    ins = [r for r in data.admin_inspections() if _year_ok(r["date"], year_from, year_to)]
    by_kind = defaultdict(lambda: {"rows": 0, "days": set()})
    for r in ins:
        by_kind[r["kind"]]["rows"] += 1
        by_kind[r["kind"]]["days"].add(r["date"])
    acts = data.admin_actions()
    in_range = [a for a in acts if _year_ok(a["action_date"], year_from or 2023, year_to)]
    manure = [m for m in data.admin_manure() if _year_ok(m["date"], year_from, year_to)]
    return {
        "data_kind": "실제 행정 기록", "source": SOURCE_I, "period": _period(ins), "area": "광령리·고성리 합계",
        "inspection_rows": len(ins), "inspection_days": len({r["date"] for r in ins}),
        "night_inspection_rows": sum(r["night"] == "1" for r in ins),
        "by_kind": {k: {"rows": v["rows"], "days": len(v["days"])}
                    for k, v in sorted(by_kind.items(), key=lambda x: -x[1]["rows"])},
        "administrative_actions": {
            "cases_in_document": len(acts),
            "cases_by_action_year": dict(Counter(a["action_date"][:4] for a in acts)),
            "cases_in_requested_period_2023_2026": len([a for a in acts if a["action_date"] >= "2023"]),
            "cases_in_filter": len(in_range),
            "actions_per_case": "개선명령 + 과태료 (사례마다 2개 처분)",
            "violation": "모두 악취배출허용기준 초과"},
        "liquid_manure": {"records": len(manure), "tons": round(sum(float(m["tons"]) for m in manure)),
                          "spread_place": sorted({m["place"] for m in manure}), "dates": [m["date"] for m in manure]},
        "definition": "지도점검 1행 = 문서의 1줄(같은 날 여러 줄 가능). 분류는 점검 문구로 정함: '포집·분석 의뢰'는 포집 후 분석 의뢰·포집 실시가 "
                      "적힌 줄, '포집 시도'는 시도만 적힌 줄, '포집 예정·안내'는 예정·안내.",
        "cannot_tell": "점검은 광령리·고성리 합계라 광령리 민원과 나눠 대응률·적발률을 내면 안 됨. 시험성적서가 없어 포집 결과는 모름. "
                       "행정처분 4사례 중 요청 기간(2023~) 안은 1사례. 액비살포 기록으로 민원 원인을 정할 수 없음. 사업장 이름은 주지 않음.",
    }


def coverage_compare(year_from=None, year_to=None, timetable="current"):
    rows = _complaints(year_from, year_to)
    timed = [r for r in rows if r["time_status"] == "ok"]
    outside = [r for r in timed if not _in_slots(r, timetable)]
    mdays = {r["date"] for r in data.measurements() if _year_ok(r["date"], year_from or 2023, year_to)
             and r["date"] <= "2026-09-30"}
    cdays = {r["date"] for r in rows}
    overlap = sorted(cdays & mdays)
    m_months = Counter(int(d[5:7]) for d in mdays)
    c_months = Counter(int(r["date"][5:7]) for r in rows)
    m_wd = Counter(WEEKDAY[date.fromisoformat(d).weekday()] for d in mdays)
    c_wd = Counter(WEEKDAY[date.fromisoformat(r["date"]).weekday()] for r in rows)
    return {
        "data_kind": "실제 행정 기록 × 실제 정기 실측", "sources": [SOURCE_C, SOURCE_M], "period": _period(rows),
        "timetable": {"current": "지금 정기 실측 시간표(08~11, 14~17, 18~20시)를 모든 해에 적용",
                      "by_year": "해마다 그 해 시간표 적용(2024년까지는 20~22시 포함)"}[timetable],
        "complaints_with_time": len(timed), "outside_measurement_hours": len(outside),
        "outside_pct": round(100 * len(outside) / len(timed), 1) if timed else None,
        "complaint_days": len(cdays), "measurement_days": len(mdays),
        "overlap_days": len(overlap), "overlap_dates": overlap,
        "months_without_measurement": [f"{m}월" for m in range(1, 13) if not m_months.get(m)],
        "complaints_in_months_without_measurement": sum(c_months[m] for m in range(1, 13) if not m_months.get(m)),
        "measurement_days_by_weekday": {d: m_wd.get(d, 0) for d in WEEKDAY},
        "complaints_by_weekday": {d: c_wd.get(d, 0) for d in WEEKDAY},
        "definition": "시간 구간은 시작 포함·끝 미포함(08:00~10:59 → 오전). 분모는 접수시각이 있는 민원. 겹친 날은 날짜만 같다는 뜻(같은 장소·시각 아님).",
        "cannot_tell": "접수 시각 기준이라 실제 냄새가 난 때와 다를 수 있음. 실측은 농장 부지경계, 민원은 마을이라 장소가 다름. "
                       "정기 실측 외의 수시 점검·주민 모니터링·드론 조사는 이 비교에 들어 있지 않음.",
    }
