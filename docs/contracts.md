# 모듈 간 계약 (해커톤 축소판)

설계서 4·5·6·8장에서 이번 범위에 쓰는 것만 모았다. 해커톤 중에는 이 문서를 기준으로 한다. 설계서와 다르면 이 문서가 우선이다.

## 1. 저장소

- 경로: `$XHUMAN_HOME/xhuman.db` (기본 `~/.xhuman/xhuman.db`), 파일 권한 600
- **LLM 캐시는 별도 파일** `$XHUMAN_HOME/llm_cache.db`(11/11 변경). 측정 DB(`xhuman.db`)를 지우고 다시 ingest해도 리플레이 캐시가 남아야 시연 초기화가 된다. 캐시 파일은 `xhuman.llm.base`만 열고 닫는다(S0에서 `store.py` 없이 만들 수 있게)
- SQLite, 외래 키 켬. 스키마 버전은 `PRAGMA user_version = 1`

### 1.1 테이블 (설계서 4장 대비 변경점만 표시)

| 테이블 | 쓰는 컬럼 | 설계서 대비 |
|---|---|---|
| `projects` | `project_id`, `root_path`, `created_at` | 동일 |
| `sessions` | `session_id`, `project_id`, `transcript`, `cc_version`, `ingested_at` | `last_offset` 제외 (매번 전체 재수집) |
| `messages` | `uuid`, `session_id`, `parent_uuid`, `role`, `ts`, `text`, `is_sidechain`, **`ref`** | `ref` 추가: 추출 입력의 표식 `m:<uuid 앞 8자리>` |
| `edits` | `edit_id`, `session_id`, `message_uuid`, `tool`, `file_path`, `patch_json`, `added_lines`, **`removed_lines`**, **`original_file`**, `user_modified`, `is_test_file`, `ts`, **`ref`** | `removed_lines`, `original_file`(test_watch용), `ref`(`e:<번호>`) 추가 |
| `units` | `unit_id`, `project_id`, `file_path`, `qualname`, `kind`, `line_start`, `line_end`, `content_hash`, `ai_lines`, `human_lines`, `risk_level`, `risk_tags`, `status`, `updated_at` | `ai_human_lines` 제외 |
| `decisions` | 설계서와 동일 + **`decided_by_note`**, `decided_by`에 **`deferred`** 추가 | 분류 근거 문구 저장(리포트 표시용). `deferred` = 사용자가 미뤘는데 코드에 반영된 결정(설계서 5.8 첫 행) |
| `decision_evidence` | 설계서와 동일 + **`verified`**(0/1) | 검증 실패 인용도 남겨 low confidence 표시 |
| `decision_units` | 동일 | |
| `test_events` | 동일. `kind`는 `assertion_changed`만 기록 | 이벤트 단위와 `unit_id`는 3장 `test_watch` 규칙(11/11) |
| `questions` | 동일 + **`missed_from`**(재확인 질문이면 원 질문 ID) + **`unit_hash`**(생성 시점 `content_hash`) | **`question_id`는 결정적으로 만든다(11/11):** `q_` + `sha256(unit_id, qtype, unit_hash, test_event_id 또는 빈 문자열)` 앞 12자리. 재확인 질문은 `<원 질문 ID>-r`. 같은 입력이면 초기화 뒤에도 ID가 같아 채점 캐시와 `--answers` 키가 맞는다. 단위 해시가 바뀌면 ID가 달라지므로 옛 질문은 다시 쓰지 않는다(`pick_targets`는 `unit_hash`가 현재 해시와 같은 질문만 쓰고, 없으면 새로 생성) |
| `understanding` | 동일 | |
| `llm_cache` | 동일. 단 `xhuman.db`가 아니라 `llm_cache.db`에 둔다 | 위 경로 참고 |

### 1.2 이해 상태 규칙 (설계서 6.3·6.4·6.6의 모호한 부분 확정)

