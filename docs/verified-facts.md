# 실측 사실과 함정

Claude Code가 오래된 지식으로 추측하지 않도록, 직접 확인한 사실만 적는다. 확인 날짜와 버전을 같이 적고, 확인하지 못한 것은 "미검증"으로 표시한다.

## 1. 세션 기록 (JSONL)

확인: Claude Code 2.1.311, 3턴 시연 세션 기록(사전 검증 때 사용. 화요일 새 녹화본은 `tests/fixtures/demo_session.jsonl`)

- 위치: `~/.claude/projects/<작업 경로의 영숫자 외 문자를 -로 바꾼 폴더>/<session_id>.jsonl`
- 한 줄에 레코드 하나. 공통 필드: `type`, `uuid`, `parentUuid`, `timestamp`, `sessionId`, `isSidechain`, `cwd`, `version`, `message`
- 공식 문서로 고정된 형식이 아니다. 모르는 `type`·필드는 건너뛴다. `isMeta`가 참인 레코드도 건너뛴다.

| 레코드 | 구분 |
|---|---|
| 사용자 발화 | `type == "user"`, `message.content`가 문자열 또는 `text` 블록 목록 |
| 사람이 쓰지 않은 사용자 레코드 | 텍스트가 `<command-`, `<local-command`, `<system-reminder`, `Caveat:`로 시작 → 제외 |
| AI 발화 | `type == "assistant"`, `message.content[]`의 `text` 블록 |
| AI 도구 호출 | `type == "assistant"`, `message.content[]`의 `tool_use` 블록(`id`, `name`, `input`) |
| 도구 결과 | `type == "user"`, `message.content[]`에 `tool_result` 블록(`tool_use_id`, `is_error`), 레코드에 `toolUseResult` |

**2.1.322 재확인(11/10 녹화본, Windows):** 위 구조 그대로. `Write`는 새 파일이면 `type: create`(`structuredPatch` 빈 목록), 기존 파일이면 `type: update`(`structuredPatch` 있음). `Edit` 결과 키는 `filePath`, `oldString`, `newString`, `originalFile`, `replaceAll`, `structuredPatch`, `userModified`. 새로 보인 레코드 `type`: `attachment`(훅 출력·사용자 컨텍스트, 이메일이 들어 있었음), `api-request`·`api-request-blob`·`api-request-shape`(요청 원문 포함), `session-owner`, `cost-state`, `file-history-delta`, `tools-used`, `atis-latch`, `ai-title`. 모두 건너뛴다. **이 레코드들에는 전역 CLAUDE.md 본문과 이메일이 들어 있어 픽스처에서는 지웠다**(픽스처에는 `user`·`assistant`만 남김). 스킬 본문은 `isMeta: true`인 사용자 레코드로 들어온다(건너뜀). Windows에서는 셸 도구 이름이 `PowerShell`이고 경로 구분자가 `\`다.

편집 도구는 `Write`, `Edit`, `MultiEdit`. `toolUseResult`:

- `structuredPatch[]`: `oldStart`, `oldLines`, `newStart`, `newLines`, `lines`(`+`/`-`/공백 접두사)
- `Write`로 새 파일: `type == "create"`, `content`
- `Edit`: `originalFile`(편집 전 전체 내용), `oldString`, `newString`, `userModified`
- 도구 결과와 호출은 `tool_use_id` ↔ `tool_use.id`로 짝을 맞춘다. `parentUuid`보다 확실하다. 세부 규칙은 [contracts.md](contracts.md) 5.1.

## 2. `claude -p` 호출

확인: Claude Code 2.1.311(설계 시), 2.1.319에서 `--help`로 플래그 존재 확인

```
claude -p "<지시문>" --model <sonnet|haiku> --tools "" --no-session-persistence \
  --setting-sources "" --output-format json --json-schema '<스키마>'
