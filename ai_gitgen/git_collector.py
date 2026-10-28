"""Git 변경 사항 수집.

변경 사항 수집은 `git status`, `git diff` 두 명령으로 제한한다.
(`git rev-parse`는 저장소 루트/HEAD 존재 여부 확인용으로만 사용한다.)
"""

import os
import subprocess
from dataclasses import dataclass, field


class GitError(Exception):
    """Git 명령 실행 실패 또는 실행 위치가 잘못된 경우."""


@dataclass
class FileChange:
    status: str  # porcelain XY 코드 (예: "M ", " M", "??", "A ")
    path: str

    @property
    def staged(self) -> bool:
        return self.status[0] not in (" ", "?")

    @property
    def label(self) -> str:
        code = self.status.strip() or "M"
        return {
            "??": "untracked",
            "A": "added",
            "M": "modified",
            "D": "deleted",
            "R": "renamed",
            "C": "copied",
        }.get(code[0] if code != "??" else code, code)


@dataclass
class GitChanges:
    branch: str
    files: list[FileChange] = field(default_factory=list)
    diff: str = ""
    scope: str = ""  # 어떤 범위의 diff 인지 (로그/프롬프트 용)

    @property
    def diff_lines(self) -> int:
        return len(self.diff.splitlines())


def run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise GitError("git 명령을 찾을 수 없습니다. Git 설치 여부를 확인하세요.") from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 실패: {proc.stderr.strip()}")
    return proc


def ensure_repo_root() -> str:
    """현재 디렉토리가 Git 저장소의 루트인지 확인하고 루트 경로를 반환한다."""
    proc = run_git(["rev-parse", "--show-toplevel"], check=False)
    if proc.returncode != 0:
        raise GitError("Git 저장소가 아닙니다. `git init`으로 초기화된 프로젝트 루트에서 실행하세요.")
    root = proc.stdout.strip()
    cwd = os.getcwd()
    if os.path.normcase(os.path.realpath(root)) != os.path.normcase(os.path.realpath(cwd)):
        raise GitError(f"프로젝트 루트 디렉토리에서 실행하세요. (현재: {cwd} / 루트: {root})")
    return root


def _has_ref(ref: str) -> bool:
    return run_git(["rev-parse", "--verify", "--quiet", ref], check=False).returncode == 0


def collect_status() -> tuple[str, list[FileChange]]:
    """`git status --porcelain -b` 결과에서 브랜치명과 변경 파일 목록을 얻는다."""
    out = run_git(["status", "--porcelain=v1", "--branch", "--untracked-files=all"]).stdout
    branch = "(unknown)"
    files: list[FileChange] = []
    for line in out.splitlines():
        if line.startswith("## "):
            head = line[3:]
            if head.startswith("No commits yet on "):
                branch = head.removeprefix("No commits yet on ")
            else:
                branch = head.split("...")[0].split(" ")[0]
            continue
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:  # rename: "old -> new"
            path = path.split(" -> ", 1)[1]
        files.append(FileChange(status=line[:2], path=path.strip('"')))
    return branch, files


def _diff(args: list[str]) -> str:
    return run_git(["diff", "--no-color", "--no-ext-diff", *args]).stdout


def collect_commit_changes() -> GitChanges:
    """커밋용 변경 사항. staged 변경이 있으면 그것만, 없으면 작업 트리 전체를 대상으로 한다."""
    branch, files = collect_status()
    staged = [f for f in files if f.staged]
    if staged:
        return GitChanges(branch, staged, _diff(["--cached"]), "staged 변경 (git add 된 파일)")
    diff = _diff(["HEAD"]) if _has_ref("HEAD") else _diff([])
    return GitChanges(branch, files, diff, "작업 트리 변경 (staged 없음)")


def collect_pr_changes(base: str) -> GitChanges:
    """PR용 변경 사항. base...HEAD 브랜치 커밋 + 아직 커밋하지 않은 작업 트리 변경을 합친다."""
    branch, files = collect_status()
    parts: list[str] = []
    scopes: list[str] = []
    seen = {f.path for f in files}

    if _has_ref("HEAD") and branch != base and _has_ref(base):
        branch_diff = _diff([f"{base}...HEAD"])
        if branch_diff.strip():
            parts.append(branch_diff)
            scopes.append(f"{base}...HEAD 브랜치 커밋")
            for line in _diff(["--name-status", f"{base}...HEAD"]).splitlines():
                cols = line.split("\t")
                if len(cols) >= 2 and cols[-1] not in seen:
                    seen.add(cols[-1])
                    files.append(FileChange(status=cols[0][0] + " ", path=cols[-1]))

    work_diff = _diff(["HEAD"]) if _has_ref("HEAD") else _diff([])
    if work_diff.strip() or any(f.status == "??" for f in files):
        parts.append(work_diff)
        scopes.append("커밋되지 않은 작업 트리 변경")

    return GitChanges(branch, files, "\n".join(p for p in parts if p), " + ".join(scopes))