1. 질문 하나의 판정: 핵심 포인트 전부 충족 → `understood`, 1개 이상 → `partial`, 0개 → `unknown`.
   **판정은 `matched`만으로 계산하고 `missed`를 믿지 않는다(11/10 추가).** 포인트 수 N에 대해 충족 = `matched` ∩ {0..N-1} − `missed`. `matched`·`missed` 어디에도 없는 번호는 미충족, 양쪽에 다 있는 번호도 미충족, 범위 밖 번호는 버린다. 누락·중복·범위 밖이 있으면 경고를 로그에 남긴다. "`missed`가 비었으면 understood"로 짜면 모델이 포인트 하나를 빠뜨렸을 때 틀린 답이 통과한다(K-EXAONE 동시 3회 중 2회 발생, 엔진과 무관한 채점 코드 결함).
2. **상환 후 재확인**: 재확인 질문의 핵심 포인트는 원 질문에서 놓친 포인트만으로 만든다(그래서 1~4개. 일반 질문의 2~4개 제한을 재확인 질문에는 적용하지 않는다, 11/11). 재확인에서 그 포인트를 모두 충족하면, 원 질문에서 이미 맞힌 포인트와 합쳐 **원 질문 기준 `understood`**로 본다. 새 `understanding` 레코드(`mode = repay_recheck`, `question_id` = 원 질문 ID)를 추가한다.
3. 단위의 이해 상태 = 그 단위의 `valid` 기록 중 **가장 최근 것**의 `verdict`. 기록이 없으면 `unmeasured`.
4. 단위 해시가 바뀌면 그 단위의 모든 기록을 `expired`로 바꾸고 상태는 `expired`.
5. 커버리지 대상: AI 작성 비율 ≥ 0.3인 `active` 단위 중 **테스트 파일이 아닌 것**(11/10 추가). 시연 세션은 단위 51개 중 42개가 테스트 코드라, 테스트를 넣으면 커버리지가 테스트 이해도로 채워진다. 테스트 변경 질문은 그대로 묻지만 커버리지에는 넣지 않는다.
6. 위험 가중 커버리지 = Σ w·[understood] / Σ w, w = 1(낮음) / 2(중간) / 4(높음). 단순 커버리지는 w = 1.
7. **질문 고르기의 테스트 변경 상한(11/10 추가):** 열린 테스트 변경 이벤트가 있는 단위는 한 번의 `xh check`에 **1개만** 맨 앞에 둔다. 고르는 순서는 이벤트 시각, 같으면 파일 안 줄 번호. 나머지 2개는 설계서 6.1의 priority로 고르고(같으면 연결된 결정 수가 많은 단위, 그래도 같으면 `unit_id` 사전순), 남은 테스트 변경은 다음 `check`로 넘긴다. 설계서대로 테스트 변경을 모두 맨 앞에 두면 AI가 assert를 여러 개 고친 세션에서 질문 3개가 전부 같은 종류의 테스트 질문이 된다.

예: 대상 단위 5개, 위험도 높음 2(w=4)·낮음 3(w=1). 낮음 3개만 understood면 단순 3/5 = 60%, 위험 가중 3/11 = 27%. 높음 하나를 더 이해하면 위험 가중 7/11 = 64%.

## 2. AI 호출

### 2.1 인터페이스

`LLMBackend.complete_json(task, prompt, schema, stdin_text) -> dict`

| 인자 | 의미 |
|---|---|
| `task` | `extract` / `question` / `grade` / `repay` |
| `prompt` | `xhuman/prompts/<task>.md`의 **"지시문" 코드 블록 안만**(11/11 수정). 버전 줄, 입력 형식, 출력 예, 검증 메모는 넣지 않는다. 출력 예는 시연과 같은 결제 예라 모델에 넘기면 질문이 예시를 베낀다(test-cases T0-6) |
| `schema` | 아래 2.3의 JSON 스키마 |
| `stdin_text` | 세션 압축 텍스트, 코드, 답변 등 긴 입력 |

공통 동작(`base.py`가 구현체 앞에서 처리):

