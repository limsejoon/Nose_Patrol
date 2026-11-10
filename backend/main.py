"""냄새알림 서버. 실행: run.bat (또는 python -m uvicorn backend.main:app --port 8000)
브라우저: http://127.0.0.1:8000"""
import json
from datetime import timedelta
from fastapi import FastAPI, HTTPException
import httpx
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend import config, data
from backend.agent import analyst, engine, llm
from backend.tools import history, report_stats, sim_history

app = FastAPI(title="냄새알림")


class Ask(BaseModel):
    question: str
    history: list[dict] | None = None   # 이어 묻기: [{"q": ..., "a": ...}]


class Msg(BaseModel):
    user: str
    text: str
    place_village: str | None = None   # [현재 위치 보내기]로 받은 마을


class FarmResp(BaseModel):
    farm_id: str
    alert_id: int
    response: str


@app.get("/api/health")
def health():
    on = llm.available()
    return {"ok": True, "llm": f"Claude ({llm.model()})" if on else "규칙 기반(LLM 미설정)",
            "llm_model": llm.model() if on else None}


@app.post("/api/message")
def message(m: Msg):
    return engine.handle_message(m.user, m.text, m.place_village)


@app.get("/api/state")
def state():
    return engine.snapshot()


@app.post("/api/farm/respond")
def farm_respond(r: FarmResp):
    a = engine.farm_respond(r.farm_id, r.alert_id, r.response)
    if not a:
        raise HTTPException(404, "알림을 찾을 수 없음")
    return a


@app.post("/api/complaint/{action_id}/approve")
def approve(action_id: int):
    a = engine.approve_complaint(action_id)
    if not a:
        raise HTTPException(404, "민원서를 찾을 수 없음")
    return a


@app.get("/api/stats/overview")
def stats():
    return history.overview()


# ---- 지도 ----
VWORLD_LAYERS = {"white": "png", "Base": "png", "Satellite": "jpeg", "Hybrid": "png"}


@app.get("/api/mapconfig")
def mapconfig():
    return {"vworld": bool(config.VWORLD_API_KEY),
            "layers": list(VWORLD_LAYERS) if config.VWORLD_API_KEY else []}


@app.get("/tiles/{layer}/{z}/{y}/{x}")
def tile(layer: str, z: int, y: int, x: int):
    """브이월드 배경지도 타일을 대신 받아 준다. 키를 화면에 노출하지 않고, 한 번 본 타일은 PC에 저장해
    다음부터 인터넷 없이 보인다."""
    ext = VWORLD_LAYERS.get(layer)
    if not ext or not config.VWORLD_API_KEY or not (0 <= z <= 19):
        raise HTTPException(404)
    path = config.TILE_CACHE / layer / str(z) / str(y) / f"{x}.{ext}"
    media = "image/jpeg" if ext == "jpeg" else "image/png"
    if not path.exists():
        try:
            r = httpx.get(f"https://api.vworld.kr/req/wmts/1.0.0/{config.VWORLD_API_KEY}/{layer}/{z}/{y}/{x}.{ext}",
                          timeout=10, headers={"User-Agent": "nose-patrol/0.1"})
        except httpx.HTTPError:
            raise HTTPException(504, "브이월드 연결 실패")
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            raise HTTPException(404)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return Response(path.read_bytes(), media_type=media, headers={"Cache-Control": "public, max-age=604800"})


@app.get("/api/boundaries")
def boundaries():
    """리·동 경계 (OpenStreetMap, scripts/prepare_boundaries.py 로 만든다)."""
    p = config.DATA_PROCESSED / "boundaries.geojson"
    if not p.exists():
        return {"type": "FeatureCollection", "features": []}
    return Response(p.read_bytes(), media_type="application/geo+json")


@app.get("/api/facilities")
def facilities():
    """악취배출시설(제주데이터허브 필수 데이터)을 지도에 올린다. 같은 자리(같은 좌표)는 하나로 묶는다."""
    groups = {}
    for f in data.facilities():
        key = (round(float(f["lat"]), 5), round(float(f["lon"]), 5))
        g = groups.setdefault(key, {"emd": f["읍면"], "ri": f["리"], "lat": float(f["lat"]), "lon": float(f["lon"]),
                                    "precision": f["precision"], "count": 0, "in_area": 0, "area_m2": 0.0,
                                    "dup": 0, "items": []})
        g["count"] += 1
        g["in_area"] += f["구분"] == "악취관리지역"
        g["area_m2"] += float(f["부지면적"] or 0)
        g["dup"] += bool(f["중복의심"])
        item = {"구분": f["구분"], "부지면적": f["부지면적"], "중복의심": f["중복의심"]}
        if config.FACILITY_SHOW_NAMES:
            item["사업장명"] = f["사업장명"]
            item["주소"] = f["주소"]
        g["items"].append(item)
    return {"source": "제주데이터허브 「제주특별자치도_악취배출시설현황」(2019.7.19 기준)",
            "show_names": config.FACILITY_SHOW_NAMES, "total": sum(g["count"] for g in groups.values()),
            "groups": list(groups.values())}


@app.post("/api/ask")
def ask(a: Ask):
    """말로 묻는 분석 (F4): Claude가 통계 도구를 골라 부르고, 도구가 계산한 숫자로 답한다."""
    q = (a.question or "").strip()[:500]
    if not q:
        raise HTTPException(400, "질문이 비어 있습니다")
    return analyst.ask(engine.S, q, a.history)


@app.get("/api/stats/reports")
def report_stats_api(days: int = 14, village: str | None = None, since: str | None = None):
    """지역·시간별 신고와 처리 경과. days=0 이면 전체 기간. since=YYYY-MM-DD 를 주면 그날 0시부터."""
    return report_stats.build(engine.S, days or None, village or None, since)


# ---- 시연용 ----
@app.post("/api/demo/reset")
def demo_reset():
    engine.S.reset()
    return {"ok": True}


@app.post("/api/demo/play")
def demo_play(name: str = "gwangryeong_morning"):
    p = config.DATA_DEMO / f"{name}.json"
    steps = json.loads(p.read_text(encoding="utf-8"))
    log = []
    engine.S.rule_only = True   # 정해진 시연 대본은 규칙으로 빠르게 (카톡 시뮬레이터 직접 입력은 LLM 해석)
    try:
        for s in steps:
            if s.get("advance_min"):
                engine.S.clock_offset += timedelta(minutes=s["advance_min"])
                continue
            r = engine.handle_message(s["user"], s["text"], s.get("place_village"))
            log.append({"user": s["user"], "text": s["text"], "reply": r["reply"]})
    finally:
        engine.S.rule_only = False
    return {"played": len(log), "log": log}


@app.post("/api/demo/history")
def demo_history(days: int = 30):
    """가상 신고 기록(지난 days일)을 엔진에 넣는다. 통계 화면 시연용. 기존 기록은 지운다."""
    engine.S.reset()
    return sim_history.generate(engine.S, engine.handle_message, engine.farm_respond,
                                engine.approve_complaint, days=days)


@app.post("/api/demo/advance")
def demo_advance(minutes: int = 180):
    engine.S.clock_offset += timedelta(minutes=minutes)
    return {"now": engine.S.now().isoformat(timespec="seconds")}


@app.get("/")
def root():
    return RedirectResponse("/index.html")


app.mount("/", StaticFiles(directory=config.ROOT / "frontend", html=True), name="frontend")
