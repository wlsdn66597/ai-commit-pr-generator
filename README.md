# AI Git Commit / PR Generator

`git status`와 `git diff`로 변경 사항을 모으고, OpenAI API(REST)를 **한 번** 호출해 **커밋 메시지**와 **PR 제목/본문 초안**을 터미널에 출력하는 Python CLI입니다.

```
git status / git diff 수집 → safe-mode(마스킹·전송 제한) → 프롬프트 구성 → AI API 1회 호출
→ JSON 응답 파싱 → 길이/형식 검증·다듬기 → 구획을 나눠 터미널 출력
```

> 생성된 문구는 **초안**입니다. 사용자가 검토한 뒤 직접 커밋하거나 PR에 붙여 넣습니다. (`git push`, GitHub PR 생성 같은 원격 반영 기능은 넣지 않았습니다.)

---

## 1. 설치 및 실행 방법

> Python 3.10 이상과 Git만 있으면 됩니다. 표준 라이브러리만 쓰기 때문에 `pip install`이 필요 없습니다.

```bash
git clone https://github.com/wlsdn66597/ai-commit-pr-generator.git
cd ai-commit-pr-generator
python --version   # 3.10 이상인지 확인
```

도구는 **변경 사항을 요약할 대상 프로젝트의 루트 디렉토리**에서 실행합니다. 하위 폴더에서 실행하거나 Git 저장소가 아닌 곳에서 실행하면 오류 메시지를 출력하고 종료합니다.

```bash
cd ~/my-project                                   # git init 된 프로젝트 루트
python ~/ai-commit-pr-generator/main.py commit    # 커밋 메시지 생성
python ~/ai-commit-pr-generator/main.py pr        # PR 초안 생성
```

| 명령 | 수집 대상 diff |
|---|---|
| `commit` | `git add` 한(staged) 변경이 있으면 staged만, 없으면 작업 트리 전체 (`git diff HEAD`) |
| `pr` | `git diff <base>...HEAD`(브랜치 커밋) + 아직 커밋하지 않은 변경 (`--base` 기본값 `main`) |

untracked 파일은 `git diff`에 내용이 나오지 않으므로 파일 이름만 프롬프트에 들어갑니다.

## 2. 환경변수(API Key) 설정 방법

> API Key는 코드에 넣지 않고 `AI_API_KEY` 환경변수로만 읽습니다. 셸에서 export 하거나 `.env` 파일에 적으면 됩니다.

**방법 A. `.env` 파일 (권장)** - 도구 폴더(`main.py`가 있는 곳)의 `.env`를 채웁니다. `.env`는 `.gitignore`에 있어 커밋되지 않습니다.

```bash
cp .env.example .env
# .env
AI_API_KEY=sk-...
```

**방법 B. 셸 환경변수** - 셸에서 설정한 값이 `.env`보다 우선합니다.

```bash
export AI_API_KEY="YOUR_KEY"          # macOS / Linux / Git Bash
$env:AI_API_KEY = "YOUR_KEY"          # Windows PowerShell
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `AI_API_KEY` | O | OpenAI API Key |
| `AI_MODEL` | | 기본 모델 변경 (기본 `gpt-4.1-mini`, `--model`이 우선) |
| `AI_API_BASE_URL` | | OpenAI 호환 엔드포인트 주소 (기본 `https://api.openai.com/v1`) |

## 3. 커밋/PR 생성 명령 사용 예시

> 서브 명령은 `commit`, `pr` 두 가지이고, API 파라미터와 safe-mode는 옵션으로 바꿀 수 있습니다.

