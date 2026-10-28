"""AI 기반 Git 커밋 메시지 / PR 초안 생성기 진입점.

사용 예)
    python main.py commit
    python main.py pr --base main
"""

import sys

if sys.version_info < (3, 10):
    sys.stderr.write("[ERROR] Python 3.10 이상이 필요합니다. (현재: %s)\n" % sys.version.split()[0])
    raise SystemExit(1)

from ai_gitgen.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
