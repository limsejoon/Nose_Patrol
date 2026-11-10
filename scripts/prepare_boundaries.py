"""광령리 주변 리·동 경계 만들기 (지도에 마을 범위 표시용).
OpenStreetMap(Overpass API)의 행정경계를 받아 data/processed/boundaries.geojson 으로 저장한다.
한 번 만들어 두면 센터 PC는 인터넷 없이 경계를 그린다.

- 애월읍의 리 경계(admin_level=10) 중 광령리 주변
- 동쪽 이웃 동(admin_level=8): 노형동·외도동·오라동
방식은 jeju-map-demo 의 build-data.mjs 와 같다: 관계(relation)의 길(way) 조각을 이어 닫힌 고리로 만든다.

실행: python scripts/prepare_boundaries.py
출처 표기: © OpenStreetMap contributors (ODbL)
"""
import json
import math
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed" / "boundaries.geojson"
UA = "nose-patrol/0.1 (odor-report demo)"

# 지도에 그릴 구역. focus=True 는 강조(시범 지역)
NAMES = {
    "광령리": True, "고성리": False, "유수암리": False, "상귀리": False, "하귀1리": False,
    "하귀2리": False, "소길리": False, "장전리": False, "노형동": False, "외도동": False, "오라동": False,
}
QUERY = """[out:json][timeout:120];
rel(33.38,126.36,33.52,126.50)["boundary"="administrative"]["admin_level"~"^(8|10)$"];
out geom;"""

LAT0, LON0 = 33.38, 126.55
KM_LAT, KM_LON = 110.574, 111.320 * math.cos(math.radians(LAT0))


def assemble_rings(members):
    """길 조각을 끝점끼리 이어 닫힌 고리 목록으로."""
    key = lambda p: (round(p["lat"], 7), round(p["lon"], 7))
    ways = [m["geometry"] for m in members if m.get("type") == "way" and m.get("geometry") and m.get("role") != "inner"]
    rings = []
    while ways:
        ring = list(ways.pop(0))
        grew = True
        while key(ring[0]) != key(ring[-1]) and grew:
            grew = False
            for i, w in enumerate(ways):
                if key(w[0]) == key(ring[-1]):
                    ring += w[1:]
                elif key(w[-1]) == key(ring[-1]):
                    ring += list(reversed(w[:-1]))
                else:
                    continue
                ways.pop(i)
                grew = True
                break
        if len(ring) >= 4:
            rings.append([[round(p["lon"], 6), round(p["lat"], 6)] for p in ring])
    return rings


def area_km2(ring):
    pts = [((lon - LON0) * KM_LON, (lat - LAT0) * KM_LAT) for lon, lat in ring]
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def inside(ring, lon, lat):
    c = False
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        if (y0 > lat) != (y1 > lat) and lon < (x1 - x0) * (lat - y0) / (y1 - y0) + x0:
            c = not c
    return c


def label_point(ring):
    """구역 안쪽에 있는 이름표 자리: 무게중심이 안쪽이면 그대로, 아니면 격자에서 중심에 가장 가까운 안쪽 점."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    if inside(ring, cx, cy):
        return [round(cx, 6), round(cy, 6)]
    best = None
    for i in range(40):
        for j in range(40):
            x = min(xs) + (max(xs) - min(xs)) * (i + 0.5) / 40
            y = min(ys) + (max(ys) - min(ys)) * (j + 0.5) / 40
            if inside(ring, x, y):
                d = (x - cx) ** 2 + (y - cy) ** 2
                if best is None or d < best[0]:
                    best = (d, x, y)
    return [round(best[1], 6), round(best[2], 6)] if best else [round(cx, 6), round(cy, 6)]


def main():
    elements = None
    for url in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                "https://overpass-api.de/api/interpreter"]:   # 공용 서버가 바쁠 때가 있어 예비 서버·재시도
        try:
            r = httpx.post(url, data={"data": QUERY}, headers={"User-Agent": UA}, timeout=180)
            r.raise_for_status()
            elements = r.json()["elements"]
            break
        except (httpx.HTTPError, ValueError) as e:
            print("  재시도:", url, e)
            time.sleep(5)
    if elements is None:
        print("경계를 받지 못했습니다. 잠시 뒤 다시 실행하세요.")
        return 1
    feats = []
    for el in elements:
        name = el["tags"].get("name")
        if name not in NAMES:
            continue
        rings = assemble_rings(el.get("members", []))
        if not rings:
            print("  경계 조각을 잇지 못함:", name)
            continue
        main_ring = max(rings, key=area_km2)
        feats.append({
            "type": "Feature",
            "properties": {
                "name": name, "focus": NAMES[name], "admin_level": el["tags"].get("admin_level"),
                "osm": f"relation/{el['id']}", "area_km2": round(sum(area_km2(rg) for rg in rings), 2),
                "label": label_point(main_ring),
            },
            "geometry": {"type": "MultiPolygon", "coordinates": [[rg] for rg in rings]},
        })
    feats.sort(key=lambda f: (not f["properties"]["focus"], f["properties"]["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "features": feats,
    }, ensure_ascii=False), encoding="utf-8")
    for f in feats:
        p = f["properties"]
        print(f"{p['name']}: {p['area_km2']} km² {'(강조)' if p['focus'] else ''}")
    missing = set(NAMES) - {f["properties"]["name"] for f in feats}
    if missing:
        print("못 찾음:", ", ".join(sorted(missing)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