```bash
python main.py commit                                   # 기본값으로 커밋 메시지 생성
python main.py commit --temperature 0.1                 # 더 일관된(보수적인) 문구
python main.py commit --model gpt-4.1 --max-tokens 500  # 모델/최대 토큰 변경
python main.py commit --context "로그인 실패 시 에러 메시지가 안 보이는 버그 수정"  # 변경 이유 전달
python main.py pr --base develop                        # develop 기준 PR 초안
python main.py pr --no-safe-mode                        # 마스킹/전송 제한 끄기 (주의)
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--model`, `-model` | `gpt-4.1-mini` | 사용할 모델 |
| `--temperature`, `-temperature` | `0.3` | 0.0~2.0. 낮을수록 같은 입력에 비슷한 결과, 높을수록 표현이 다양해짐 |
| `--max-tokens`, `-max-tokens` | `800` | 응답 최대 토큰 수. 너무 작으면 응답이 잘려 오류로 안내 |
| `--safe-mode` / `--no-safe-mode` | 켜짐 | 민감정보 마스킹 + 최대 10개 파일 / 200줄만 전송 |
| `--context`, `-context` | 없음 | 변경 이유·요구사항 메모를 프롬프트에 추가 |
| `--base`, `-base` (`pr` 전용) | `main` | PR 비교 기준 브랜치 |
| `--timeout` | `60` | API 요청 타임아웃(초) |

`temperature`를 지원하지 않는 모델(일부 추론형 모델)을 지정하면 API가 400 오류를 돌려주고, 도구가 그 원인을 그대로 출력합니다.

## 4. 출력 예시

> 로그 → 변경 요약 → 결과물 → 검증 결과 순서로, `--- 제목 ---` 구분선으로 구획을 나눠 출력합니다. 아래 문구는 예시이고 실제 결과는 diff에 따라 달라집니다.

### 커밋 메시지 (`python main.py commit`)

```
[INFO] Git 저장소 루트 확인: C:/work/my-project
[INFO] Git status 수집 완료: 3개 파일 변경 감지
[INFO] Git diff 수집 완료: 128줄 (작업 트리 변경 (staged 없음))
[INFO] safe-mode ON: 마스킹 api_key 1건 / 제외 파일 1개 / 생략 파일 0개 / 생략 줄 0줄
[INFO] AI API 요청 중... (model=gpt-4.1-mini, temperature=0.3, max_tokens=800)
[INFO] AI API 호출 횟수: 1회 (입력 1834 토큰 / 출력 121 토큰)
[DONE] 커밋 메시지 생성 완료

--- Change Summary ---
로그인 입력값 검증을 추가하고 설정을 환경변수에서 읽도록 바꿨습니다.
------------------------------------------------------------

--- Commit Message ---
feat: 로그인 입력 검증 및 환경변수 설정 로딩 추가

- app.py에 이메일/비밀번호 형식 검증 함수 validate_login 추가
- config.py가 하드코딩 값 대신 환경변수에서 API 설정을 읽도록 변경
------------------------------------------------------------

--- Validation ---
[OK] 커밋 제목 길이 31자 (권장 50자 이내)
[OK] Conventional Commits 형식(type: 요약)
[OK] 커밋 본문 bullet 2개 (핵심 변경 1~3개)
------------------------------------------------------------
※ AI 초안입니다. 검토/수정 후 적용하세요. 예) git commit -m "<제목>" -m "<본문>"
```

### PR 제목/본문 (`python main.py pr`)

```
[INFO] Git 저장소 루트 확인: C:/work/my-project
[INFO] 현재 브랜치: feature/login-validation (기준: main)
[INFO] Git status 수집 완료: 3개 파일 변경 감지
[INFO] Git diff 수집 완료: 142줄 (main...HEAD 브랜치 커밋)
[INFO] safe-mode ON: 마스킹 없음 / 제외 파일 0개 / 생략 파일 0개 / 생략 줄 0줄
[INFO] AI API 요청 중... (model=gpt-4.1-mini, temperature=0.3, max_tokens=800)
[INFO] AI API 호출 횟수: 1회 (입력 1950 토큰 / 출력 210 토큰)
[DONE] PR 초안 생성 완료

--- Change Summary ---
로그인 입력 검증과 환경변수 기반 설정 로딩을 추가합니다.
------------------------------------------------------------

--- PR Title ---
feat: 로그인 입력 검증과 환경변수 기반 설정 로딩 추가
------------------------------------------------------------

--- PR Body ---
## Why
- 잘못된 형식의 입력이 서버까지 전달되어 불필요한 요청과 오류가 발생했습니다.
- API 설정이 코드에 하드코딩되어 있어 키 유출 위험이 있었습니다.

## What
- app.py에 이메일/비밀번호 형식을 검사하는 validate_login 함수 추가
- config.py가 환경변수에서 API 설정을 읽도록 변경
- README.md에 환경변수 설정 방법 추가

## How to Test
- export API_URL="http://localhost:8000" 설정 후 python app.py 실행
- 잘못된 이메일(예: abc)로 로그인 시 검증 오류 메시지가 출력되는지 확인
- 올바른 형식으로 로그인 시 정상적으로 요청이 전송되는지 확인
------------------------------------------------------------

--- Validation ---
[OK] PR 제목 길이 33자 (최대 80자)
[OK] PR 본문 '## Why' 섹션 bullet 2개
[OK] PR 본문 '## What' 섹션 bullet 3개
[OK] PR 본문 '## How to Test' 섹션 bullet 3개
------------------------------------------------------------
※ AI 초안입니다. 검토/수정 후 GitHub PR 작성 화면에 붙여 넣으세요.
```

