"""정보공개청구 PDF 4개 → 집계용 CSV (data/processed/admin_*.csv).

원본 PDF는 저장소에 넣지 않는다. 처리내용 원문(농장 이름이 섞여 있음)도 옮기지 않고
날짜·접수시각·접수방법·처리 종류(분류)·원본 쪽만 남긴다. 개인 식별 정보는 원본에도 없다.

실행: .venv\\Scripts\\python scripts\\prepare_admin_records.py "PDF가 있는 폴더"

정규화 규칙 (결과 설명자료에도 적음)
- 한 칸에 접수시각이 여러 개면 시각마다 1건으로 편다 (민원 건수 = 접수시각 수).
- "1700" → 17:00, "21;36" → 21:36. "-" 는 시각 미상(건수엔 포함, 시간대 분석 제외).
- "24:14" 처럼 있을 수 없는 시각은 원문을 남기고 invalid (건수·시간대 모두 제외 → 1,778건).
- 한 행에 날짜가 두 개면("9/3 9/4", "2026-06-03 2026-06-04") 시각과 순서대로 짝짓는다. 연도가 없으면 앞 행의 연도.
"""
import csv
import re
import sys
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\b")
MD2 = re.compile(r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2})/(\d{1,2})\b")
TIME = re.compile(r"^(\d{1,2})[:;](\d{2})$")
HHMM = re.compile(r"^(\d{2})(\d{2})$")
SKIP = ("===", "접수일시", "애월읍 광령리 축산", "(2023년", "점검일시", "광령리 및 고성리")


def pages(path):
    for i, p in enumerate(pypdf.PdfReader(str(path)).pages, 1):
        for line in (p.extract_text() or "").splitlines():
            yield i, line.strip()


def find(folder, key):
    hits = [p for p in Path(folder).glob("*.pdf") if key in p.name]
    if not hits:
        sys.exit(f"PDF를 찾지 못했습니다: *{key}*.pdf")
    return hits[0]


# ---------------------------------------------------------------- 민원 접수
def complaints(path):
    recs, cur = [], None
    for pg, line in pages(path):
        if not line or line.startswith(SKIP):
            continue
        if DATE.match(line) or MD2.match(line):
            cur = {"page": pg, "text": line}
            recs.append(cur)
        elif cur:
            cur["text"] += " " + line
    rows, year = [], None
    for r in recs:
        toks = r["text"].split()
        m = DATE.match(r["text"])
        if m:
            year = m.group(1)
            dates, toks, inferred = [f"{m.group(1)}-{m.group(2)}-{m.group(3)}"], toks[1:], False
            while toks and DATE.match(toks[0]):          # "2026-06-03 2026-06-04 23:16 00:04"
                dates.append(toks.pop(0))
        else:
            m = MD2.match(r["text"])
            dates = [f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}",
                     f"{year}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"]
            toks, inferred = toks[2:], True
        times = []
        while toks and not toks[0].startswith("광령") and not toks[0].startswith("고성"):
            times.append(toks.pop(0))
        rest = " ".join(toks)
        head = rest.replace(" ", "")[:30]
        method = ("인터넷(국민신문고)" if "국민신문고" in rest or "인터넷" in head else
                  "도청 전달" if "도청" in head and "당직" not in head else
                  "당직민원" if "당직민원" in head else
                  "전화" if "전화" in head else
                  "진정(다수인)" if "진정" in head else "기타")
        acts = {"act_spray": "방제" in rest,
                "act_reduce": "저감" in rest or "농장주" in rest or "농가" in rest,
                "act_sms": "문자" in rest,
                "act_site": "현장" in rest or "점검" in rest,
                "act_reply": "답변" in rest or "통화" in rest}
        for k, t in enumerate(times or ["-"]):
            d = dates[min(k, len(dates) - 1)]
            mt, mh = TIME.match(t), HHMM.match(t)
            if t == "-":
                hhmm, status = "", "missing"
            elif mt or mh:
                h, mi = (int(x) for x in (mt or mh).groups())
                hhmm, status = (f"{h:02d}:{mi:02d}", "ok") if h < 24 and mi < 60 else ("", "invalid")
            else:
                hhmm, status = "", "invalid"
            rows.append({"date": d, "time": hhmm, "time_raw": t, "time_status": status, "method": method,
                         **{k2: int(v) for k2, v in acts.items()},
                         "date_inferred": int(inferred), "page": r["page"]})
    return rows


# ---------------------------------------------------------------- 지도점검
def inspection_kind(t):
    if re.search(r"포집\s*(후|및)\s*(분석|시료)|분석\s*의뢰|포집\s*실시", t):
        return "포집·분석 의뢰"
    if "포집 시도" in t:
        return "포집 시도"
    if re.search(r"포집.{0,10}(예정|안내)", t):
        return "포집 예정·안내"
    if "시료채취" in t:
        return "분뇨 시료채취"
    if "철거" in t or "폐쇄" in t:
        return "시설 철거·폐쇄 확인"
    if "민원" in t or "현장" in t:
        return "민원 현장확인"
    if "합동" in t:
        return "합동 지도점검"
    return "기타 점검"


def inspections(path):
    recs, cur = [], None
    for pg, line in pages(path):
        if not line or line.startswith(SKIP):
            continue
        m = DATE.match(line)
        if m:
            cur = {"date": m.group(0), "page": pg, "text": line[10:]}
            recs.append(cur)
        elif cur:
            cur["text"] += " " + line
    return [{"date": r["date"], "kind": inspection_kind(r["text"]), "night": int("야간" in r["text"]),
             "page": r["page"]} for r in recs]


# ---------------------------------------------------------------- 행정처분 (이름 없이)
def admin_actions(path):
    text = " ".join(l for _, l in pages(path))
    out = []
    for k, chunk in enumerate(re.split(r"\s(?=\d\s+가축분뇨)", text)[1:], 1):
        ds = re.findall(r"\d{4}-\d{2}-\d{2}", chunk)
        out.append({"case": k, "inspect_date": ds[0], "action_date": ds[1] if len(ds) > 1 else "",
                    "violation": "악취배출허용기준 초과" if "악취배출허용기준" in chunk else "기타",
                    "actions": "|".join(a for a in ("개선명령", "과태료") if a in chunk)})
    return out


# ---------------------------------------------------------------- 액비살포
def manure(path):
    out = []
    for pg, line in pages(path):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\S+)\s+([\d.]+)$", line)
        if m:
            out.append({"date": m.group(1), "place": m.group(2), "tons": float(m.group(3))})
    return out


def write(name, rows):
    with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"  {name}: {len(rows)}행")


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else str(Path.home() / "Downloads")
    c = complaints(find(folder, "민원접수"))
    write("admin_complaints.csv", c)
    st = {s: sum(r["time_status"] == s for r in c) for s in ("ok", "missing", "invalid")}
    print(f"    접수시각 기록 {len(c)}, 유효 {st['ok']}, 미상 {st['missing']}, 오류 {st['invalid']}"
          f" → 민원 건수(오류 제외) {len(c) - st['invalid']}")
    write("admin_inspections.csv", inspections(find(folder, "지도점검")))
    write("admin_actions.csv", admin_actions(find(folder, "행정처분")))
    write("admin_manure.csv", manure(find(folder, "액비살포")))


if __name__ == "__main__":
    main()
