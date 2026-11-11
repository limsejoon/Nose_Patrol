"""말로 묻는 분석 Agent 질문 평가 (Claude API 키 필요, 질문 1건 약 20원).

각 질문마다 기대 도구, 답에 꼭 있어야 할 값, 있으면 안 되는 말을 정해 두고 자동 채점한다.
결과는 docs/6_질문_평가_결과.md 에 표로 저장한다.

실행: .venv\\Scripts\\python scripts\\eval_questions.py
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import config, data  # noqa: E402
from backend.agent import analyst, engine, llm  # noqa: E402
from backend.tools import sim_history  # noqa: E402

S = engine.S
S.reset()
sim_history.generate(S, engine.handle_message, engine.farm_respond, engine.approve_complaint)

# 시연 신고 질문의 정답은 같은 도구를 직접 불러 구한다(가상 기록은 실행 날짜에 따라 달라짐)
q11 = analyst.t_report_stats(S, "month", "광령2리", 8, 11)["reports_in_hour_range"]
q13 = analyst.t_incident_list(S, "all", None, 2)["count_matching"]
FARMS = [f["name"] for f in data.farms()] + ["피그랜드", "성신", "백록"]
num = lambda n: rf"{n:,}|{n}"  # 1,778 / 1778 둘 다

CASES = [
    # (질문, 기대 도구, 꼭 있어야 할 정규식 목록, 있으면 안 되는 정규식 목록, 분류)
    ("실제 민원은 어느 접수 시간대에 몰려?", "complaint_history", [r"20\s*시", num(257)], [], "실제 민원"),
    ("민원이 정기 측정 시간 밖에 얼마나 접수됐어? 해마다 그 해 시간표로도 비교해 줘", "coverage_compare",
     [r"67\.8", r"54\.3", num(1761)], [], "비교"),
    ("민원 있는 날과 정기 측정일이 겹친 날은 며칠이야?", "coverage_compare", [r"9\s*일"], [], "비교"),
    ("점검 기록에서 포집 시도와 포집 후 분석 의뢰를 나눠 줘", "inspection_history", [r"25|13", r"174|50"],
     [r"검사 완료"], "점검"),
    ("2023년 이후 행정처분은 몇 건이야?", "inspection_history", [r"1\s*(건|사례|개)"], [r"4\s*건이\s*있"], "점검"),
    ("2024년 실제 민원은 몇 건이야?", "complaint_history", [num(731)], [], "실제 민원"),
    ("민원 접수 방법은 뭐가 제일 많아?", "complaint_history", [r"당직", num(1367)], [], "실제 민원"),
    ("2023년부터 실측 기준 초과율이 어떻게 변했어?", "measurement_stats", [r"23\.4", r"25(\.0)?\s*%", r"10"], [r"15배\s*기준"], "실측"),
    ("악취관리지역 시설이 가장 많은 읍면은?", "facility_stats", [r"한림", r"29"], [r"전체\s*58\s*곳\s*중\s*29"], "지정 데이터"),
    ("악취관리지역 안에 있는 시설은 전체 몇 곳이야?", "facility_stats", [r"46"], [], "지정 데이터"),
    ("이번 달 광령2리 오전 신고 몇 건이야?", "report_stats", [rf"{q11}\s*건", r"가상"], [], "시연 신고"),
    ("최근 30일 신고가 가장 많이 몰린 시간대는?", "hourly_daily", [r"가상"], [], "시연 신고"),
    ("경보까지 간 사건은 몇 건이야?", "incident_list|report_stats", [rf"{q13}\s*건", r"가상"], [], "시연 신고"),
    ("피그랜드 농장이 냄새 원인이야?", "", [r"단정|지목|알 수 없|정할 수 없|확인할 수 없|추정하지"], [r"원인입니다|원인이 맞"], "원칙"),
    ("내일 광령리에 냄새 날까?", "", [r"예측|답할 수 없|알 수 없|없습니다"], [r"냄새가 날 것입니다|확률\s*\d"], "도구 밖"),
]


def run():
    if not llm.available():
        sys.exit("Claude API 키가 없습니다 (.env 의 ANTHROPIC_API_KEY).")
    rows, t_all = [], time.time()
    for q, tool, must, mustnot, kind in CASES:
        r = analyst.ask(S, q)
        ans = r["answer"]
        used = [s["tool"] for s in r["steps"]]
        ok_tool = (not tool and True) or any(re.fullmatch(tool, u) for u in used)
        miss = [p for p in must if not re.search(p, ans)]
        bad = [p for p in mustnot if re.search(p, ans)]
        named = [n for n in FARMS if n in ans and n not in q]
        ok = ok_tool and not miss and not bad and not named and r.get("ok")
        rows.append({"q": q, "kind": kind, "expect_tool": tool or "(없음/아무거나)", "used": used, "ok": bool(ok),
                     "why": "; ".join(filter(None, ["도구 다름" if not ok_tool else "", f"빠짐 {miss}" if miss else "",
                                                     f"금지어 {bad}" if bad else "", f"이름 {named}" if named else ""])),
                     "sec": r.get("seconds"), "usage": r.get("usage"), "answer": ans})
        print(("✅" if ok else "❌"), q, used, r.get("seconds"), "초", flush=True)
    return rows, round(time.time() - t_all)


def save(rows, total_sec):
    n_ok = sum(r["ok"] for r in rows)
    tin = sum((r["usage"] or {}).get("input", 0) for r in rows)
    tout = sum((r["usage"] or {}).get("output", 0) for r in rows)
    won = (tin * 2 + tout * 10) / 1e6 * 1400 if "sonnet" in llm.model() else None
    secs = [r["sec"] for r in rows if r["sec"]]
    lines = [
        "# 말로 묻는 분석 질문 평가 결과", "",
        f"- 실행: {time.strftime('%Y-%m-%d %H:%M')} · 모델 `{llm.model()}` · `scripts/eval_questions.py`",
        f"- 결과: **{n_ok}/{len(rows)} 통과** · 평균 {sum(secs) / len(secs):.1f}초 · 전체 {total_sec}초"
        + (f" · 토큰 입력 {tin:,} / 출력 {tout:,} (약 {won:.0f}원)" if won else ""),
        "- 채점: ① 기대 도구를 불렀는지 ② 답에 정답 값(원자료 검산값)이 있는지 ③ 금지 표현(범위 오설명, 원인 단정, 15배를 기준으로 부름 등)이 없는지 "
        "④ 질문에 없던 농장·사업장 이름이 없는지. 시연 신고 질문은 '가상' 표시도 확인.",
        "- 시연 신고 질문의 정답은 같은 날 만든 가상 한 달 기록에서 도구로 직접 구한 값.", "",
        "| # | 분류 | 질문 | 기대 도구 | 부른 도구 | 결과 | 시간 |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['kind']} | {r['q']} | {r['expect_tool']} | {', '.join(r['used']) or '-'} | "
                     f"{'통과' if r['ok'] else '실패: ' + r['why']} | {r['sec']}초 |")
    lines += ["", "## 답 원문", ""]
    for i, r in enumerate(rows, 1):
        lines += [f"### {i}. {r['q']}", "", r["answer"], ""]
    out = ROOT / "docs" / "6_질문_평가_결과.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "data" / "processed" / "eval_last.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{n_ok}/{len(rows)} 통과 → {out}")
    return n_ok == len(rows)


if __name__ == "__main__":
    rows, sec = run()
    S.reset()
    sys.exit(0 if save(rows, sec) else 1)
