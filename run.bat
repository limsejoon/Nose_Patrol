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
start "" http://127.0.0.1:8000
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
