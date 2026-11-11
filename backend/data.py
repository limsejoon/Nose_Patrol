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


def _processed(name):
    p = config.DATA_PROCESSED / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@lru_cache
def admin_complaints():
    """제주시 정보공개청구: 광령리 축산 악취 민원 접수 (2023.1.1~2026.9.30). 접수시각 1개 = 1행.
    scripts/prepare_admin_records.py 로 PDF에서 만든다. 처리내용 원문·이름은 없다."""
    return _processed("admin_complaints.csv")


@lru_cache
def admin_inspections():
    """제주시 정보공개청구: 광령리·고성리 지도점검 673행 (날짜·분류만)."""
    return _processed("admin_inspections.csv")


@lru_cache
def admin_actions():
    """제주시 정보공개청구: 광령리·고성리 행정처분 4사례 (사업장명 없이)."""
    return _processed("admin_actions.csv")


@lru_cache
def admin_manure():
    """제주시 정보공개청구: 광령·고성 양돈농가 액비살포 9건."""
    return _processed("admin_manure.csv")


def village(name):
    return next((v for v in villages() if v["village"] == name), None)
