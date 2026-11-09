"""geocode_place, get_wind, rank_sources: 위치와 풍향으로 주의 알림을 보낼 바람 위쪽 농장을 고른다.
결과는 항상 '추정'이다. 특정 농장을 원인으로 단정하지 않는다.
명예훼손 위험 때문에 결과에는 농장 이름을 넣지 않는다. 방향·거리 라벨만 내보내고,
농장 알림 전달에 필요한 farm_id 는 내부용으로만 쓴다."""
import math
from backend import config, data
from backend.fallback.rule_parser import PLACES

DIR_NAMES = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]


def geocode_place(name: str):
    v = data.village(name) or data.village(PLACES.get(name, ""))
    return (v["lat"], v["lon"]) if v else None


def get_wind(ts=None) -> dict:
    """TODO: KMA_API_KEY가 있으면 기상청 초단기실황 조회. 지금은 기본값(또는 data/raw/wind.csv)."""
    deg = config.DEFAULT_WIND_FROM_DEG
    name = DIR_NAMES[int((deg + 22.5) % 360 // 45)] + "풍"
    return {"from_deg": deg, "speed": config.DEFAULT_WIND_SPEED, "label": name,
            "source": "기본값(기상청 API 미연결)" if not config.KMA_API_KEY else "기상청"}


def _bearing(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1)))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _dist_km(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def rank_sources(lat, lon, wind: dict, max_km=5.0):
    """신고 지점에서 바람이 불어오는 쪽(바람 위쪽)에 있고 가까운 농장일수록 점수가 높다."""
    out = []
    for f in data.farms():
        if f["lat"] is None:
            continue  # 위치 미확인 농장
        d = _dist_km(lat, lon, f["lat"], f["lon"])
        if d > max_km:
            continue
        b = _bearing(lat, lon, f["lat"], f["lon"])          # 신고 지점 → 농장 방향
        diff = abs((b - wind["from_deg"] + 180) % 360 - 180)  # 바람이 불어오는 방향과의 차이
        upwind = max(0.0, math.cos(math.radians(diff)))
        score = upwind / (0.3 + d)
        if score > 0:
            direction = DIR_NAMES[int((b + 22.5) % 360 // 45)]
            out.append({"farm_id": f["farm_id"], "direction": direction, "dist_km": round(d, 2),
                        "label": f"{direction}쪽 {d:.1f}km 축산시설",
                        "angle_diff": round(diff), "score": score})
    total = sum(x["score"] for x in out) or 1
    for x in out:
        x["share"] = round(100 * x["score"] / total)
        del x["score"]
    return sorted(out, key=lambda x: -x["share"])
