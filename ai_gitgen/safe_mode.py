"""diff 전송 전 민감정보 보호 (safe-mode).

safe-mode(기본 ON)에서는 아래 순서로 diff를 가공한 뒤 AI API에 보낸다.
  1) 민감 파일(.env, *.pem, *.key 등)은 diff 내용을 통째로 제외
  2) API Key / 토큰 / 이메일 / 전화번호 / 주민등록번호 형태를 [MASKED:종류]로 치환  -> 요구사항 (A)
  3) 최대 10개 파일, 최대 200줄까지만 전송                                       -> 요구사항 (B)
safe-mode OFF(--no-safe-mode)여도 비용 보호용 최대 줄 수(HARD_LIMIT_LINES)는 항상 적용한다.
"""

import fnmatch
import re
from dataclasses import dataclass, field

SAFE_MAX_FILES = 10
SAFE_MAX_LINES = 200
HARD_LIMIT_LINES = 3000

SENSITIVE_FILE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore",
    "id_rsa*", "id_ed25519*", "*credentials*", "*secret*",
]

MASK_RULES: list[tuple[str, re.Pattern, str]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[MASKED:private_key]"),
    ("api_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[MASKED:api_key]"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "[MASKED:github_token]"),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[MASKED:aws_key]"),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), "[MASKED:google_key]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"), "[MASKED:jwt]"),
    # key = "value" / KEY: value 형태의 비밀값 대입
    ("secret_assign", re.compile(
        r"(?i)((?:api[_-]?key|secret|token|passw(?:or)?d|pwd|access[_-]?key)[\w\-]*[\"']?\s*[:=]\s*)([\"']?)(?!\[MASKED)([^\s\"',;]{6,})\2"
    ), r"\1\2[MASKED:secret]\2"),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[MASKED:email]"),
    ("rrn", re.compile(r"\b\d{6}-[1-4]\d{6}\b"), "[MASKED:rrn]"),
    ("phone", re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"), "[MASKED:phone]"),
]


@dataclass
class SafeReport:
    enabled: bool
    masked: dict[str, int] = field(default_factory=dict)
    excluded_files: list[str] = field(default_factory=list)
    omitted_files: list[str] = field(default_factory=list)
    truncated_lines: int = 0


def is_sensitive_file(path: str) -> bool:
    name = path.replace("\\", "/").split("/")[-1].lower()
    return any(fnmatch.fnmatch(name, pat) for pat in SENSITIVE_FILE_PATTERNS)


def _split_by_file(diff: str) -> list[tuple[str, str]]:
    """diff 텍스트를 (파일경로, 해당 파일 diff) 목록으로 나눈다."""
    chunks: list[tuple[str, list[str]]] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1] if " b/" in line else line
            chunks.append((path, [line]))
        elif chunks:
            chunks[-1][1].append(line)
    return [(p, "\n".join(lines)) for p, lines in chunks]


def mask_text(text: str, counter: dict[str, int] | None = None) -> str:
    for name, pattern, repl in MASK_RULES:
        text, n = pattern.subn(repl, text)
        if n and counter is not None:
            counter[name] = counter.get(name, 0) + n
    return text


def prepare_diff(diff: str, safe_mode: bool) -> tuple[str, SafeReport]:
    report = SafeReport(enabled=safe_mode)
    max_files = SAFE_MAX_FILES if safe_mode else None
    max_lines = SAFE_MAX_LINES if safe_mode else HARD_LIMIT_LINES

    kept: list[str] = []
    for path, chunk in _split_by_file(diff):
        if safe_mode and is_sensitive_file(path):
            report.excluded_files.append(path)
            kept.append(chunk.splitlines()[0] + "\n[SAFE-MODE] 민감 파일로 분류되어 diff 내용을 전송하지 않음")
            continue
        if max_files is not None and len(kept) >= max_files:
            report.omitted_files.append(path)
            continue
        kept.append(mask_text(chunk, report.masked) if safe_mode else chunk)

    lines = "\n".join(kept).splitlines()
    if len(lines) > max_lines:
        report.truncated_lines = len(lines) - max_lines
        lines = lines[:max_lines] + [f"... (이하 {report.truncated_lines}줄 생략)"]
    if report.omitted_files:
        lines.append(f"... (파일 수 제한으로 {len(report.omitted_files)}개 파일 diff 생략: {', '.join(report.omitted_files)})")
    return "\n".join(lines), report