- 캐시 키 = `sha256(backend, task, prompt_ver, model, prompt, stdin_text)`. 캐시가 있으면 호출하지 않는다. `backend`(`claude`/`fake`/`openai`)를 넣는 이유: 가짜 응답이 실제 실행(C1)이나 리플레이에 섞이지 않게 한다(11/11). 리플레이 모드는 `backend = claude` 캐시만 읽는다(`XHUMAN_BACKEND`로 바꾸지 않았으면).
- 응답이 스키마의 `required`를 만족하지 않으면 1회 재시도, 그래도 실패하면 `LLMError`.
- **리플레이 모드**: `XHUMAN_REPLAY=1`이면 캐시만 쓴다. 캐시가 없으면 호출하지 않고 `LLMError("리플레이 캐시 없음: task=..., key=...")`로 즉시 실패한다. 조용히 다른 응답을 지어내지 않는다.

### 2.2 구현체

| 이름 | 설정값 | 내용 |
|---|---|---|
| `ClaudeCLIBackend` | `claude` (기본) | `verified-facts.md` 2장의 명령. 구독 로그인 사용, `--bare` 불가 |
| `FakeBackend` | `fake` | `tests/fixtures/llm/<task>/*.json`에서 응답을 읽음(목요일에 손으로 작성). 입력 해시로 고르고 없으면 `default.json` |
| `OpenAICompatBackend` | `openai` (선택. 후보: 행사 제공 OpenAI 크레딧. API를 실제로 쓸 수 있고 C1에서 `grade` 판정이 Claude와 같을 때만. **K-EXAONE 2.5는 11/10 확인 후 쓰지 않기로 함**: 판정은 Claude와 같았지만 피드백이 정답을 흘리고 초당 1회 제한이 있음) | `/v1/chat/completions` + `response_format` JSON 스키마. 사내 OSS와 같은 코드 |

작업별 백엔드·모델은 환경 변수 `XHUMAN_BACKEND`(전체) 또는 `XHUMAN_BACKEND_GRADE`처럼 작업별로 덮어쓴다. 기본 모델: `extract`·`question` = sonnet, `grade`·`repay` = haiku.

### 2.3 작업별 출력 스키마

**extract** (`extract-v0.3`에서 검증한 형식. 설계서 5.6의 `quotes/message_ref`가 아니라 `evidence/ref`를 쓴다)

| 필드 | 형식 |
|---|---|
| `decisions[]` | 배열 |
| `.summary` | 문자열, 한국어 한 문장 |
| `.reason` | 문자열. 근거 없으면 `"기록에 근거 없음"` |
| `.alternatives[]` | `{option, why_rejected}` |
| `.level` | `structure` / `implementation` |
| `.evidence[]` | `{ref, text}`. `ref`는 `m:xxxxxxxx` 또는 `e:N`, `text`는 원문 10~200자 |
| `.related_files[]`, `.related_symbols[]` | 문자열 배열 |

**question**

| 필드 | 형식 |
|---|---|
| `question` | 문자열 |
| `qtype` | `how` / `why` / `test` |
| `key_points[]` | 문자열 2~4개, 서로 겹치지 않음(재확인 질문은 repay의 `recheck_key_points`를 그대로 저장하므로 1~4개) |

**grade** (답변 3개를 한 번에)

| 필드 | 형식 |
|---|---|
| `results[]` | 질문 순서대로 |
| `.question_id` | 입력으로 받은 ID 그대로 |
| `.matched[]`, `.missed[]` | 핵심 포인트 번호(0부터) |
| `.feedback` | 2문장 이내 |

**repay**

| 필드 | 형식 |
|---|---|
| `flow` | 동작 흐름 한 문장 |
| `decisions[]` | `{text, quote}` 0~3개(11/11: 결정 기록이 없는 함수면 빈 배열). `quote`는 저장된 근거 인용 중 하나를 그대로. JSON 스키마에 `minItems`를 두지 않는다 |
| `alternative` | 버린 대안 한 문장(없으면 빈 문자열) |
| `recheck_question` | 놓친 포인트를 다르게 묻는 질문 |
| `recheck_key_points[]` | 놓친 포인트와 1:1 |

## 3. 모듈 함수 계약 (시그니처 수준)