### 오류 / 예외 상황

```
$ python main.py commit            # 변경 사항이 없을 때 (API를 호출하지 않음)
[INFO] 변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다.

$ python main.py commit            # API Key 미설정
[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.
## 예) export AI_API_KEY="YOUR_KEY"  (또는 .env 파일에 AI_API_KEY=YOUR_KEY)

$ python main.py commit            # 잘못된 API Key
[ERROR] AI API 호출 실패: HTTP 401 인증 실패 - AI_API_KEY 값이 올바른지 확인하세요
        응답: Incorrect API key provided: sk-xx****

$ python main.py commit            # 네트워크 연결 불가
[ERROR] AI API 호출 실패: 네트워크 오류 - API 서버에 연결할 수 없습니다 (...)
```

| 상황 | 출력 |
|---|---|
| Git 저장소가 아님 / 루트가 아님 | `[ERROR] Git 저장소가 아닙니다...` / `[ERROR] 프로젝트 루트 디렉토리에서 실행하세요...` |
| 401 / 403 / 404 / 429 / 5xx | 상태 코드별 원인 안내 + API가 돌려준 오류 메시지 |
| 타임아웃 | `요청 시간 초과(60초)` |
| `max_tokens` 부족으로 응답 잘림 | `--max-tokens 값을 늘려 다시 실행하세요` |

## 5. 출력 형식 검증 및 다듬기

> AI 응답을 그대로 믿지 않고, 재생성 없이 **후처리**로 실무 규칙을 맞춥니다. API 호출을 1회로 유지하기 위해서입니다.

| 대상 | 규칙 | 처리 |
|---|---|---|
| 커밋 제목 | 1줄, 50자 이내 권장, 최대 72자 | 첫 줄만 사용, 끝 마침표 제거, 50자 초과 시 `WARN`, 72자 초과 시 잘라냄 |
| 커밋 본문 | 핵심 변경 bullet 1~3개 (파일/모듈 언급) | `- ` 형식으로 통일, 최대 3개 |
| PR 제목 | 1줄, 최대 80자 | 80자 초과 시 잘라냄 |
| PR 본문 | `## Why` / `## What` / `## How to Test` + 섹션별 bullet 1개 이상 | 빈 섹션은 기본 bullet로 채우고 `WARN` 표시, 최종 본문을 정규식으로 다시 검사 |

프롬프트에서도 같은 규칙과 JSON 출력 스키마(`{"title", "body", ...}`)를 지정해서, 처음부터 규칙에 맞는 응답이 나오도록 유도합니다 (`ai_gitgen/prompts.py`).

## 6. 주의사항 (운영 관점)

### 민감정보 포함 가능성과 대응 (safe-mode)

> `git diff`에는 API Key, 비밀번호, 이메일 같은 개인정보가 섞일 수 있습니다. 그래서 safe-mode를 **기본으로 켜 두고**, 외부 API로 보내기 전에 diff를 가공합니다.

