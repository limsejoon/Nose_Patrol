@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist .venv (
  echo [1/3] 가상환경 만드는 중...
  python -m venv .venv
)
call .venv\Scripts\activate
echo [2/3] 패키지 설치 확인...
pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
echo [3/3] 서버 시작: http://127.0.0.1:8000
rem Edge가 있으면 Edge로 연다 (통화 [듣기]에 자연스러운 신경망 음성 '선히'가 있음)
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (start "" "%EDGE%" http://127.0.0.1:8000) else (start "" http://127.0.0.1:8000)
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