| 모듈 | 함수 | 입력 → 출력 |
|---|---|---|
| `ingest` | `parse_session(path, project_root)` | JSONL 경로 → `Item` 목록(발화·편집, 순서 유지, 비밀값 가림) |
| | `store_session(db, items, meta)` | DB에 `sessions`, `messages`, `edits` 저장 |
| `codeindex` | `index_project(root)` | Git 추적 `.py` → 단위 목록(`unit_id`, 줄 범위, `content_hash`). 단위는 모듈 수준 함수·클래스와 클래스의 메서드다. **함수 안의 중첩 함수·클래스는 단위로 세지 않는다**(11/11. 시연 샘플은 그래서 51개, 테스트 42개. 중첩까지 세면 52개) |
| | `unit_hash(node)` | AST 노드 → 해시. 클래스는 메서드 본문 제외 골격 |
| `provenance` | `classify_lines(file_text, ai_added_lines)` | 줄별 `ai` / `human` (공백 무시 완전 일치, 빈 줄·닫는 괄호 제외) |
| `risk` | `tag_unit(unit_node, file_path)` | → `(risk_level, risk_tags)`. 태그는 `payment`, `db_write`, `auth`만. `db_write`의 SQL 검사는 `execute`/`executemany` 첫 인자가 문자열 리터럴이거나, **같은 파일 모듈 수준에서 문자열 상수로 대입된 이름**이면 그 값을 본다(11/11: 시연 `record_payment`가 `_INSERT_PAYMENT` 상수와 `with conn:`을 씀). **테스트 파일 단위에는 태그를 붙이지 않는다**(테스트 함수 이름의 `payment` 때문에 높음이 되는 것을 막음). 이름 규칙(`payment`, `auth`)은 함수·메서드 이름에만 적용하고 클래스 이름에는 적용하지 않는다(11/10) |
| `test_watch` | `detect(edits)` | 원래 있던 테스트 파일의 `Edit` → `assertion_changed` 이벤트 목록. **이벤트 단위(11/11): 조건을 충족한 `Edit` 하나에 이벤트 하나.** `before_text`/`after_text`는 그 편집에서 지워진·추가된 assert 줄 전부. `unit_id`: 편집 직후 파일(`original_file`의 `old_string`을 `new_string`으로 한 번 바꾼 것)을 `ast`로 파싱해 **처음 추가된 assert 줄을 감싸는 함수의 이름**을 구하고(이름이 바뀌었으면 바뀐 뒤 이름), 그 이름으로 최종 색인에서 찾은 단위. 최종 코드에 그 함수가 없으면 이벤트를 버린다. 11/11 녹화본에 적용하면 이벤트 6개이고, 단위는 시각순으로 `test_gives_up_after_exactly_two_attempts_on_transient_failure`(함수 4개를 한꺼번에 바꾼 첫 편집), `test_backs_off_exponentially_between_attempts`, `test_backoff_is_drawn_from_zero_to_the_exponential_cap`, `test_skips_remaining_attempts_when_next_one_would_exceed_deadline`, `test_unknown_outcome_carries_last_error_for_reconciliation`, `test_raises_payment_declined_without_retry_on_any_4xx`다. 모두 최종 코드에 있다. "원래 있던"은 그 편집 직전에 파일이 있었다는 뜻이다(`Edit`이면 해당, `Write`의 `type: create`는 제외). 같은 세션 앞부분에서 `Write`로 만든 테스트 파일이라도 뒤의 `Edit`은 감지한다(11/10 명확화. 시연 세션이 이 경우) |
| `decisions` | `extract(items, backend)` → `verify(...)` → `classify(...)` → `link(...)` | 5장 규칙대로 새로 작성(프로토타입은 반입 불가). DB 저장은 `store_decisions` |
| `quiz` | `pick_targets(db, n=3)` | 설계서 6.1 우선순위. 열린 테스트 이벤트가 맨 앞, 같은 단위 2개 금지 |
| | `pregenerate(db, backend)` | ingest 직후 상위 대상 질문을 미리 생성해 저장 |
| | `grade(db, backend, answers)` | 답변 → `understanding` 레코드 |
| `repay` | `explain(db, backend, record)` → `recheck(...)` | 1.2의 규칙 2 적용 |
| `coverage` | `compute(db, project)` | → `{simple, weighted, by_unit[]}` |
| `report` | `render(db, project, out_dir)` | 정적 HTML 1장 |
| `cli` | `main(argv)` | 이 문서 4장 명령 |

## 4. CLI 입출력

