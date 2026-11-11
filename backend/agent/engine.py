"""냄새알림 Agent 판단 엔진.
신고 해석 → 사건 묶기(같은 마을·최근 1시간) → 단계 판단 → 행동(농장 알림 / 대표 민원 전화 / 민원서 초안).
숫자는 모두 여기와 tools가 계산한다. LLM은 문장 해석에만 쓴다.
원인 농장과 풍향은 화면·문안에 표시하지 않는다(명예훼손 방지). 풍향 계산은 주의 알림을 보낼
바람 위쪽 농장을 고르는 데만 내부적으로 쓴다."""
import itertools
from datetime import datetime, timedelta
from backend import config, data
from backend.fallback import rule_parser
from backend.tools import parse_report, geo, drafts, history

STAGES = ["관찰", "주의", "경보", "지속"]
_id = itertools.count(1)


class State:
    def __init__(self):
        self.reset()

    def reset(self):
        self.clock_offset = timedelta()
        self.users = {}       # 익명 ID → {"village", "pending"}
        self.reports = []
        self.incidents = {}     # 마을 → 진행 중인 사건
        self.incident_log = []  # 지금까지의 모든 사건 (통계용)
        self.fixed_now = None   # 과거 기록을 다시 돌릴 때 쓰는 시각
        self.rule_only = False  # 과거 기록 재생 때는 LLM을 부르지 않는다
        self.actions = []     # 농장 알림, 민원 전화, 문자, 민원서
        self.farm_inbox = {}  # farm_id → [알림]

    def now(self):
        return self.fixed_now or (datetime.now() + self.clock_offset)


S = State()


def _inc(village):
    return S.incidents.get(village) or {"stage": 0, "alarm_at": None}


def _incident_for(village, now):
    """같은 마을에서 신고가 이어지면 같은 사건. PERSIST_HOURS*2 동안 조용하면 새 사건을 연다."""
    cur = S.incidents.get(village)
    if cur is None or now - cur["last"] > timedelta(hours=config.PERSIST_HOURS * 2):
        cur = {"id": next(_id), "village": village, "start": now, "last": now, "stage": 0,
               "alarm_at": None, "last_call": None, "farm_alert_sent": False, "complaint_id": None}
        S.incidents[village] = cur
        S.incident_log.append(cur)
    cur["last"] = now
    return cur


def _recent(village, now):
    since = now - timedelta(minutes=config.WINDOW_MIN)
    return [r for r in S.reports if r["village"] == village and r["ts"] >= since]


def village_status(village, now=None):
    now = now or S.now()
    rec = _recent(village, now)
    latest = {}                       # 같은 사람이 여러 번 보내면 가장 최근 강도 하나만 센다
    for r in sorted(rec, key=lambda r: r["ts"]):
        latest[r["user"]] = r["intensity"]
    n = len(latest)
    avg = sum(latest.values()) / n if n else 0.0
    v = data.village(village)
    per_1000 = round(1000 * n / v["population"], 2) if v and v["population"] else None
    inc = _inc(village)
    stage = 0
    if n >= config.CAUTION_MIN_PEOPLE or (avg >= config.CAUTION_AVG_INTENSITY and n >= 2):
        stage = 1
    if n >= config.ALARM_MIN_PEOPLE:
        stage = 2
    if inc["alarm_at"] and n >= 1 and now - inc["alarm_at"] >= timedelta(hours=config.PERSIST_HOURS):
        stage = 3
    return {"village": village, "n": n, "avg": round(avg, 1), "per_1000": per_1000,
            "stage": stage, "stage_name": STAGES[stage], "reports_window": len(rec)}


def _act(kind, village, payload, status="기록됨"):
    a = {"id": next(_id), "ts": S.now().isoformat(timespec="seconds"), "type": kind,
         "village": village, "payload": payload, "status": status,
         "incident_id": (S.incidents.get(village) or {}).get("id")}
    S.actions.append(a)
    return a


def _escalate(village, st):
    """단계가 올라가면 행동한다. 같은 사건에 같은 행동을 반복하지 않는다."""
    inc, now = _inc(village), S.now()
    v = data.village(village)
    wind = geo.get_wind(now)
    cands = geo.rank_sources(v["lat"], v["lon"], wind) if v else []
    done = []
    if st["stage"] >= 1 and not inc["farm_alert_sent"] and cands:  # 바람 위쪽 농장이 없으면 보내지 않는다
        msg = drafts.farm_alert(village, st["n"])
        for c in cands:
            alert = {"id": next(_id), "ts": now.isoformat(timespec="seconds"), "village": village,
                     "message": msg, "response": None, "incident_id": inc["id"]}
            S.farm_inbox.setdefault(c["farm_id"], []).append(alert)
        _act("farm_alert", village, {"farm_count": len(cands), "message": msg})
        inc["farm_alert_sent"] = True
        done.append("farm_alert")
    if st["n"] >= config.ALARM_MIN_PEOPLE and (inc["last_call"] is None or now - inc["last_call"] >= timedelta(hours=config.PERSIST_HOURS)):
        _act("city_call", village, {"to": "제주시 담당부서(사전 등록 번호)",
                                    "script": drafts.call_script(village, st["n"], st["avg"])},
             status="발신 기록(대회판: 실제 발신 안 함)")
        _act("sms", village, {"to": "제주시 담당부서", "text": drafts.sms(village, st["n"], st["avg"])},
             status="발송 기록(대회판)")
        inc["last_call"] = now
        inc["alarm_at"] = inc["alarm_at"] or now
        done.append("city_call")
    if st["stage"] >= 3 and not inc["complaint_id"]:
        total = len({r["user"] for r in S.reports if r["village"] == village
                     and r["ts"] >= inc["alarm_at"] - timedelta(minutes=config.WINDOW_MIN)})
        # 농장별 이력은 이름이 드러나므로 넣지 않고, 측정구역 전체 통계만 쓴다.
        hist = []
        ov = history.overview()
        if ov["n"]:
            y, d = list(ov["by_year"].items())[-1]
            hist.append(f"광령리 악취관리지역 측정구역 {y}년 정기 실측 {d['n']}건 중 {d['over10']}건이 "
                        f"부지경계 기준(희석배수 10)을 넘음")
        a = _act("complaint", village, {"text": drafts.complaint(village, total, config.PERSIST_HOURS, hist)},
                 status="마을 대표 승인 대기")
        inc["complaint_id"] = a["id"]
        done.append("complaint")
    inc["stage"] = max(inc["stage"], st["stage"])
    return done, cands, wind