1. **민감 파일 제외** - `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `id_rsa*`, `*secret*`, `*credentials*` 파일은 diff 내용을 보내지 않고 파일 이름만 남깁니다.
2. **패턴 마스킹 (A)** - 아래 값을 `[MASKED:종류]`로 바꿉니다.
   - `sk-...` 형태 API Key, GitHub 토큰(`ghp_...`), AWS Access Key(`AKIA...`), Google API Key(`AIza...`), JWT, PEM 개인키 블록
   - `api_key = "..."`, `password: ...`, `token=...` 같은 비밀값 대입
   - 이메일, 휴대전화 번호, 주민등록번호
3. **전송량 제한 (B)** - 최대 **10개 파일**, 최대 **200줄**까지만 보냅니다. 나머지는 생략했다는 표시만 남깁니다.

`--no-safe-mode`로 끌 수 있지만, 이때도 비용 보호를 위해 3000줄 상한은 유지됩니다. 마스킹은 정규식 기반이라 모든 비밀값을 잡는다고 보장할 수 없으니, 민감한 저장소에서는 실행 전에 `git diff`를 직접 확인하세요.

### 비용 / 요청 횟수 제한 및 권장 사용법

> 실행 1회당 AI API 호출은 **정확히 1회**이고, 실패해도 자동 재시도하지 않습니다. 호출 횟수와 입력/출력 토큰 수는 매번 로그에 찍힙니다.

- 변경 사항이 없거나 API Key가 없으면 API를 호출하지 않고 끝납니다.
- 작은 단위로 `git add` 한 뒤 `commit`을 실행하면 diff가 작아져 비용이 줄고, 요약도 정확해집니다.
- 기본 모델은 비용이 낮은 `gpt-4.1-mini`입니다. 큰 모델은 필요할 때만 `--model`로 지정하세요.
- `--max-tokens`는 응답 길이 상한이자 비용 상한입니다. 커밋/PR 초안은 기본값 800이면 충분합니다.
- 429(요청 한도 초과) 오류가 나면 잠시 기다렸다 다시 실행하고, OpenAI 대시보드에서 사용량 한도를 설정해 두는 것을 권장합니다.

---

## 프로젝트 구조

```
ai-commit-pr-generator/
├── main.py                 # 진입점 (Python 3.10 버전 확인)
├── .env.example            # 환경변수 템플릿 (.env 로 복사해서 사용)
└── ai_gitgen/
    ├── cli.py              # 명령/옵션 파싱, 전체 흐름 제어, 로그 출력
    ├── config.py           # .env 로딩, 기본값
    ├── git_collector.py    # git status / git diff 수집, 루트 확인
    ├── safe_mode.py        # 민감 파일 제외, 마스킹, 파일/줄 수 제한
    ├── prompts.py          # system/user 프롬프트 구성
    ├── ai_client.py        # OpenAI Chat Completions REST 호출, 예외 처리
    └── formatter.py        # JSON 파싱, 길이/템플릿 검증, 구획 출력
```

## 동작 원리 요약

| 주제 | 설명 |
|---|---|
| REST API 연동 | `urllib`로 `POST /v1/chat/completions`에 JSON 요청을 보냅니다. `Authorization: Bearer <AI_API_KEY>` 헤더로 인증하고, HTTP 상태 코드와 응답의 `error.message`를 읽어 원인별 오류 메시지로 바꿉니다 (`ai_client.py`). |
| 파라미터 | `temperature`는 무작위성입니다. 커밋 메시지는 일관성이 중요해 0.3을 기본으로 둡니다. `max_tokens`는 응답 길이 상한이고, 부족하면 `finish_reason=length`로 잘린 것을 감지해 안내합니다. |
| Git 연결 | `subprocess`로 `git status --porcelain --branch`(브랜치, 파일 목록)와 `git diff`(변경 내용)를 실행하고, 결과 텍스트를 프롬프트의 입력으로 넣습니다 (`git_collector.py`). |
| 프롬프트 설계 | system에는 역할, Conventional Commits/PR 템플릿 규칙, 길이 제한, "diff에 없는 내용 금지", JSON 스키마를 넣습니다. user에는 브랜치, diff 범위, 변경 이유(`--context`), 파일 목록, diff를 넣습니다 (`prompts.py`). OpenAI 호환 프록시에서도 동작하도록 `response_format` 같은 확장 파라미터는 쓰지 않고, 프롬프트로 JSON만 답하게 한 뒤 코드에서 JSON 부분을 추출합니다. |
| 검증·다듬기 | 모델이 규칙을 어길 수 있으므로 코드에서 길이를 자르고, 섹션/불릿을 보정하고, 최종 결과를 다시 검사해 `OK/WARN`으로 보여 줍니다 (`formatter.py`). |