```

- 긴 입력은 표준 입력으로.
- 결과 JSON: `structured_output`(스키마 결과), `is_error`, `result`, `duration_ms`, `total_cost_usd`. `structured_output`이 없으면 `result`를 JSON으로 파싱해 본다.
- 자식 프로세스 환경에서 `CLAUDE_CODE_SESSION_ID`를 지우고 `XHUMAN_CHILD=1`을 넣는다. Claude Code 안에서 띄우면 부모 세션 ID를 이어받는 것을 확인했다.
- `--bare`는 API 키 인증 전용이다. **이번 환경은 Claude API 키가 없고 구독 로그인만 있으므로 쓰지 않는다.**
- 실측 소요: 짧은 대화 추출 약 6초, 3턴 세션 추출 1회 약 15초(sonnet).

## 3. 프로토타입 결과

사전 검증 결과(extract-v0.3, sonnet). 프로토타입 코드와 이 결과 파일은 반입하지 않는다. 목요일 비교 기준은 [session-script.md](session-script.md) 3장 기준표

- 3턴 세션 → 결정 12개, 근거 인용 19/19 원문 일치, 제외 0
- 주체: 포괄 수락 8, AI 단독 3, 사람 지시 1
- 같은 세션이 실행에 따라 6/7/12개로 나뉨(프롬프트 버전도 바뀐 상태라 순수 편차는 미측정)

### 11/10 녹화본 추출 편차 (extract-v0.3, sonnet, 같은 입력 3회)

| 회 | 결정 수 | 보류 | 포괄 | AI 단독 | 사람 지시 | 인용 제외 |
|---|---|---|---|---|---|---|
| 1 | 17 | 3(오탐 1) | 4 | 7 | 3 | 0 |
| 2 | 12 | 1(타임아웃 기본값과 ValueError를 한 결정으로 묶음) | 3 | 5 | 3 | 0 |
| 3 | 15 | 2 | 4 | 6 | 3 | 0 |

결정 수는 12~17개로 흔들리지만 타임아웃 보류는 3회 모두 나왔고, 사람 지시 3개와 인용 제외 0은 같았다. 보류 오탐은 1회에만 나왔다. 발표에서는 "같은 세션이 12~17개로 나뉜다"고 말하고, 시연은 캐시로 고정한다.

### 11/10 녹화본 채점 편차 (grade-v0.3, haiku, 같은 입력)

| 질문 | 5회 결과(충족 포인트) | 판정 |
|---|---|---|
| Q1 테스트 변경 | [0,2] 2회, [0] 3회 | 5회 모두 partial |
| Q2 보류(타임아웃) | [0] 5회 | 5회 모두 partial |
| Q3 `record_payment` "모르겠어요" | [] 5회 | 5회 모두 unknown |
| Q2 재확인 | [0,1] 5회 | 5회 모두 understood |

포인트 단위로는 흔들리지만(Q1 포인트 2: "의도적 결정인지 근거 확인"처럼 판단이 들어간 포인트) 시연 판정은 5회 모두 같았다. 시연은 캐시로 고정하므로 화면에는 영향 없음. 정밀도 주장은 하지 않는다.

### 11/10 채점 검증 (답변 15개, haiku, 5회, 별도 스레드)

- 일관성: 15개 중 14개가 5회 모두 같은 결과. 흔들린 1개는 원칙형 포인트.
- 사람(발표자) 원래 판정과의 일치: 포인트 84.0%, 최종 판정 74.7%.
- 판정을 다시 본 뒤 고친 정답지 기준: 포인트 95~97%, 판정 94.7%. **순환 요소가 있다**(사람 판정 일부를 AI 판정 쪽으로 고친 뒤 계산). 반드시 84%/75%와 함께 적는다.
- 한계: 표본 15개, 답변을 Claude가 작성(Claude가 판정하기 쉬운 답이 많았을 수 있음). "95% 정확"이라고 말하지 않는다. "일관성이 높고, 판정이 갈린 곳은 포인트 문장이 애매한 곳이었다"까지만 말한다.
- 판정이 갈린 원인(원칙형 포인트, 주장 두 개짜리 포인트)은 question-v0.4~v0.6 규칙 6으로 대응(v0.6에 시연과 무관한 좋은 예·나쁜 예). 자료: 프로젝트 폴더 `exaone/grading-findings.md`

## 4. 알려진 함정

| 함정 | 내용 |
|---|---|
| 픽스처 테스트 실패 | `fixtures/demo-payment`에서 `PYTHONPATH=. pytest` 결과 20 통과 / 1 실패(`test_deadline_stops_retrying`). 가짜 시계 순서가 실제 `monotonic` 호출 순서와 맞지 않음. `PYTHONPATH` 없이는 수집조차 안 됨 |
| 녹화 환경(11/10) | Windows, 명령 프롬프트(cmd), Claude Code **2.1.322**(녹화 직전 2.1.308에서 업데이트), pytest 9.2.0. 형식 확인은 2.1.311 기준이라 녹화본으로 레코드 형식을 다시 확인한다. 녹화가 끝날 때까지 업데이트 금지. 목요일 버전이 더 높아도 무방(당일은 녹화본을 읽기만 함, `claude -p` 옵션만 확인). 대화 기록 경로에 사번이 든 Windows 홈 경로가 남으므로 정리 단계에서 치환 |
| Windows의 `claude` 실행 파일(11/11, 미확인) | 지금까지 `claude -p --json-schema` 검증은 Linux에서만 했다. Windows에서 `claude`가 `.cmd` 래퍼이면 `subprocess`로 JSON 스키마를 인자로 넘길 때 따옴표가 깨질 수 있다. 수요일 점검에서 실행 파일 종류와 스키마 호출 성공 여부를 확인한다. 깨지면 `claude_cli.py`에서 래퍼 대신 실제 실행 파일을 찾아 부르거나, 스키마 없이 호출하고 `result`를 JSON으로 파싱하는 경로를 쓴다 |
| 사내망 HTTPS(11/10) | 녹화 PC(Windows, Python 3.15)에서 Python `urllib`로 외부 API(K-EXAONE)를 부르면 `CERTIFICATE_VERIFY_FAILED: Basic Constraints of CA cert not marked critical`. 사내 프록시가 내미는 CA 인증서가 Python 3.13+의 엄격 검사에 걸리는 것으로 보인다. 해커톤 PC는 대외망이라(11/10 발표자 확인) 이 문제는 녹화 PC 환경에 한정될 가능성이 높다. 수요일 점검에서 해커톤 PC로 확인한다. `claude` CLI는 이 영향을 받지 않았다. 검증을 약하게 하는 우회는 보안 판단이 필요하므로 기본으로 넣지 않는다 |
| 버전 드리프트 | 설계 시 2.1.311, 2026-11-09 기준 2.1.319. 해커톤 전 버전을 고정한다 |
| 인용 정규화 | NFC + 연속 공백 하나로 + 앞뒤 따옴표 제거 후 부분 문자열 비교. 8자 미만은 인정 안 함 |
| 짧은 수락 표현 | 다음 단어 중 하나로 시작하면 짧은 수락: 좋아, 좋습니다, 좋네, 좋아요, ㅇㅋ, 오케이, ok, okay, ㅇㅇ, 네, 응, 그래, 그렇게, 진행, 고고, lgtm, yes, sure. "네"·"응"으로 시작하는 다른 말도 걸리는 한계가 있다 |

## 5. 미검증 (해커톤 전에 확인하거나 쓰지 않는다)

| 항목 | 상태 | 이번 범위에서 |
|---|---|---|
| `userModified == true`의 정확한 의미 | 미검증 | 쓰지 않음(`ai_then_human` 제외) |
| SessionEnd 훅 입력 필드(`transcript_path`, `cwd`) | 미검증 | 쓰지 않음(훅 제외) |
| `--setting-sources ""` 빈 값이 모든 설정을 끄는지 | 미검증 | 프로토타입에서 오류 없이 동작. 훅이 없으니 영향 작음 |
| `/compact` 이후 레코드 형식 | 미검증 | 시연 세션에서 쓰지 않음 |
