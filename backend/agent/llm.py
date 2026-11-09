"""외부 LLM 호출. 실패하면 None을 돌려주고, 호출한 쪽이 규칙 기반으로 대신한다."""
import json
import httpx
from backend import config


def available() -> bool:
    if config.LLM_PROVIDER == "anthropic":
        return bool(config.ANTHROPIC_API_KEY)
    if config.LLM_PROVIDER == "openai":
        return bool(config.OPENAI_API_KEY)
    return False


def ask(system: str, user: str, want_json: bool = False, max_tokens: int = 600):
    if not available():
        return None
    try:
        if config.LLM_PROVIDER == "anthropic":
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": config.ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": config.LLM_MODEL or "claude-haiku-5-5",
                      "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": user}]},
                timeout=config.LLM_TIMEOUT)
            r.raise_for_status()
            text = r.json()["content"][0]["text"]
        else:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
                json={"model": config.LLM_MODEL or "gpt-4o-mini",
                      "max_tokens": max_tokens,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
                timeout=config.LLM_TIMEOUT)
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
    except Exception as e:  # 통신 차단(DLP), 키 오류 등
        print(f"[LLM] 호출 실패 → 규칙 기반 사용: {e}")
        return None
    if not want_json:
        return text.strip()
    try:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1])
    except Exception:
        return None