| 명령 | 출력 예 |
|---|---|
| `xh ingest --session P --project R` | `발화 8+11, 편집 14 → 결정 12 (제외 0, 확신 낮음 1), 테스트 변경 6, 질문 6개 미리 생성`(숫자는 형식 예시. 테스트 변경 6은 11/11 녹화본 기준) |
| `xh status` | 커버리지 두 줄 + 이해 부채 상위 5개 표 + 열린 테스트 변경 + 아직 확인하지 않은 보류 후 반영 결정 수 |
| `xh check [--answers FILE]` | 질문 3개 → 답 입력(또는 파일) → 질문별 판정·피드백 → "상환할까요? [Y/n]" → 설명 → 재확인 → 점수 전후 → 마지막 줄 `이번에 질문하지 않은 함수의 결정: 보류 후 반영 a · AI 단독 b · 포괄 수락 c (위험 함수 n개)`. 다 확인하지 않았다는 사실을 숨기지 않기 위한 줄이며 프로그램이 계산한다. 질문한 함수에 연결된 결정은 모두 세지 않는다(질문이 그중 어느 결정을 물었는지는 기록하지 않으므로). 이름도 그 범위대로 쓴다(11/11) |
| `xh why <파일::함수>` | 결정별: 요약 / 주체 배지 / 이유 / 버린 대안 / 근거 인용(✓ 원문 일치) |
| `xh report` | `$XHUMAN_HOME/report/index.html`(기본 `~/.xhuman/report/index.html`) 생성 후 경로 출력(가능하면 브라우저 열기) |
| `xh scan [--project R]` | 해시를 다시 계산해 `만료 N개`를 출력(11/11 추가. 만료 기능에 필요한데 표에 빠져 있었다). `--project`를 생략하면 DB에 저장된 프로젝트(`projects.root_path`)를 쓴다. 시연 대본은 인자 없이 `xh scan`으로 부른다. `status`·`check`·`why`·`report`도 같은 프로젝트를 쓴다 |

`--answers FILE`은 `{"<question_id>": "답변", "<question_id>-r": "재확인 답변", ...}` JSON. 시연에서 답변을 고정해 채점·상환 결과를 캐시와 일치시키는 용도다. 파일이 있으면 입력을 하나도 묻지 않고 아래 규칙으로 끝까지 간다(11/11):

| 상황 | 동작 |
|---|---|
| 질문 ID가 파일에 없음 | 그 질문은 건너뜀(채점·기록 없음). 출력에 `건너뜀` 표시 |
| `partial`/`unknown`이고 `<question_id>-r`이 파일에 있음 | 상환 Y로 보고 설명 → 재확인 질문 출력 → 그 답으로 재확인 채점 |
| `partial`/`unknown`이고 `<question_id>-r`이 없음 | 상환하지 않음(`상환 생략` 표시). 판정은 그대로 기록 |
| 키 이름이 질문 ID가 아님(`_comment` 등) | 무시 |

시연은 Q2(타임아웃)만 재확인 답을 넣는다. Q1(테스트 변경)·Q3은 재확인 키를 넣지 않아 상환하지 않는다. `_comment` 외의 별칭 키(`q_timeout` 등)는 쓰지 않는다. 실제 ID는 `xh check`가 질문 앞에 `[q_xxxxxxxxxxxx]`로 함께 출력하므로 리허설 한 번 뒤 거기서 복사한다(ID가 결정적이라 초기화해도 같다).

## 5. 처음부터 다시 만들 때의 세부 규칙

프로토타입 코드는 해커톤에 반입할 수 없다. 화요일까지 프로토타입으로 맞춰 둔 세부 동작을 목요일에 같은 결과로 다시 만들 수 있도록 **규칙만** 적는다. 코드, 정규식 원문, 테스트 코드는 넣지 않는다. 설계서 5.1·5.6~5.9와 다르면 이 장이 우선이다.

### 5.1 파싱 (`ingest.parse_session`)

