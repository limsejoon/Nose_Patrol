"""parse_report: 주민 문장 → 위치·시각·강도·종류. LLM 우선, 실패하면 규칙 기반."""
from backend import data
from backend.agent import llm
from backend.fallback import rule_parser

SYSTEM = """너는 악취 신고 해석기다. 주민이 카톡에 쓴 문장에서 값을 뽑아 JSON 하나만 출력한다.
키: is_report(악취 신고면 true), intensity(1~5, 1=희미 3=분명 4=심함 5=견디기 힘듦, 신고 아니면 0),
time(문장에 나온 시각 표현, 없으면 "지금"), odor("축산" 또는 null),
village(아래 목록 중 하나 또는 null), place(목록에 없는 지명이 나오면 그 지명, 없으면 null).
마을 목록: {villages}
숫자는 문장에서 근거를 찾을 수 있을 때만 쓴다. 추측하지 말고 모르면 null."""


def parse(text: str) -> dict:
    vs = data.villages()
    names = ", ".join(v["village"] for v in vs)
    out = llm.ask(SYSTEM.format(villages=names), text, want_json=True)
    if isinstance(out, dict) and "intensity" in out:
        out["parser"] = "llm"
        try:
            out["intensity"] = max(0, min(5, int(out.get("intensity") or 0)))
        except (TypeError, ValueError):
            out["intensity"] = 0
        # LLM이 지명만 준 경우 규칙 사전으로 마을 보완
        if not out.get("village"):
            v, p = rule_parser.place(text, vs)
            out["village"] = v
            out["place"] = out.get("place") or p
        return out
    return rule_parser.parse(text, vs)
