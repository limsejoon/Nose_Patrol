"""냄새알림 서버. 실행: run.bat (또는 python -m uvicorn backend.main:app --port 8000)
브라우저: http://127.0.0.1:8000"""
import json
from datetime import timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend import config, data
from backend.agent import engine, llm
from backend.tools import history, report_stats, sim_history

app = FastAPI(title="냄새알림")


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
    return {"ok": True, "llm": config.LLM_PROVIDER if llm.available() else "규칙 기반(LLM 미설정)"}


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


@app.get("/api/stats/reports")
def report_stats_api(days: int = 14, village: str | None = None):
    """지역·시간별 신고와 처리 경과. days=0 이면 전체 기간."""
    return report_stats.build(engine.S, days or None, village or None)


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
    for s in steps:
        if s.get("advance_min"):
            engine.S.clock_offset += timedelta(minutes=s["advance_min"])
            continue
        r = engine.handle_message(s["user"], s["text"], s.get("place_village"))
        log.append({"user": s["user"], "text": s["text"], "reply": r["reply"]})
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