| 항목 | 규칙 |
|---|---|
| 건너뛸 레코드 | `type`이 `user`·`assistant`가 아님, `isMeta`가 참, 텍스트가 비었음, 사람이 쓰지 않은 사용자 레코드([verified-facts.md](verified-facts.md) 1장의 네 가지 접두사) |
| 깨진 줄 | 줄 번호를 넣은 경고 한 줄만 남기고 건너뜀 |
| 사용자 레코드 중 도구 결과 | `tool_result` 블록이 하나라도 있으면 발화가 아니다. 블록마다 앞서 나온 `tool_use`와 `tool_use_id`로 짝을 맞춰 편집 항목을 만든다. `is_error`가 참이거나 짝이 없으면 버린다 |
| AI 레코드 | `text` 블록마다 발화 항목 하나. `tool_use` 블록은 이름이 `Write`·`Edit`·`MultiEdit`일 때만 결과를 기다리는 목록에 넣는다 |
| 추가·삭제 줄 (우선순위) | ① `toolUseResult.structuredPatch`의 `+`·`-` 줄 ② 결과의 `type`이 `create`면 `content` 전체 ③ 도구 입력: `Write`는 `content`, `Edit`은 `new_string`(삭제 수는 `old_string` 줄 수), `MultiEdit`은 각 `new_string`을 이어 붙임 |
| 표식(`ref`) | 발화는 `m:` + uuid 앞 8자리, 편집은 `e:` + 1부터 세는 편집 번호. 같은 표식이 이미 있으면 `-2`, `-3`을 붙인다(AI 레코드 하나에 `text` 블록이 여러 개일 때) |
| 턴 번호 | 사람 발화를 만날 때마다 1 증가. 모든 항목에 "그때까지 나온 사람 발화 수"를 단다(포괄 수락 판정에 씀) |
| 경로 | 먼저 `\`를 `/`로 바꾼다(Windows 녹화본 대비). 지정한 프로젝트 루트 또는 레코드의 `cwd` 기준 상대 경로. 둘 다 아니면 원래 경로를 두고, 저장 단계에서 프로젝트 밖으로 보고 뺀다 |
| 비밀값 가리기 | 발화와 편집 텍스트 모두 `[REDACTED]`로 바꾼다. 대상: `sk-` 뒤 16자 이상, GitHub 토큰 접두사(`ghp_`·`gho_`·`ghu_`·`ghs_`·`ghr_`) 뒤 20자 이상, `AKIA` 뒤 대문자·숫자 16자, `api_key`·`secret`·`token`·`password`·`passwd` 다음에 `:`나 `=`와 6자 이상의 값 |

### 5.2 추출 입력 (`decisions.extract`)

| 항목 | 규칙 |
|---|---|
| 발화 한 줄 | `[<ref>\|<user 또는 assistant>] <텍스트>` |
| 편집 | 머리 줄 `[<ref>\|edit <파일> +<추가 수>/-<삭제 수>]` 다음에 추가된 줄. 60줄을 넘으면 60줄까지만 넣고 `... (N줄 생략)` |
| 분할 | 위 형식으로 만든 글자 수 합이 40,000자를 넘기 직전에 끊는다. 다음 덩어리는 앞 덩어리 마지막 2개 항목 중 **편집이 아닌 것**으로 시작한다 |
| 덩어리 결과 합치기 | 덩어리마다 받은 결정 목록을 순서대로 이어 붙인다(중복 제거는 하지 않는다. 겹침이 2개 항목뿐이라 중복이 드묾) |

### 5.3 인용 검증 (`decisions.verify`)

- 정규화: 유니코드 NFC → 연속 공백을 하나로 → 앞뒤 공백 제거. 인용문은 여기에 더해 앞뒤의 따옴표·백틱을 벗긴다.
- AI가 준 `ref`에서 대괄호와 `|` 뒤를 떼어 낸다(`[m:1a2b3c4d|user]` → `m:1a2b3c4d`).
- 8자 미만이면 확인 실패. 8자 이상이면 `ref` 항목 → 나머지 모든 항목 순서로 "정규화한 원문 안에 정규화한 인용문이 부분 문자열로 있는지" 본다. 처음 찾은 항목으로 `ref`를 고치고, 그 항목의 종류(`user`/`assistant`/`edit`)와 시각을 근거에 기록한다.

### 5.4 핵심 단어 (`keywords`, 분류 전체에서 씀)

1. 소문자로 바꾼 뒤 "영문·숫자·밑줄 3자 이상" 또는 "한글 2자 이상"인 덩어리를 뽑는다.
2. 한글 덩어리가 아래 조사로 끝나고, 떼어 낸 뒤에도 2자 이상 남으면 조사를 한 번만 뗀다. 앞에 있는 것부터 검사한다: 에서, 으로, 하고, 은, 는, 이, 가, 을, 를, 에, 의, 로, 도, 만, 와, 과
3. 불용어는 뺀다: 그리고, 그렇게, 하도록, 한다, 합니다, 있도록, 경우, 때는, 때, 함수, 코드

### 5.5 주체 분류 (`decisions.classify`, 설계서 5.8의 판정 순서를 그대로 따름)

| 단계 | 규칙 |
|---|---|
| 보류 표현 | 나중에, 추후(추후에), 보류, 미루·미뤄, 생각해 보자(띄어쓰기 무관), later, TBD(대소문자 무관). "다음에"는 바로 뒤(공백 허용)에 생각·정하·정해·보자·하자·논의가 올 때만 |
| 보류 절 | 사용자 발화를 정규화한 뒤 `.` `!` `?` `,` `;` 줄바꿈으로 나눈 조각. 보류 표현이 있고 결정 요약과 핵심 단어를 1개 이상 공유하는 첫 조각 |
| 보류를 볼 발화 | ① 확인된 근거 중 사용자 발화 ② 확인된 근거 중 가장 앞선 것보다 앞에 나온 마지막 사용자 발화 ③ 결정을 처음 말한 AI 발화(확인된 AI 근거 중 가장 앞선 것) 바로 뒤의 사용자 발화 |
| 보류 제외 | 확인된 사용자 근거 중 보류 절이 없는 발화가 하나라도 있으면 보류가 아니다(보류 뒤에 사람이 직접 정함) |
| 보류 기록 | `decided_by_note` = `사용자가 미뤘는데 코드에 반영됨: "<보류 절 앞 40자>"` |
| AI 제안 수락 | 첫 AI 근거 다음의 사용자 발화와 결정 요약이 핵심 단어 **2개 이상** 공유 |
| 짧은 수락 | 다음 사용자 발화가(정규화 후) 좋아·좋습니다·좋네·좋아요·ㅇㅋ·오케이·ok·okay·ㅇㅇ·네·응·그래·그렇게·진행·고고·lgtm·yes·sure 중 하나로 **시작**(대소문자 무관) |
| 포괄 수락 | 짧은 수락이고, 첫 AI 근거의 턴 번호가 같은 결정이 2개 이상 |
| 그 밖 | 다음 사용자 발화가 없으면 `ai_autonomous`("이후 사용자 반응 없음"), 있지만 위에 해당하지 않으면 `ai_autonomous`("다음 사용자 발화가 결정을 다루지 않음") |

`decided_by_note`의 나머지 문구: 사람 지시 "사용자 발화에 결정이 있음", 코드만 "대화 없이 코드에만 나타남", AI 제안 수락 "사용자가 구체적으로 언급함 (<겹친 단어를 정렬해 최대 3개>)", 포괄 수락 `짧은 수락 한 번에 결정 N개가 함께 넘어감: "<발화 앞 30자>"`, 단일 짧은 수락 `짧은 수락: "<발화 앞 30자>"`.

### 5.6 연결 (`decisions.link`)

- `related_symbols`의 각 이름이 단위의 `qualname`과 같거나, 마지막 점 뒤 이름끼리 같으면 연결한다(`charge_with_retry` ↔ `PaymentClient.charge_with_retry`). 같은 단위는 한 번만.
- 일치가 없을 때의 편집 hunk 겹침 연결은 설계서 5.9를 따른다.

### 5.7 같은 결과인지 확인하는 방법

사전 분석 결과 파일은 반입하지 않는다(사실상 프로토타입 산출물). 대신 [session-script.md](session-script.md) 3장 기준표에 대본 턴별로 기대하는 결정 주체(보류 후 반영 1개 이상, 포괄 수락, AI 단독, 사람 지시)를 사람이 판단해 적어 두고, 목요일 S2에서 실제 extract 결과의 분류가 이 기준을 충족하는지 확인한다.
