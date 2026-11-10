"""대회 제출물 만들기.
  dist/애월주민_냄새알림_기획서.pdf        ← docs/냄새알림_기획서.html 을 Edge로 PDF 변환 (15쪽)
  dist/애월주민_냄새알림_최종결과물.zip    ← 실행 코드 + 매뉴얼·명세·결과 설명 (키·가상환경·캐시 제외)

평가용 Claude 키를 넣으려면 프로젝트 폴더에 `평가용_키.txt` (한 줄: sk-ant-...)를 만든 뒤 실행한다.
그러면 ZIP 안의 `.env` 와 설치 매뉴얼 7절에 그 키가 들어간다(대회 규칙: 평가용 AI 키는 ZIP 매뉴얼에 포함 가능).
이 파일과 dist/ 는 git 에 올라가지 않는다.

실행: .venv\\Scripts\\python scripts\\make_submission.py
"""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TEAM = "애월주민"
EXCLUDE_PREFIX = (".git/", ".venv/", "dist/", "data/processed/tiles/")
EXCLUDE_NAME = {".env", "평가용_키.txt"}


def tracked_files():
    out = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "-co", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    files = []
    for line in out.splitlines():
        p = line.strip()
        if not p or p.startswith(EXCLUDE_PREFIX) or Path(p).name in EXCLUDE_NAME or "__pycache__" in p:
            continue
        if (ROOT / p).is_file():
            files.append(p)
    return sorted(files)


def make_pdf():
    edge = None
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and Path(base, "Microsoft/Edge/Application/msedge.exe").exists():
            edge = Path(base, "Microsoft/Edge/Application/msedge.exe")
            break
    if not edge:
        print("  Edge가 없어 PDF를 만들지 못했습니다. docs/냄새알림_기획서.html 을 브라우저로 열어 Ctrl+P → PDF로 저장하세요.")
        return None
    import shutil
    import time
    src = (ROOT / "docs" / "냄새알림_기획서.html").resolve().as_uri()
    out = DIST / f"{TEAM}_냄새알림_기획서.pdf"
    tmp = DIST / "_proposal.pdf"      # Edge가 한글 경로를 다루지 못할 때를 피해 영문 이름으로 먼저 쓴다
    prof = DIST / "_edge_profile"
    for f in (out, tmp):
        f.unlink(missing_ok=True)
    subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                    "--virtual-time-budget=8000", f"--print-to-pdf={tmp}", src], timeout=120)
    for _ in range(90):               # Edge는 창을 띄우고 바로 끝나므로 파일이 생길 때까지 기다린다
        if tmp.exists() and tmp.stat().st_size > 0:
            time.sleep(1)
            break
        time.sleep(1)
    if not tmp.exists():
        print("  PDF를 만들지 못했습니다. docs/냄새알림_기획서.html 을 브라우저로 열어 Ctrl+P → PDF로 저장하세요.")
        return None
    tmp.replace(out)
    shutil.rmtree(prof, ignore_errors=True)
    try:
        from pypdf import PdfReader
        print(f"  PDF {len(PdfReader(str(out)).pages)}쪽")
    except ImportError:
        pass
    return out


def main():
    DIST.mkdir(exist_ok=True)
    print("1) 기획서 PDF")
    make_pdf()

    print("2) 최종 결과물 ZIP")
    key_file = ROOT / "평가용_키.txt"
    key = key_file.read_text(encoding="utf-8-sig").strip() if key_file.exists() else ""   # 메모장 BOM 제거
    files = tracked_files()
    out = DIST / f"{TEAM}_냄새알림_최종결과물.zip"
    top = "냄새알림"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            data = (ROOT / f).read_bytes()
            if key and f == "docs/1_설치_실행_매뉴얼.md":
                data = data.decode("utf-8").replace("ANTHROPIC_API_KEY=(제출 직전에 기입)", f"ANTHROPIC_API_KEY={key}").encode("utf-8")
            z.writestr(f"{top}/{f}", data)
        if key:   # 심사위원이 바로 실행할 수 있게 .env 도 넣는다
            env = (ROOT / ".env.example").read_text(encoding="utf-8").replace("ANTHROPIC_API_KEY=", f"ANTHROPIC_API_KEY={key}", 1)
            z.writestr(f"{top}/.env", env)
    size = out.stat().st_size / 1024 / 1024
    print(f"  파일 {len(files)}개, {size:.1f} MB → {out}")
    print(f"  평가용 Claude 키: {'포함됨' if key else '없음 (평가용_키.txt 를 만들고 다시 실행하면 포함)'}")
    leaked = [f for f in files if Path(f).name == ".env"]
    if leaked:
        print("  경고: .env 가 목록에 있습니다:", leaked)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
