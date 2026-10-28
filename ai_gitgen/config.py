"""환경변수 / .env 설정 로딩.

API Key는 코드에 두지 않고 환경변수(AI_API_KEY)로만 읽는다.
편의를 위해 프로젝트 루트(main.py 위치)의 .env 파일을 읽어 환경변수로 등록하지만,
이미 셸에서 export 한 값이 있으면 그 값을 우선한다.
"""

import os
from pathlib import Path

API_KEY_ENV = "AI_API_KEY"

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 2000
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60

TOOL_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = TOOL_ROOT / ".env") -> None:
    """KEY=VALUE 형식의 .env 파일을 읽어 아직 설정되지 않은 환경변수만 채운다."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def get_api_key() -> str | None:
    value = os.environ.get(API_KEY_ENV, "").strip()
    return value or None


def env_or(name: str, default):
    value = os.environ.get(name, "").strip()
    return value if value else default