def _parse(text):
    return rule_parser.parse(text, data.villages()) if S.rule_only else parse_report.parse(text)


def handle_message(user: str, text: str, place_village: str | None = None, source: str = "simulator") -> dict:
    """주민 카톡 메시지 하나를 처리하고 답장을 돌려준다.
    source: 신고가 어디서 왔는지. 대회판은 모두 시연용이다
      simulator(카톡 시뮬레이터 직접 입력) / demo_script(시연 대본) / synthetic_history(가상 한 달 기록)"""
    u = S.users.setdefault(user, {"village": None, "pending": None})
    p = _parse(text)

    # 처음 신고: 동네를 한 번만 묻는다
    if u["village"] is None and not p.get("village") and not place_village:
        if p.get("is_report"):
            u["pending"] = text
            return {"reply": "처음이시죠? 어느 동네 사세요? 한 번만 알려 주시면 기억할게요. (예: 광령 2리)", "parsed": p}
        return {"reply": "냄새가 나면 평소 말로 보내 주세요. 예: \"오늘 아침부터 냄새 심하다\"", "parsed": p}

    if u["village"] is None:
        u["village"] = place_village or p["village"]
        if u["pending"] and not p.get("is_report"):
            text, u["pending"] = u["pending"], None
            p = _parse(text)
            p["village"] = None

    if not p.get("is_report"):
        return {"reply": f"{u['village']}으로 기억해 둘게요. 냄새가 나면 평소 말로 보내 주세요.", "parsed": p}

    village = place_village or p.get("village") or u["village"]
    now = S.now()
    inc = _incident_for(village, now)
    rep = {"id": next(_id), "ts": now, "user": user, "village": village, "text": text,
           "incident_id": inc["id"], "source": source,
           "intensity": p.get("intensity") or 3, "time": p.get("time") or "지금",
           "odor": p.get("odor"), "place": p.get("place"), "parser": p.get("parser")}
    S.reports.append(rep)

    before = inc["stage"]
    st = village_status(village, now)
    done, cands, wind = _escalate(village, st)
    today = sum(1 for r in S.reports if r["village"] == village and r["ts"].date() == now.date())
    words = {1: "희미함", 2: "약함", 3: "분명함", 4: "꽤 심함", 5: "아주 심함"}
    reply = f"{village} · {words.get(rep['intensity'], '')}({rep['intensity']}단계)으로 접수했어요. 오늘 이 동네 {today}번째 신고예요."
    if "complaint" in done:
        reply += "\n냄새가 3시간 넘게 이어져 민원서 초안을 만들었어요. 마을 대표가 승인하면 제출해요.(대회판: 실제 제출 안 함)"
    elif "city_call" in done:
        reply += f"\n이웃 {st['n']}분이 같은 냄새를 신고해서, 시청에 걸 대표 민원 전화 문안을 만들었어요.(대회판: 실제 발신 안 함)"
    elif "farm_alert" in done:
        reply += "\n주변 농장에 저감시설 점검 요청 알림을 보냈어요.(농장주 화면)"
    return {"reply": reply, "parsed": p, "report_id": rep["id"], "stage_before": before, "status": st}


def farm_respond(farm_id: str, alert_id: int, response: str):
    for a in S.farm_inbox.get(farm_id, []):
        if a["id"] == alert_id:
            a["response"] = response
            a["responded_at"] = S.now().isoformat(timespec="seconds")
            r = _act("farm_response", a["village"], {"farm_id": farm_id, "response": response})
            r["incident_id"] = a.get("incident_id")
            return a
    return None


def approve_complaint(action_id: int):
    for a in S.actions:
        if a["id"] == action_id and a["type"] == "complaint":
            a["status"] = "마을 대표 승인 · 제출 기록(대회판: 실제 제출 안 함)"
            a["approved_at"] = S.now().isoformat(timespec="seconds")
            return a
    return None


def snapshot():
    now = S.now()
    wind = geo.get_wind(now)
    vs = []
    for v in data.villages():
        st = village_status(v["village"], now)
        st.update({"lat": v["lat"], "lon": v["lon"]})
        vs.append(st)
    recent = sorted(S.reports, key=lambda r: r["ts"])[-50:]
    reps = [{**r, "ts": r["ts"].isoformat(timespec="seconds")} for r in recent]
    return {"now": now.isoformat(timespec="seconds"), "wind": wind, "villages": vs,
            "farms": data.farms(), "reports": reps[::-1], "actions": sorted(S.actions, key=lambda a: (a["ts"], a["id"]), reverse=True)[:60],
            "farm_inbox": S.farm_inbox}
