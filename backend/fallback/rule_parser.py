"""LLM이 없거나 막혔을 때 쓰는 규칙 기반 신고 해석기. 시연이 멈추지 않게 하는 백업."""
import re

STRONG = ["죽겠", "토할", "숨을 못", "숨 못", "최악", "미치겠", "장난 아", "진짜 심", "너무 심", "엄청", "깼", "못 자", "못자"]
MID = ["심하", "심해", "심함", "창문", "못 열", "역하", "독하", "지독"]
WEAK = ["좀 나", "약간", "살짝", "조금", "희미"]
PLACES = {"무수천": "광령3리", "광령초": "광령2리", "광령초등학교": "광령2리"}


def intensity(text: str) -> int:
    if any(k in text for k in STRONG):
        return 5 if ("죽겠" in text or "토할" in text or "숨" in text) else 4
    if any(k in text for k in MID):
        return 3 if "창문" in text or "못 열" in text else 4
    if any(k in text for k in WEAK):
        return 2
    if "냄새" in text or "악취" in text:
        return 3
    return 0


def time_expr(text: str):
    # "3시간째"·"2시간 동안"처럼 시간 길이는 시각이 아니다 → "시" 뒤에 "간"이 오면 건너뛴다
    m = re.search(r"(새벽|아침|오전|낮|오후|저녁|밤)?\s*(\d{1,2})\s*시(?!간)", text)
    if m:
        h = int(m.group(2))
        part = m.group(1) or ""
        if part in ("오후", "저녁", "밤") and h < 12:
            h += 12
        return f"{h:02d}시"
    for k in ["새벽", "아침", "오전", "점심", "오후", "저녁", "밤"]:
        if k in text:
            return k + ("부터" if "부터" in text else "")
    return "지금"


def odor_type(text: str):
    if any(k in text for k in ["돼지", "축사", "똥", "분뇨", "양돈", "거름"]):
        return "축산"
    return None


def place(text: str, villages):
    for v in villages:
        for a in [v["village"]] + v["aliases"]:
            if a.replace(" ", "") in text.replace(" ", ""):
                return v["village"], None
    for p, v in PLACES.items():
        if p in text:
            return v, p
    return None, None


def parse(text: str, villages) -> dict:
    v, p = place(text, villages)
    return {"is_report": intensity(text) > 0, "intensity": intensity(text),
            "time": time_expr(text), "odor": odor_type(text),
            "village": v, "place": p, "parser": "rule"}
