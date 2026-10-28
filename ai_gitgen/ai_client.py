"""AI API(REST) 연동 - OpenAI Chat Completions.

요청 구성 -> HTTP 호출 -> 응답 파싱 -> 예외를 사람이 읽을 수 있는 오류로 변환하는 흐름을
표준 라이브러리(urllib)만으로 구현한다. 비용 보호를 위해 재시도하지 않는다(1회 실행 = 1회 호출).
"""

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass


class AIClientError(Exception):
    """AI API 호출 실패. 메시지에 원인을 담는다."""


@dataclass
class AIResult:
    content: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int


STATUS_HINTS = {
    400: "잘못된 요청 - 모델명/파라미터 값을 확인하세요",
    401: "인증 실패 - AI_API_KEY 값이 올바른지 확인하세요",
    403: "권한 없음 - 해당 모델에 접근 권한이 있는지 확인하세요",
    404: "모델 또는 엔드포인트를 찾을 수 없음 - --model 값을 확인하세요",
    429: "요청 한도 초과 또는 크레딧 부족 - 잠시 후 다시 시도하거나 사용량/결제 상태를 확인하세요",
}


def chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> AIResult:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc)
        hint = STATUS_HINTS.get(exc.code, "서버 오류 - 잠시 후 다시 시도하세요" if exc.code >= 500 else "요청 실패")
        raise AIClientError(f"HTTP {exc.code} {hint}\n        응답: {detail}") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, socket.timeout):
            raise AIClientError(f"요청 시간 초과({timeout}초) - 네트워크 상태를 확인하세요") from exc
        raise AIClientError(f"네트워크 오류 - API 서버에 연결할 수 없습니다 ({reason})") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise AIClientError(f"요청 시간 초과({timeout}초) - 네트워크 상태를 확인하세요") from exc
    except json.JSONDecodeError as exc:
        raise AIClientError("API 응답을 JSON으로 해석할 수 없습니다") from exc

    try:
        choice = body["choices"][0]
        content = choice["message"].get("content") or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise AIClientError(f"예상하지 못한 응답 형식: {str(body)[:300]}") from exc

    usage = body.get("usage") or {}
    return AIResult(
        content=content,
        finish_reason=choice.get("finish_reason", ""),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return exc.reason or ""
    try:
        return json.loads(raw)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return raw[:300] or str(exc.reason)
