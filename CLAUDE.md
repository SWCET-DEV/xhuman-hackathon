# XHuman — 해커톤 구현 지침

이 파일은 해커톤 당일 Claude Code가 가장 먼저 읽는 지침이다. 짧게 유지한다.

## 무엇을 만드는가

Claude Code 개발 세션 기록(JSONL)에서 "왜"(결정, 이유, 버린 대안)를 근거 인용과 함께 뽑아 Python 함수에 연결하고, 질문 3개로 사용자의 이해도를 측정한 뒤 모르는 부분만 채워 주는 로컬 CLI `xh`.

- 상세 설계: [docs/design.md](docs/design.md)
- 기획: [docs/proposal.md](docs/proposal.md)

## 범위: 이 문서가 설계서보다 우선한다

설계서는 전체 그림이다. **이번 구현 범위는 아래 표가 정한다.** 설계서에 있어도 아래에서 "제외"면 만들지 않는다.

| 구분 | 기능 |
|---|---|
| 필수 | 세션 수집, 코드 색인·AST 해시, 작성 출처(완전 일치만), 위험 태그 3종, 결정 추출·인용 검증·주체 분류(보류 후 반영 포함)·연결, 테스트 변경 감지(`assertion_changed`만), 질문 생성(미리 생성)·채점·상환·재확인, 커버리지, 만료, `xh ingest/scan/why/status/check/report`, 정적 HTML 리포트, 리플레이 모드 |
| 선택 (16시에 일정이 앞설 때만) | OpenAI 호환 백엔드(`grade`에만 연결) |
| 제외 | 인수인계 내보내기(`xh export`, 다음 단계), 리뷰 리허설, SessionEnd 훅, 사내 OSS 실제 연결, 웹 퀴즈, `ai_then_human` 유사도 분류, 위험 규칙 TOML, `test_removed/skipped/added`, 증분 읽기(`last_offset`) |

일정과 단계별 작업은 [docs/build-plan.md](docs/build-plan.md), 모듈 간 계약은 [docs/contracts.md](docs/contracts.md), 완료 기준인 시연 대본은 [docs/demo-script.md](docs/demo-script.md)를 따른다.

## 디렉터리

```
xhuman/            패키지 (설계서 10장 구조에서 hook.py, rehearse 제외)
xhuman/llm/        base.py(인터페이스·캐시·리플레이), claude_cli.py, fake.py
xhuman/prompts/    docs/prompts/*.md를 그대로 복사해 사용
tests/             pytest
tests/fixtures/    시연 세션 JSONL, 샘플 프로젝트, 가짜 백엔드 응답 JSON
```

## 코딩 규칙

- Python 3.11 이상, **런타임은 표준 라이브러리만**. 개발 의존성은 `pytest`만.
- 데이터는 `~/.xhuman/` 아래에만 쓴다(테스트에서는 `XHUMAN_HOME` 환경 변수로 임시 폴더). **사용자 프로젝트 폴더에는 아무것도 쓰지 않는다.**
- AI 호출은 반드시 `xhuman.llm`을 거친다. 다른 모듈에서 `subprocess`로 `claude`를 직접 부르지 않는다.
- 해시, 작성 출처, 위험 태그, 결정 주체, 점수, 커버리지는 프로그램이 계산한다. AI는 추출, 질문 생성, 핵심 포인트 충족 판정, 상환 설명만 한다.
- 모든 파이프라인 단계는 멱등이어야 한다. 같은 입력으로 두 번 돌려도 DB 결과가 같아야 한다.
- 사용자에게 보이는 문구는 한국어.

## 바꾸면 안 되는 것

- [docs/contracts.md](docs/contracts.md)의 DB 스키마, `LLMBackend` 인터페이스, 작업별 JSON 스키마. 바꿔야 하면 먼저 contracts.md를 고치고 이유를 커밋 메시지에 쓴다.
- `docs/prompts/*.md`의 프롬프트 본문. 고치면 맨 위 버전을 올린다.

## 작업 방식

- 한 번에 모듈 하나. 완료 기준은 "해당 테스트 통과"다. [docs/test-cases.md](docs/test-cases.md)의 시나리오로 테스트를 먼저 쓴다.
- 개발 중 AI 호출은 `FakeBackend`로 한다. 실제 `claude -p`는 통합 체크포인트에서만 쓴다.
- 실측 사실과 함정은 [docs/verified-facts.md](docs/verified-facts.md)를 먼저 본다. 세션 JSONL 형식을 추측하지 않는다.
- **사전 작성 코드는 반입하지 않는다.** 모든 코드는 당일 문서만 보고 새로 쓴다. 파싱·인용 검증·주체 분류의 세부 규칙은 [docs/contracts.md](docs/contracts.md) 5장에 있다. 반입 목록은 [docs/carry-in.md](docs/carry-in.md).
- 단계가 끝나면 커밋한다. 커밋 메시지는 한국어 한 줄 + 필요하면 본문.

## 자주 쓰는 명령

```bash
pip install -e .[dev]
pytest -q
xh ingest --session tests/fixtures/demo_session.jsonl --project tests/fixtures/demo-payment
xh status
xh check
xh why payment/retry.py::charge_with_retry
xh report
XHUMAN_REPLAY=1 xh check --answers tests/fixtures/demo_answers.json   # 시연용
```
