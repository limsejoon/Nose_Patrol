"""Claude(Anthropic) 호출. 공식 Python SDK를 쓴다.
- 키가 없거나 통신이 막히면(센터 DLP 등) None 을 돌려주고, 부른 쪽이 규칙 기반으로 대신한다.
- 모델 두 개: 말로 묻는 분석은 LLM_MODEL (기본 claude-sonnet-5-5),
  카톡 신고 해석은 LLM_PARSE_MODEL (기본 claude-haiku-5-5, 가장 저렴·빠름).
- LLM은 숫자를 만들지 않는다: 문장 해석과 설명만 맡고, 계산은 도구(파이썬 함수)가 한다.
"""
import json
import anthropic
from backend import config

DEFAULT_MODEL = "claude-sonnet-5-5"        # 말로 묻는 분석 (도구 고르기·해석)
DEFAULT_PARSE_MODEL = "claude-haiku-5-5"   # 신고 한 줄 해석 (간단, 자주 호출)
_client = None


def model() -> str:
    return config.LLM_MODEL or DEFAULT_MODEL


def parse_model() -> str:
    return config.LLM_PARSE_MODEL or DEFAULT_PARSE_MODEL


def available() -> bool:
    return config.LLM_PROVIDER == "anthropic" and bool(config.ANTHROPIC_API_KEY)


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=1)
    return _client


def _text(resp) -> str:
    """응답에서 글자 블록만 모은다 (생각 블록 등은 건너뜀)."""
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def ask(system: str, user: str, want_json: bool = False, max_tokens: int = 600, schema: dict | None = None,
        model_name: str | None = None):
    """한 번 묻고 답을 받는다. schema 를 주면 그 JSON 형식으로만 답하게 강제한다(구조화된 출력)."""
    if not available():
        return None
    output_config = {"effort": "low"}
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    try:
        resp = client().messages.create(
            model=model_name or model(), max_tokens=max_tokens, system=system,
            output_config=output_config,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIConnectionError as e:   # 통신 차단(DLP), 네트워크
        print(f"[LLM] 연결 실패 → 규칙 기반 사용: {e}")
        return None
    except anthropic.APIStatusError as e:       # 키 오류, 한도 초과, 서버 오류
        print(f"[LLM] API 오류 {e.status_code} → 규칙 기반 사용: {e.message}")
        return None
    if resp.stop_reason == "refusal":
        return None
    text = _text(resp)
    if not (want_json or schema):
        return text
    try:
        return json.loads(text) if schema else json.loads(text[text.find("{"):text.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
