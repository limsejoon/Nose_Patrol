"""필수 데이터 「제주특별자치도_악취배출시설현황」 전처리.
data/raw/제주특별자치도_악취배출시설현황.csv → data/processed/facilities.csv

하는 일
1. 주소에서 읍면·리를 뽑는다
2. 중복 의심 표시: 같은 주소에 사업장이 여럿 / 같은 이름이 여러 주소
3. 좌표 찾기
   - .env 에 VWORLD_API_KEY 가 있으면: 브이월드 지번 주소 → 정확한 좌표 (precision=지번)
   - 없으면: OpenStreetMap Nominatim 으로 '리' 중심 좌표 (precision=리 중심(근사))
   한 번 찾은 좌표는 data/processed/geocode_cache.json 에 저장해 다시 묻지 않는다.

실행: python scripts/prepare_facilities.py
"""
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "제주특별자치도_악취배출시설현황.csv"
OUT = ROOT / "data" / "processed" / "facilities.csv"
CACHE = ROOT / "data" / "processed" / "geocode_cache.json"
UA = "nose-patrol/0.1 (odor-report demo)"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
VWORLD_KEY = os.getenv("VWORLD_API_KEY", "")


def split_addr(addr):
    m = re.search(r"(\S+[읍면])\s+(\S+리)\s+(.+)$", addr)
    return (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)


def vworld(addr):
    r = httpx.get("https://api.vworld.kr/req/address", timeout=10, params={
        "service": "address", "request": "getcoord", "version": "2.0", "crs": "epsg:4326",
        "address": addr, "type": "parcel", "format": "json", "key": VWORLD_KEY})
    j = r.json().get("response", {})
    if j.get("status") == "OK":
        p = j["result"]["point"]
        return float(p["y"]), float(p["x"])
    return None


def nominatim(q):
    r = httpx.get("https://nominatim.openstreetmap.org/search", timeout=15, headers={"User-Agent": UA},
                  params={"q": q, "format": "json", "limit": 1, "countrycodes": "kr"})
    time.sleep(1.1)  # 이용 정책: 초당 1회
    j = r.json()
    return (float(j[0]["lat"]), float(j[0]["lon"])) if j else None


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    with open(RAW, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    addr_n = Counter(r["소재지(대표주소)"].strip() for r in rows)
    name_addrs = defaultdict(set)
    for r in rows:
        name_addrs[r["사업장명"].strip()].add(r["소재지(대표주소)"].strip())

    out = []
    for i, r in enumerate(rows, 1):
        addr = r["소재지(대표주소)"].strip()
        name = r["사업장명"].strip()
        emd, ri, jibun = split_addr(addr)
        notes = []
        if addr_n[addr] > 1:
            notes.append(f"같은 주소에 사업장 {addr_n[addr]}곳")
        if len(name_addrs[name]) > 1:
            notes.append(f"같은 이름이 주소 {len(name_addrs[name])}곳")

        lat = lon = None
        precision = ""
        if VWORLD_KEY:
            key = "vworld:" + addr
            if key not in cache:
                cache[key] = vworld(addr)
            if cache[key]:
                lat, lon = cache[key]
                precision = "지번"
        if lat is None and emd and ri:
            key = f"nominatim:{emd} {ri}"
            if key not in cache:
                cache[key] = nominatim(f"제주특별자치도 {emd} {ri}")
            if cache[key]:
                lat, lon = cache[key]
                precision = "리 중심(근사)"
        out.append({
            "fid": f"H{i:02d}", "구분": r["구분"].strip(), "사업장명": name, "주소": addr,
            "읍면": emd or "", "리": ri or "", "부지면적": r["부지면적(제곱미터)"].strip(),
            "데이터기준일자": r["데이터기준일자"].strip(),
            "lat": f"{lat:.6f}" if lat is not None else "", "lon": f"{lon:.6f}" if lon is not None else "",
            "precision": precision, "중복의심": " / ".join(notes)})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")

    miss = [o["주소"] for o in out if not o["lat"]]
    print(f"{len(out)}곳 처리 · 좌표 {len(out) - len(miss)}곳 ({'브이월드 지번' if VWORLD_KEY else '리 중심 근사'}) · "
          f"중복 의심 {sum(1 for o in out if o['중복의심'])}곳 · 좌표 못 찾음 {len(miss)}곳")
    for m in miss:
        print("  좌표 없음:", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
