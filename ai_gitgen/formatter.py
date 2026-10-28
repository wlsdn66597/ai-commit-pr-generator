"""AI 응답 검증 및 다듬기(후처리) + 터미널 출력 형식.

재생성 대신 후처리 방식을 택했다 (API 호출 1회 유지).
  - 커밋 제목: 한 줄, 끝 마침표 제거, 50자 초과 시 경고, 72자 초과 시 잘라냄
  - 커밋 본문: bullet 1~3개로 정리
  - PR 제목: 한 줄, 80자 초과 시 잘라냄
  - PR 본문: Why / What / How to Test 헤더 + 섹션마다 bullet 1개 이상 보장 후 최종 검증
"""

import json
import re
from dataclasses import dataclass, field

from .git_collector import FileChange

COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
PR_TITLE_MAX = 80
COMMIT_BODY_MAX_BULLETS = 3
PR_SECTION_MAX_BULLETS = 5

CONVENTIONAL_RE = re.compile(r"^(feat|fix|refactor|docs|style|test|chore|perf|build|ci|revert)(\([^)]+\))?!?: \S")
PR_SECTIONS = [("why", "Why"), ("what", "What"), ("how_to_test", "How to Test")]

SEP = "-" * 60


class FormatError(Exception):
    pass


@dataclass
class Check:
    ok: bool
    message: str


@dataclass
class CommitDraft:
    summary: str
    title: str
    body: list[str]
    checks: list[Check] = field(default_factory=list)

    @property
    def message(self) -> str:
        if not self.body:
            return self.title
        return self.title + "\n\n" + "\n".join(f"- {b}" for b in self.body)


@dataclass
class PRDraft:
    summary: str
    title: str
    body: str
    checks: list[Check] = field(default_factory=list)


def parse_json(content: str) -> dict:
    text = content.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FormatError(f"AI 응답이 JSON 형식이 아닙니다: {text[:200]}") from exc
    if not isinstance(data, dict):
        raise FormatError("AI 응답 JSON의 최상위가 객체가 아닙니다.")
    return data


def _one_line(value) -> str:
    text = str(value or "").strip().strip("`\"'")
    text = text.splitlines()[0] if text else ""
    return re.sub(r"\s+", " ", text).strip()


def _bullets(value, limit: int) -> list[str]:
    if isinstance(value, str):
        value = value.splitlines()
    items = []
    for item in value or []:
        text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", str(item)).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            items.append(text)
    return items[:limit]


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_commit(data: dict) -> CommitDraft:
    checks: list[Check] = []
    title = _one_line(data.get("title")).rstrip(".")
    if not title:
        raise FormatError("AI 응답에 커밋 제목(title)이 없습니다.")
    if len(title) > COMMIT_TITLE_MAX:
        title = _cut(title, COMMIT_TITLE_MAX)
        checks.append(Check(False, f"커밋 제목이 최대 {COMMIT_TITLE_MAX}자를 넘어 잘라냈습니다."))
    if len(title) <= COMMIT_TITLE_RECOMMENDED:
        checks.append(Check(True, f"커밋 제목 길이 {len(title)}자 (권장 {COMMIT_TITLE_RECOMMENDED}자 이내)"))
    else:
        checks.append(Check(False, f"커밋 제목 길이 {len(title)}자 - 권장 {COMMIT_TITLE_RECOMMENDED}자 초과 (최대 {COMMIT_TITLE_MAX}자 이내)"))
    checks.append(Check(bool(CONVENTIONAL_RE.match(title)), "Conventional Commits 형식(type: 요약)"))

    body = _bullets(data.get("body"), COMMIT_BODY_MAX_BULLETS)
    if body:
        checks.append(Check(True, f"커밋 본문 bullet {len(body)}개 (핵심 변경 1~{COMMIT_BODY_MAX_BULLETS}개)"))
    else:
        checks.append(Check(True, "커밋 본문 없음 (제목만 사용)"))
    return CommitDraft(summary=_one_line(data.get("summary")), title=title, body=body, checks=checks)


def normalize_pr(data: dict, files: list[FileChange]) -> PRDraft:
    checks: list[Check] = []
    title = _one_line(data.get("title")).rstrip(".")
    if not title:
        raise FormatError("AI 응답에 PR 제목(title)이 없습니다.")
    if len(title) > PR_TITLE_MAX:
        title = _cut(title, PR_TITLE_MAX)
        checks.append(Check(False, f"PR 제목이 {PR_TITLE_MAX}자를 넘어 잘라냈습니다."))
    checks.append(Check(len(title) <= PR_TITLE_MAX, f"PR 제목 길이 {len(title)}자 (최대 {PR_TITLE_MAX}자)"))

    fallbacks = {
        "why": ["(변경 배경을 작성해 주세요)"],
        "what": [f"{f.path} 변경 ({f.label})" for f in files[:3]] or ["(핵심 변경 사항을 작성해 주세요)"],
        "how_to_test": ["변경된 기능을 로컬에서 실행해 기존 동작과 새 동작을 확인"],
    }
    lines: list[str] = []
    for key, header in PR_SECTIONS:
        items = _bullets(data.get(key), PR_SECTION_MAX_BULLETS)
        if not items:
            items = fallbacks[key]
            checks.append(Check(False, f"'{header}' 섹션이 비어 있어 기본 bullet을 채웠습니다. 직접 보완하세요."))
        lines += [f"## {header}", *(f"- {i}" for i in items), ""]
    body = "\n".join(lines).rstrip()

    checks += validate_pr_body(body)
    return PRDraft(summary=_one_line(data.get("summary")), title=title, body=body, checks=checks)


def validate_pr_body(body: str) -> list[Check]:
    """최종 PR 본문이 템플릿 규칙(헤더 + 섹션별 bullet 1개 이상)을 만족하는지 검사한다."""
    checks = []
    for _, header in PR_SECTIONS:
        m = re.search(rf"^## {re.escape(header)}\s*$([\s\S]*?)(?=^## |\Z)", body, re.MULTILINE)
        count = len(re.findall(r"^- \S", m.group(1), re.MULTILINE)) if m else 0
        checks.append(Check(bool(m) and count >= 1, f"PR 본문 '## {header}' 섹션 bullet {count}개"))
    return checks


def section(title: str, content: str) -> str:
    return f"\n--- {title} ---\n{content}\n{SEP}"


def render_checks(checks: list[Check]) -> str:
    return "\n".join(f"[{'OK' if c.ok else 'WARN'}] {c.message}" for c in checks)
