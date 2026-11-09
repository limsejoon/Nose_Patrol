"""data/raw 의 CSV를 읽는다."""
import csv
from functools import lru_cache
from backend import config


def _read(name):
    p = config.DATA_RAW / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@lru_cache
def villages():
    out = []
    for r in _read("villages.csv"):
        out.append({"village": r["village"], "aliases": r["aliases"].split("|"),
                    "lat": float(r["lat"]), "lon": float(r["lon"]),
                    "population": int(r["population"])})
    return out


@lru_cache
def farms():
    """실측 대상 농장. 위치를 못 찾은 농장은 lat/lon 이 None (지도·바람 계산에서 빠짐)."""
    num = lambda x: float(x) if x not in (None, "") else None
    return [{"farm_id": r["farm_id"], "name": r["name"], "village": r["village"],
             "address": r.get("address", ""), "lat": num(r["lat"]), "lon": num(r["lon"]),
             "coord_source": r.get("coord_source", ""),
             "in_hub_list": r["in_hub_list"] == "True", "note": r["note"]}
            for r in _read("farms.csv")]


@lru_cache
def measurements():
    return _read("광령리_악취실측_2020-2026.csv")


@lru_cache
def facilities():
    """필수 데이터 「악취배출시설현황」 전처리 결과 (scripts/prepare_facilities.py 로 만든다)."""
    p = config.DATA_PROCESSED / "facilities.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r["lat"]]


def village(name):
    return next((v for v in villages() if v["village"] == name), None)
