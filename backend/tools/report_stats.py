"""report_stats: 지역·시간별 신고와 처리 경과를 집계한다 (통계 화면용).
숫자는 모두 여기서 계산한다. 원인 농장 정보는 다루지 않는다."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from backend import data

ACTION_LABEL = {"farm_alert": "농장 주의 알림", "city_call": "대표 민원 전화", "sms": "문자",
                "complaint": "민원서 작성", "farm_response": "농장 조치 응답"}
STAGES = ["관찰", "주의", "경보", "지속"]


def _t(x):
    return x if isinstance(x, datetime) else datetime.fromisoformat(x)


def _med(xs):
    return round(median(xs)) if xs else None


def build(S, days: int | None = 14, village: str | None = None) -> dict:
    now = S.now()
    since = now - timedelta(days=days) if days else None
    in_range = lambda ts: since is None or _t(ts) >= since
    want = lambda v: not village or v == village

    reps = [r for r in S.reports if in_range(r["ts"]) and want(r["village"])]
    acts = [a for a in S.actions if in_range(a["ts"]) and want(a["village"])]
    incs = [i for i in S.incident_log if (since is None or i["last"] >= since) and want(i["village"])]
    villages = [v["village"] for v in data.villages() if want(v["village"])]

    # 마을 × 시간대 (0~23시)
    heat = {v: [0] * 24 for v in villages}
    for r in reps:
        if r["village"] in heat:
            heat[r["village"]][r["ts"].hour] += 1

    # 날짜별 신고 수
    first_day = (since or min((r["ts"] for r in reps), default=now)).date()
    n_days = (now.date() - first_day).days + 1
    day_keys = [(first_day + timedelta(d)).isoformat() for d in range(n_days)]
    daily = Counter(r["ts"].date().isoformat() for r in reps)
    daily_rows = [{"date": d, "n": daily.get(d, 0)} for d in day_keys]

    # 사건별 처리 경과
    reps_by_inc, acts_by_inc = defaultdict(list), defaultdict(list)
    for r in S.reports:
        reps_by_inc[r.get("incident_id")].append(r)
    for a in S.actions:
        acts_by_inc[a.get("incident_id")].append(a)
    inc_rows = []
    for i in incs:
        rs = sorted(reps_by_inc[i["id"]], key=lambda r: r["ts"])
        if not rs:
            continue
        start = rs[0]["ts"]
        steps = [{"type": "report", "label": "첫 신고", "ts": start.isoformat(timespec="minutes"), "after_min": 0}]
        for a in sorted(acts_by_inc[i["id"]], key=lambda a: a["ts"]):
            if a["type"] == "sms":
                continue  # 대표 전화와 같은 시각, 같은 내용
            steps.append({"type": a["type"], "label": ACTION_LABEL.get(a["type"], a["type"]),
                          "ts": a["ts"][:16], "after_min": round((_t(a["ts"]) - start).total_seconds() / 60)})
            if a["type"] == "complaint" and a.get("approved_at"):
                steps.append({"type": "approved", "label": "마을 대표 승인·제출", "ts": a["approved_at"][:16],
                              "after_min": round((_t(a["approved_at"]) - start).total_seconds() / 60)})
        kinds = {s["type"] for s in steps}
        if "complaint" in kinds:
            outcome = "민원서 제출" if "approved" in kinds else "민원서 승인 대기"
        elif "city_call" in kinds:
            outcome = "시청 전달"
        elif "farm_alert" in kinds:
            outcome = "농장 주의 알림"
        else:
            outcome = "기록·접수 답장"
        inc_rows.append({
            "id": i["id"], "village": i["village"], "start": start.isoformat(timespec="minutes"),
            "end": rs[-1]["ts"].isoformat(timespec="minutes"),
            "duration_min": round((rs[-1]["ts"] - start).total_seconds() / 60),
            "reports": len(rs), "people": len({r["user"] for r in rs}),
            "avg_intensity": round(sum(r["intensity"] for r in rs) / len(rs), 1),
            "stage": i["stage"], "stage_name": STAGES[i["stage"]], "steps": steps, "outcome": outcome})
    inc_rows.sort(key=lambda x: x["start"], reverse=True)

    def first_after(row, kind):
        return next((s["after_min"] for s in row["steps"] if s["type"] == kind), None)

    # 마을별 요약
    by_v = []
    for v in villages:
        rv = [r for r in reps if r["village"] == v]
        iv = [x for x in inc_rows if x["village"] == v]
        av = [a for a in acts if a["village"] == v]
        cnt = Counter(a["type"] for a in av)
        comp = [a for a in av if a["type"] == "complaint"]
        by_v.append({
            "village": v, "reports": len(rv), "people": len({r["user"] for r in rv}),
            "avg_intensity": round(sum(r["intensity"] for r in rv) / len(rv), 1) if rv else None,
            "incidents": len(iv), "max_stage": max((x["stage"] for x in iv), default=None),
            "farm_alerts": cnt["farm_alert"], "calls": cnt["city_call"],
            "complaints": len(comp), "complaints_done": sum(1 for a in comp if a.get("approved_at")),
            "farm_responses": cnt["farm_response"],
            "med_min_to_call": _med([m for x in iv if (m := first_after(x, "city_call")) is not None]),
        })

    stage_counts = Counter(x["stage"] for x in inc_rows)
    cnt_all = Counter(a["type"] for a in acts)
    comp_all = [a for a in acts if a["type"] == "complaint"]
    return {
        "now": now.isoformat(timespec="minutes"), "days": days, "village": village,
        "villages": villages,
        "simulated": any(str(r["user"]).startswith("sim_") for r in reps),
        "kpi": {
            "reports": len(reps), "people": len({r["user"] for r in reps}), "incidents": len(inc_rows),
            "days_total": len(daily_rows), "quiet_days": sum(1 for d in daily_rows if d["n"] == 0),
            "farm_alerts": cnt_all["farm_alert"], "calls": cnt_all["city_call"],
            "complaints": len(comp_all), "complaints_done": sum(1 for a in comp_all if a.get("approved_at")),
            "farm_responses": cnt_all["farm_response"],
            "med_min_to_alert": _med([m for x in inc_rows if (m := first_after(x, "farm_alert")) is not None]),
            "med_min_to_call": _med([m for x in inc_rows if (m := first_after(x, "city_call")) is not None]),
        },
        "stage_counts": [{"stage": s, "name": STAGES[s], "n": stage_counts.get(s, 0)} for s in range(4)],
        "heat": [{"village": v, "hours": heat[v]} for v in villages],
        "daily": daily_rows,
        "by_village": by_v,
        "incidents": inc_rows[:60],
    }
