"""악취조사 DB 실측 통계.
기준: 광령리 A구역은 2018년 지정 악취관리지역이라 부지경계 복합악취 희석배수 10 이 배출허용기준이다
(일반지역 15). 15 초과는 참고 지표로만 함께 준다. 정기 실측의 기준 초과는 행정처분과 같은 것이 아니다."""
from collections import defaultdict
from backend import data

LIMIT = 10        # 악취관리지역 부지경계 배출허용기준 (복합악취 희석배수)
COMMON_SLOTS = ("오전(08-11)", "오후(14-17)", "야간1(18-20)")   # 2025년부터 야간2(20-22)가 없다


def _agg(rows):
    n = len(rows)
    o10 = sum(float(r["value"]) > LIMIT for r in rows)
    o15 = sum(float(r["value"]) > 15 for r in rows)
    return {"n": n, "over10": o10, "over10_pct": round(100 * o10 / n, 1) if n else None,
            "over15": o15, "over15_pct": round(100 * o15 / n, 1) if n else None}


def overview(rows=None) -> dict:
    rows = data.measurements() if rows is None else rows
    by_year, by_slot, by_year_common = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)
        by_slot[r["slot_label"]].append(r)
        if r["slot_label"] in COMMON_SLOTS:
            by_year_common[r["year"]].append(r)
    return {"n": len(rows), "all": _agg(rows),
            "by_year": {y: _agg(v) for y, v in sorted(by_year.items())},
            "by_year_common_slots": {y: _agg(v) for y, v in sorted(by_year_common.items())},
            "by_slot": {k: _agg(v) for k, v in sorted(by_slot.items())}}
