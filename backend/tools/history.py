"""get_farm_history, query_stats: 악취조사 DB 실측으로 농장 이력·통계를 계산한다."""
from collections import defaultdict
from backend import data


def farm_history(name: str) -> dict:
    rows = [r for r in data.measurements() if r["farm"] == name]
    by_year = defaultdict(lambda: [0, 0])
    for r in rows:
        by_year[r["year"]][0] += 1
        by_year[r["year"]][1] += r["over15"] == "True"
    mx = max(rows, key=lambda r: float(r["value"]), default=None)
    return {"farm": name, "n": len(rows),
            "over15_rate_by_year": {y: round(100 * o / n, 1) for y, (n, o) in sorted(by_year.items())},
            "max": {"value": float(mx["value"]), "date": mx["date"], "slot": mx["slot_label"]} if mx else None}


def overview() -> dict:
    rows = data.measurements()
    by_year, by_slot = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in rows:
        o = r["over15"] == "True"
        by_year[r["year"]][0] += 1; by_year[r["year"]][1] += o
        by_slot[r["slot_label"]][0] += 1; by_slot[r["slot_label"]][1] += o
    rate = lambda d: {k: round(100 * o / n, 1) for k, (n, o) in d.items()}
    return {"n": len(rows), "over15_rate_by_year": dict(sorted(rate(by_year).items())),
            "over15_rate_by_slot": rate(by_slot)}
