"""CLI: python main.py {commit,pr} [옵션]

흐름: 루트 확인 -> git status/diff 수집 -> (변경 없음이면 종료) -> safe-mode 가공
      -> API Key 확인 -> AI API 1회 호출 -> JSON 파싱 -> 검증/다듬기 -> 구획 출력
"""

import argparse
import sys

from . import config
from .ai_client import AIClientError, chat_completion
from .formatter import FormatError, normalize_commit, normalize_pr, parse_json, render_checks, section
from .git_collector import GitChanges, GitError, collect_commit_changes, collect_pr_changes, ensure_repo_root
from .prompts import COMMIT_SYSTEM, PR_SYSTEM, build_user_prompt
from .safe_mode import SAFE_MAX_FILES, SAFE_MAX_LINES, prepare_diff


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def error(msg: str) -> None:
    print(f"[ERROR] {msg}")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", "-model", default=config.env_or("AI_MODEL", config.DEFAULT_MODEL),
                        help=f"사용할 모델 (기본: AI_MODEL 환경변수 또는 {config.DEFAULT_MODEL})")
    common.add_argument("--temperature", "-temperature", type=float, default=config.DEFAULT_TEMPERATURE,
                        help=f"샘플링 온도 0.0~2.0, 낮을수록 일관적 (기본: {config.DEFAULT_TEMPERATURE})")
    common.add_argument("--max-tokens", "-max-tokens", type=int, default=config.DEFAULT_MAX_TOKENS,
                        help=f"응답 최대 토큰 수 (기본: {config.DEFAULT_MAX_TOKENS})")
    common.add_argument("--safe-mode", "-safe-mode", action=argparse.BooleanOptionalAction, default=True,
                        help=f"민감정보 마스킹 + 최대 {SAFE_MAX_FILES}개 파일/{SAFE_MAX_LINES}줄만 전송 (기본: 켜짐)")
    common.add_argument("--context", "-context", default=None,
                        help="변경 이유/요구사항 메모 (프롬프트 맥락으로 전달)")
    common.add_argument("--timeout", type=int, default=config.DEFAULT_TIMEOUT, help="API 요청 타임아웃(초)")

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Git 변경 사항(git status / git diff)으로 커밋 메시지와 PR 초안을 생성합니다.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("commit", parents=[common], help="커밋 메시지 생성")
    pr = sub.add_parser("pr", parents=[common], help="PR 제목/본문 초안 생성")
    pr.add_argument("--base", "-base", default="main", help="PR 비교 기준 브랜치 (기본: main)")
    return parser


def collect(args) -> GitChanges | None:
    root = ensure_repo_root()
    info(f"Git 저장소 루트 확인: {root}")
    changes = collect_pr_changes(args.base) if args.command == "pr" else collect_commit_changes()
    if args.command == "pr":
        info(f"현재 브랜치: {changes.branch} (기준: {args.base})")
    if not changes.files:
        what = "PR 초안" if args.command == "pr" else "커밋 메시지"
        info(f"변경 사항이 없습니다. {what}를 생성하지 않고 종료합니다.")
        return None
    info(f"Git status 수집 완료: {len(changes.files)}개 파일 변경 감지")
    info(f"Git diff 수집 완료: {changes.diff_lines}줄 ({changes.scope})")
    return changes


def call_ai(args, api_key: str, system: str, user: str) -> dict:
    info(f"AI API 요청 중... (model={args.model}, temperature={args.temperature}, max_tokens={args.max_tokens})")
    result = chat_completion(
        api_key=api_key,
        base_url=config.env_or("AI_API_BASE_URL", config.DEFAULT_BASE_URL),
        model=args.model,
        system=system,
        user=user,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
    )
    info(f"AI API 호출 횟수: 1회 (입력 {result.prompt_tokens} 토큰 / 출력 {result.completion_tokens} 토큰)")
    if result.finish_reason == "length":
        raise FormatError(f"응답이 max_tokens({args.max_tokens}) 제한에 걸려 잘렸습니다. --max-tokens 값을 늘려 다시 실행하세요.")
    return parse_json(result.content)


def run(args) -> int:
    if not 0.0 <= args.temperature <= 2.0:
        error("--temperature 는 0.0 ~ 2.0 사이여야 합니다.")
        return 2
    if args.max_tokens <= 0:
        error("--max-tokens 는 1 이상이어야 합니다.")
        return 2

    changes = collect(args)
    if changes is None:
        return 0

    diff, report = prepare_diff(changes.diff, args.safe_mode)
    if report.enabled:
        masked = ", ".join(f"{k} {v}건" for k, v in report.masked.items()) or "없음"
        info(f"safe-mode ON: 마스킹 {masked} / 제외 파일 {len(report.excluded_files)}개 / "
             f"생략 파일 {len(report.omitted_files)}개 / 생략 줄 {report.truncated_lines}줄")
    else:
        info("safe-mode OFF: diff 원문을 전송합니다." +
             (f" (비용 보호로 {report.truncated_lines}줄 생략)" if report.truncated_lines else ""))

    api_key = config.get_api_key()
    if not api_key:
        error(f"{config.API_KEY_ENV} 환경변수가 설정되지 않았습니다.")
        print(f'## 예) export {config.API_KEY_ENV}="YOUR_KEY"  (또는 .env 파일에 {config.API_KEY_ENV}=YOUR_KEY)')
        return 1

    user_prompt = build_user_prompt(changes, diff, args.context)

    if args.command == "commit":
        draft = normalize_commit(call_ai(args, api_key, COMMIT_SYSTEM, user_prompt))
        print("[DONE] 커밋 메시지 생성 완료")
        print(section("Change Summary", draft.summary or "(요약 없음)"))
        print(section("Commit Message", draft.message))
        print(section("Validation", render_checks(draft.checks)))
        print("※ AI 초안입니다. 검토/수정 후 적용하세요. 예) git commit -m \"<제목>\" -m \"<본문>\"")
    else:
        draft = normalize_pr(call_ai(args, api_key, PR_SYSTEM, user_prompt), changes.files)
        print("[DONE] PR 초안 생성 완료")
        print(section("Change Summary", draft.summary or "(요약 없음)"))
        print(section("PR Title", draft.title))
        print(section("PR Body", draft.body))
        print(section("Validation", render_checks(draft.checks)))
        print("※ AI 초안입니다. 검토/수정 후 GitHub PR 작성 화면에 붙여 넣으세요.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    config.load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except GitError as exc:
        error(str(exc))
    except AIClientError as exc:
        error(f"AI API 호출 실패: {exc}")
    except FormatError as exc:
        error(f"응답 처리 실패: {exc}")
    except KeyboardInterrupt:
        error("사용자에 의해 중단되었습니다.")
    return 1
