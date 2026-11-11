"""가상 신고 기록 만들기 (대회판 시연용).
지난 N일 동안의 주민 신고를 만들어 실제 판단 엔진에 시간 순서대로 넣는다.
그래서 단계·농장 알림·대표 전화·민원서가 엔진 규칙 그대로 생긴다.
- 시간대 분포는 실측 경향(오전 > 오후 > 저녁, 새벽 드묾)을 따르지만 숫자 자체는 가상이다.
- 같은 시드면 같은 결과가 나온다(재현성)."""
import heapq
import random
from datetime import datetime, timedelta
from backend import data

TEXTS = {
    2: ["냄새 좀 나네", "약간 냄새 나요", "살짝 냄새남"],
    3: ["냄새 나요", "창문을 못 열겠다", "또 악취", "축사 냄새 나네"],
    4: ["냄새 심하다", "냄새 너무 심함", "냄새 엄청 나네", "냄새 진짜 심해요"],
    5: ["냄새 때문에 숨을 못 쉬겠어", "토할 것 같아요 냄새", "냄새 죽겠다"],
}
# 시간대별 사건 시작 가중치 (0~23시)
HOUR_W = [0.2, 0.1, 0.1, 0.1, 0.2, 0.5, 1.5, 3.5, 4.5, 4.0, 3.0, 2.0,
          1.5, 1.8, 2.5, 2.6, 2.2, 1.6, 1.4, 1.2, 0.8, 0.6, 0.4, 0.3]
VILLAGE_W = {"광령1리": 0.8, "광령2리": 1.3, "광령3리": 0.6}


# 날마다 냄새 정도가 다르다: 0 없음 · 1 약함 · 2 보통 · 3 심함
# 기준: 제주시 정보공개(2023.1~2026.9) 광령리 민원 있는 날 652일 / 전체 1,369일 ≈ 48% (신고 없는 날 절반 남짓)
# → 신고 없는 날 약 56%. 날씨가 며칠 이어지듯 냄새 정도도 전날을 따라가는 경향(STAY)이 있다.
DAY_LEVELS = [0, 1, 2, 3]
DAY_BASE = [0.56, 0.22, 0.14, 0.08]
STAY = 0.45
# 냄새 정도별: (영향받는 마을 수 범위, 마을당 사건 수 범위, 사건당 신고 주민 수 범위, 지속될 확률)
DAY_PROFILE = {
    0: None,
    1: ((1, 1), (1, 1), (1, 3), 0.0),
    2: ((1, 2), (1, 2), (3, 9), 0.1),
    3: ((2, 3), (1, 3), (6, 16), 0.5),
}
DAY_NAME = {0: "없음", 1: "약함", 2: "보통", 3: "심함"}


def _day_levels(rng, days):
    out, prev = [], None
    for _ in range(days):
        if prev is not None and rng.random() < STAY:
            lvl = prev
        else:
            lvl = rng.choices(DAY_LEVELS, weights=DAY_BASE)[0]
        out.append(lvl)
        prev = lvl
    return out


def generate(S, handle_message, farm_respond, approve_complaint, days=30, seed=40):
    rng = random.Random(seed)
    today0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_day = today0 - timedelta(days=days)
    villages = [v["village"] for v in data.villages()]
    events = []  # (시각, 순번, 종류, 값)
    k = 0

    levels = _day_levels(rng, days)
    for d, lvl in enumerate(levels):
        day = start_day + timedelta(days=d)
        prof = DAY_PROFILE[lvl]
        if prof is None:
            continue  # 냄새 없는 날: 신고 없음
        (v_lo, v_hi), (i_lo, i_hi), (p_lo, p_hi), persist_p = prof
        n_v = min(len(villages), rng.randint(v_lo, v_hi))
        hit = []
        pool = list(villages)
        for _ in range(n_v):  # 신고가 잦은 마을이 먼저 뽑히도록 가중치
            v = rng.choices(pool, weights=[VILLAGE_W.get(x, 1) for x in pool])[0]
            hit.append(v); pool.remove(v)
        for v in hit:
            for _ in range(rng.randint(i_lo, i_hi)):
                h = rng.choices(range(24), weights=HOUR_W)[0]
                t0 = day + timedelta(hours=h, minutes=rng.randint(0, 59))
                people = rng.sample(range(1, 80), rng.randint(p_lo, p_hi))
                for j, p in enumerate(people):
                    lvl = rng.choices([2, 3, 4, 5], weights=[2, 4, 4, 1])[0]
                    ts = t0 + timedelta(minutes=int(j * rng.uniform(1, 55 / max(1, len(people)))))
                    events.append((ts, k, "msg", (f"sim_{v}_{p}", rng.choice(TEXTS[lvl]), v))); k += 1
                # 경보급 사건 일부는 3시간 넘게 이어진다 → 지속 단계
                if len(people) >= 10 and rng.random() < persist_p:
                    for p in rng.sample(people, 2):
                        ts = t0 + timedelta(hours=3, minutes=rng.randint(10, 50))
                        events.append((ts, k, "msg", (f"sim_{v}_{p}", rng.choice(TEXTS[4]), v))); k += 1

    heapq.heapify(events)
    seen_alerts, seen_complaints = set(), set()
    S.rule_only = True
    try:
        while events:
            ts, _, kind, val = heapq.heappop(events)
            if ts >= datetime.now():
                continue
            S.fixed_now = ts
            if kind == "msg":
                handle_message(*val[:2], place_village=val[2], source="synthetic_history")
            elif kind == "farm":
                farm_respond(*val)
            elif kind == "approve":
                approve_complaint(val)
            # 새로 생긴 알림·민원서에 대한 후속 처리 예약
            for fid, box in S.farm_inbox.items():
                for a in box:
                    if a["id"] in seen_alerts:
                        continue
                    seen_alerts.add(a["id"])
                    if rng.random() < 0.6:
                        t = ts + timedelta(minutes=rng.randint(15, 90))
                        heapq.heappush(events, (t, k, "farm", (fid, a["id"], rng.choice(["저감시설 가동함", "확인 중", "저감시설 가동함"])))); k += 1
            for a in S.actions:
                if a["type"] == "complaint" and a["id"] not in seen_complaints:
                    seen_complaints.add(a["id"])
                    if rng.random() < 0.8:
                        heapq.heappush(events, (ts + timedelta(minutes=rng.randint(40, 180)), k, "approve", a["id"])); k += 1
    finally:
        S.fixed_now = None
        S.rule_only = False
    return {"reports": len(S.reports), "incidents": len(S.incident_log),
            "day_levels": {(start_day + timedelta(days=d)).date().isoformat(): DAY_NAME[l]
                           for d, l in enumerate(levels)}}
