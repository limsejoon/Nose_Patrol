"""설정값. .env 파일(또는 환경변수)에서 읽는다. API 키는 코드에 넣지 않는다."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_DEMO = ROOT / "data" / "demo"

# LLM: none(규칙 기반만) | anthropic | openai
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "8"))

# 기상청 API (없으면 기본 풍향 사용)
KMA_API_KEY = os.getenv("KMA_API_KEY", "")
DEFAULT_WIND_FROM_DEG = float(os.getenv("DEFAULT_WIND_FROM_DEG", "180"))  # 남풍 (시연 기본값)
DEFAULT_WIND_SPEED = float(os.getenv("DEFAULT_WIND_SPEED", "4"))

# 판단 기준값 (설정에서 바꿀 수 있음)
WINDOW_MIN = int(os.getenv("WINDOW_MIN", "60"))          # 사건 묶는 시간
CAUTION_MIN_PEOPLE = int(os.getenv("CAUTION_MIN_PEOPLE", "4"))
ALARM_MIN_PEOPLE = int(os.getenv("ALARM_MIN_PEOPLE", "10"))
CAUTION_AVG_INTENSITY = float(os.getenv("CAUTION_AVG_INTENSITY", "4"))
PERSIST_HOURS = float(os.getenv("PERSIST_HOURS", "3"))    # 지속 단계, 재발신 대기

# 브이월드: 배경지도 타일(서버가 대신 받아 PC에 저장) · 지번 주소 → 좌표
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "")
TILE_CACHE = DATA_PROCESSED / "tiles"

# 지도에 악취배출시설 사업장명을 보일지 (기본: 숨김 — 신고 지점과 나란히 보이면 원인 지목으로 읽힐 수 있음)
FACILITY_SHOW_NAMES = os.getenv("FACILITY_SHOW_NAMES", "false").lower() == "true"
