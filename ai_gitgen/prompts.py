"""프롬프트 구성.

프롬프트 = system(역할 + 양식 규칙 + 출력 JSON 스키마) + user(작업 맥락 + git status + git diff).
결과를 JSON으로 받으면 코드에서 길이/형식을 검증하고 다듬기 쉽다.
"""

from .git_collector import GitChanges

COMMIT_SYSTEM = """너는 Git 커밋 메시지를 작성하는 시니어 개발자다.
주어진 git status / git diff 만 근거로, Conventional Commits 형식의 한국어 커밋 메시지를 만든다.

[작성 규칙]
1. title: "<type>: <무엇을 했는지>" 한 줄.
   - type은 feat, fix, refactor, docs, style, test, chore, perf, build, ci 중 하나.
   - 50자 이내(절대 72자 초과 금지), 끝에 마침표를 찍지 않는다.
2. body: 핵심 변경 사항 1~3개를 bullet 문자열 배열로 작성한다.
   - 각 항목은 변경된 파일 또는 모듈 이름을 1개 이상 언급하고, 무엇을 왜 바꿨는지 한 문장으로 쓴다.
   - "- " 기호는 붙이지 않는다.
3. summary: 이번 변경 전체를 1~2문장으로 요약한다.
4. diff에 없는 내용을 지어내지 않는다. [MASKED:...] 로 가려진 값은 추측하거나 언급하지 않는다.
5. 아래 JSON 형식으로만 답한다. 다른 텍스트는 쓰지 않는다.
{"summary": "...", "title": "...", "body": ["...", "..."]}"""

PR_SYSTEM = """너는 코드 리뷰어가 읽기 쉬운 Pull Request 설명을 작성하는 시니어 개발자다.
주어진 git status / git diff 만 근거로 한국어 PR 제목과 본문 초안을 만든다.

[작성 규칙]
1. title: "<type>: <핵심 변경>" 한 줄, 80자 이내. type은 feat, fix, refactor, docs, test, chore 등.
2. why: 변경 배경/이유 1~3개. diff와 작업 맥락에서 추론할 수 있는 범위에서만 쓴다.
3. what: 핵심 변경 사항 2~5개. 파일/모듈 이름을 언급하며 무엇이 바뀌었는지 쓴다.
4. how_to_test: 리뷰어가 따라 할 수 있는 테스트 방법 1~4개. 가능하면 실행 명령을 포함한다.
5. 각 항목은 한 문장의 bullet 문자열이며 "- " 기호는 붙이지 않는다.
6. diff에 없는 내용을 지어내지 않는다. [MASKED:...] 로 가려진 값은 추측하거나 언급하지 않는다.
7. 아래 JSON 형식으로만 답한다. 다른 텍스트는 쓰지 않는다.
{"summary": "...", "title": "...", "why": ["..."], "what": ["..."], "how_to_test": ["..."]}"""


def build_user_prompt(changes: GitChanges, diff: str, context: str | None) -> str:
    file_lines = "\n".join(f"- [{f.label}] {f.path}" for f in changes.files)
    untracked = [f.path for f in changes.files if f.status == "??"]
    parts = [
        "[작업 맥락]",
        f"- 현재 브랜치: {changes.branch}",
        f"- diff 범위: {changes.scope}",
        f"- 변경 이유(작성자 메모): {context or '없음 (diff에서 추론)'}",
    ]
    if untracked:
        parts.append("- untracked 파일은 git diff에 내용이 포함되지 않아 파일명만 제공됨")
    parts += [
        "",
        f"[변경 파일 목록 - git status ({len(changes.files)}개)]",
        file_lines,
        "",
        "[git diff]",
        diff or "(diff 내용 없음 - 파일 목록만 참고)",
    ]
    return "\n".join(parts)
