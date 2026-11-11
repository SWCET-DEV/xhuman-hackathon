# XHuman 설계서 (1차 구현)

| 항목 | 내용 |
|---|---|
| 문서 버전 | v0.1 (초안) |
| 근거 문서 | [기획서](proposal.md) |
| 1차 범위 | Python 코드 + Claude Code 개발 대화, 개인용, 로컬 실행 |
| 확인한 환경 | Claude Code 2.1.311, Python 3.13, Git 2.43 |

## 1. 개요

### 1.1 목적

AI와 함께 작성한 코드에 대해 다음 세 가지를 제공한다.

1. **축적:** 개발 대화에서 "왜"(결정, 이유, 버린 대안)를 근거와 함께 뽑아 함수 단위로 코드에 연결한다.
2. **측정:** 사람이 그 코드를 이해하는지 질문 3개로 확인하고, 위험도를 반영한 이해 커버리지를 계산한다.
3. **상환:** 모르는 부분만 짧게 채워 주고 다시 확인한다.

### 1.2 범위

| 구분 | 1차에 포함 | 1차에서 제외 (확장) |
|---|---|---|
| 언어 | Python (`.py`) | 다른 언어 |
| 대화 출처 | Claude Code 세션 기록 (JSONL) | 다른 AI 코딩 도구 |
| 사용자 | 개인 1명, 로컬 | 팀 공유, 조직 집계 |
| 연동 | 로컬 Git | GitHub PR, Jira |
| 화면 | CLI + 로컬 웹 리포트 | IDE 플러그인 |

### 1.3 설계 원칙

| 원칙 | 설계에 반영한 방식 |
|---|---|
| **근거 없으면 저장하지 않는다** | AI가 뽑은 결정의 인용문을 원문과 글자 단위로 대조하고, 일치하지 않으면 버린다 (5.7) |
| **AI는 판단만, 확인과 계산은 프로그램이** | 해시, 작성 출처, 위험 태그, 결정 주체, 점수, 커버리지는 모두 프로그램이 계산한다. AI는 추출, 질문 생성, 핵심 포인트 충족 판정만 맡는다 |
| **프로젝트에 파일을 만들지 않는다** | 모든 데이터는 `~/.xhuman/`에 저장한다. 사용자 프로젝트 폴더에는 아무것도 쓰지 않는다 |
| **로컬 우선** | 저장은 로컬 SQLite, 분석은 사용자가 이미 쓰는 Claude Code CLI. 결과는 본인만 본다 |
| **질문은 적게** | 한 번에 질문 3개. 설명은 모르는 부분에 대해서만 한다 |
| **모델 교체 가능** | AI 호출은 하나의 인터페이스로 모으고, Claude CLI와 사내 OSS 모델을 설정으로 바꿀 수 있게 한다 (8장) |

## 2. 전체 구조

```
 ┌──────────────────────────┐        ┌─────────────────────────┐
 │ Claude Code 세션 기록     │        │ 사용자 Python 프로젝트   │
 │ ~/.claude/projects/*.jsonl│        │ (Git 작업 트리)          │
 └────────────┬─────────────┘        └────────────┬────────────┘
              │ ① 수집                              │ ② 코드 색인
              ▼                                     ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                       XHuman 코어 (Python)                     │
 │                                                                │
 │  ingest ─▶ provenance ─▶ risk ─▶ test_watch ─▶ decisions       │
 │  (대화 정규화) (작성 출처)  (위험 태그) (테스트 변경)  (결정 추출·검증·분류·연결) │
 │                                                                │
 │  quiz (우선순위·질문·채점) ─▶ repay (상환) ─▶ coverage (집계)     │
 │                                                                │
 │  llm: LLMBackend ── ClaudeCLIBackend / InternalOSSBackend      │
 └───────────────┬───────────────────────────────┬──────────────┘
                 │                               │
                 ▼                               ▼
        ┌──────────────────┐            ┌──────────────────┐
        │ ~/.xhuman/        │            │ CLI (xh) /        │
        │ xhuman.db (SQLite)│◀──────────▶│ 로컬 웹 리포트     │
        └──────────────────┘            └──────────────────┘
```

| 모듈 | 역할 | AI 사용 |
|---|---|---|
| `ingest` | 세션 기록을 읽어 메시지와 편집 이력으로 정규화 | 없음 |
| `codeindex` | Python 파일을 함수·메서드·클래스 단위로 색인하고 해시 계산 | 없음 |
| `provenance` | AI 편집 이력과 현재 코드를 비교해 줄별 작성 출처 계산 | 없음 |
| `risk` | 규칙으로 위험 태그 부여 | 없음 |
| `test_watch` | AI의 기존 테스트 변경 감지 | 없음 |
| `decisions` | 결정 추출(AI) → 인용 검증 → 주체 분류 → 코드 연결 | 추출만 |
| `quiz` | 우선순위 계산, 질문 생성(AI), 채점(AI 판정 + 프로그램 집계) | 생성·판정 |
| `repay` | 놓친 핵심 포인트만 설명(AI), 재확인 질문 | 생성 |
| `coverage` | 이해 상태와 위험 가중 커버리지 계산 | 없음 |
| `llm` | AI 호출 추상화, 캐시, 재시도 | — |
| `cli`, `report` | 사용자 인터페이스 | 없음 |

## 3. 입력 데이터: Claude Code 세션 기록

### 3.1 위치와 형식

- 경로: `~/.claude/projects/<작업 경로를 -로 치환한 폴더>/<session_id>.jsonl`
- 한 줄에 레코드 하나(JSON). 레코드마다 `type`, `uuid`, `parentUuid`, `timestamp`, `sessionId`, `cwd`, `gitBranch`, `isSidechain`, `version` 등이 있다.
- **주의:** 공식 문서로 고정된 형식이 아니라 버전에 따라 바뀔 수 있다. 파서는 레코드의 `version`을 함께 저장하고, 모르는 필드와 `type`은 건너뛴다.

### 3.2 XHuman이 쓰는 레코드 (Claude Code 2.1.311에서 실측)

| 레코드 | 구분 방법 | 쓰는 필드 |
|---|---|---|
| 사용자 발화 | `type == "user"`, `message.content`가 문자열이거나 `text` 블록 | `uuid`, `timestamp`, 텍스트 |
| AI 발화 | `type == "assistant"`, `message.content[]`의 `text` 블록 | `uuid`, `timestamp`, 텍스트 |
| AI 도구 호출 | `type == "assistant"`, `message.content[]`의 `tool_use` 블록 | `id`, `name`, `input` |
| 도구 실행 결과 | `type == "user"`이면서 `toolUseResult`가 있음 | 아래 표 |

파일 편집 도구의 `input`과 `toolUseResult`:

| 도구 | `input` | `toolUseResult` |
|---|---|---|
| `Write` | `file_path`, `content` | `type`(`create` 등), `filePath`, `content`, `originalFile`, `structuredPatch`, `userModified`, `gitDiff` |
| `Edit` | `file_path`, `old_string`, `new_string`, `replace_all` | `filePath`, `oldString`, `newString`, `originalFile`, `structuredPatch`(줄 단위 hunk), `userModified`, `replaceAll`, `gitDiff` |

- `structuredPatch[]`는 `oldStart`, `oldLines`, `newStart`, `newLines`, `lines`(`+`/`-`/공백 접두사)를 가진다. 작성 출처 계산의 기본 재료다.
- `userModified == true`는 사용자가 AI의 편집 제안을 고쳐서 승인했다는 뜻으로 해석한다(구현 시 재확인). 이 경우 작성 출처를 `ai_then_human`으로 본다.
- 도구 결과 레코드의 `parentUuid`로 어떤 도구 호출의 결과인지 연결한다.
- `isSidechain == true`는 서브에이전트 대화다. 1차에서는 포함하되 표시만 해 둔다.

### 3.3 수집 대상 판별

세션 기록 폴더 이름은 작업 경로에서 만들어지므로, 등록된 프로젝트 경로와 레코드의 `cwd`를 비교해 해당 프로젝트의 세션만 수집한다.

## 4. 데이터 모델

저장소는 `~/.xhuman/xhuman.db`(SQLite, 파일 권한 600) 하나다. 프로젝트는 저장소 루트 경로로 구분한다.

아래 표가 스키마의 정본이다. 타입은 SQLite 타입, "필수"는 NOT NULL, "→ 테이블"은 외래 키다. 해커톤 범위의 변경점은 [contracts.md](contracts.md) 1.1에 있다.

**`projects`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `project_id` | INTEGER | 기본 키 |  |
| `root_path` | TEXT | 필수 · 고유 |  |
| `created_at` | TEXT | 필수 |  |

**`sessions`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `session_id` | TEXT | 기본 키 |  |
| `project_id` | INTEGER | 필수 · → `projects` |  |
| `transcript` | TEXT | 필수 | JSONL 경로 |
| `cc_version` | TEXT |  |  |
| `ingested_at` | TEXT | 필수 |  |
| `last_offset` | INTEGER | 필수 · 기본값 `0` | 이어서 읽기용 바이트 위치 |

**`messages`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `uuid` | TEXT | 기본 키 |  |
| `session_id` | TEXT | 필수 · → `sessions` |  |
| `parent_uuid` | TEXT |  |  |
| `role` | TEXT | 필수 · 허용값: user, assistant |  |
| `ts` | TEXT | 필수 |  |
| `text` | TEXT | 필수 | 정규화된 발화 텍스트 |
| `is_sidechain` | INTEGER | 필수 · 기본값 `0` |  |

**`edits`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `edit_id` | INTEGER | 기본 키 |  |
| `session_id` | TEXT | 필수 · → `sessions` |  |
| `message_uuid` | TEXT | 필수 | tool_use가 들어 있는 AI 메시지 |
| `tool` | TEXT | 필수 | Write / Edit |
| `file_path` | TEXT | 필수 | 프로젝트 기준 상대 경로 |
| `patch_json` | TEXT | 필수 | structuredPatch |
| `added_lines` | TEXT | 필수 | AI가 추가한 줄 목록(JSON) |
| `user_modified` | INTEGER | 필수 · 기본값 `0` |  |
| `is_test_file` | INTEGER | 필수 · 기본값 `0` |  |
| `ts` | TEXT | 필수 |  |

**`units`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `unit_id` | TEXT | 기본 키 | "<상대경로>::<qualname>" |
| `project_id` | INTEGER | 필수 · → `projects` |  |
| `file_path` | TEXT | 필수 |  |
| `qualname` | TEXT | 필수 | 예: PaymentClient.charge_with_retry |
| `kind` | TEXT | 필수 | function / method / class |
| `line_start` | INTEGER | 필수 |  |
| `line_end` | INTEGER | 필수 |  |
| `content_hash` | TEXT | 필수 | 5.2 참고 |
| `ai_lines` | INTEGER | 필수 · 기본값 `0` |  |
| `ai_human_lines` | INTEGER | 필수 · 기본값 `0` |  |
| `human_lines` | INTEGER | 필수 · 기본값 `0` |  |
| `risk_level` | INTEGER | 필수 · 기본값 `1` | 1 낮음, 2 중간, 3 높음 |
| `risk_tags` | TEXT | 필수 · 기본값 `[]` |  |
| `status` | TEXT | 필수 · 기본값 `active` | active / deleted |
| `updated_at` | TEXT | 필수 |  |

**`decisions`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `decision_id` | TEXT | 기본 키 |  |
| `project_id` | INTEGER | 필수 · → `projects` |  |
| `summary` | TEXT | 필수 |  |
| `reason` | TEXT | 필수 |  |
| `alternatives` | TEXT | 필수 · 기본값 `[]` | [{option, why_rejected}] |
| `level` | TEXT | 필수 · 허용값: structure, implementation |  |
| `decided_by` | TEXT | 필수 · 허용값: human_directed, ai_proposed_accepted, blanket_accepted, ai_autonomous, deferred |  |
| `confidence` | TEXT | 필수 | high / low |
| `status` | TEXT | 필수 · 기본값 `active` | active / needs_recheck / archived |
| `prompt_ver` | TEXT | 필수 |  |
| `created_at` | TEXT | 필수 |  |

**`decision_evidence`** (기본 키: (decision_id, source_ref, quote))

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `decision_id` | TEXT | 필수 · → `decisions` |  |
| `source_kind` | TEXT | 필수 · 허용값: user, assistant, edit |  |
| `source_ref` | TEXT | 필수 | messages.uuid 또는 edits.edit_id |
| `quote` | TEXT | 필수 | 원문과 일치가 확인된 인용문 |

**`decision_units`** (기본 키: (decision_id, unit_id))

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `decision_id` | TEXT | 필수 · → `decisions` |  |
| `unit_id` | TEXT | 필수 · → `units` |  |
| `anchored_hash` | TEXT | 필수 | 연결 시점의 content_hash |

**`test_events`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `event_id` | INTEGER | 기본 키 |  |
| `edit_id` | INTEGER | 필수 · → `edits` |  |
| `unit_id` | TEXT |  | 바뀐 테스트 함수 |
| `kind` | TEXT | 필수 | assertion_changed / test_removed / test_skipped / test_added |
| `before_text` | TEXT |  |  |
| `after_text` | TEXT |  |  |
| `status` | TEXT | 필수 · 기본값 `open` | open / answered |

**`questions`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `question_id` | TEXT | 기본 키 |  |
| `unit_id` | TEXT | 필수 · → `units` |  |
| `decision_id` | TEXT | → `decisions` |  |
| `test_event_id` | INTEGER | → `test_events` |  |
| `qtype` | TEXT | 필수 · 허용값: how, why, test |  |
| `text` | TEXT | 필수 |  |
| `key_points` | TEXT | 필수 | JSON 배열, 2~4개 |
| `priority` | REAL | 필수 |  |
| `prompt_ver` | TEXT | 필수 |  |
| `created_at` | TEXT | 필수 |  |

**`understanding`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `record_id` | INTEGER | 기본 키 |  |
| `unit_id` | TEXT | 필수 · → `units` |  |
| `question_id` | TEXT | 필수 · → `questions` |  |
| `mode` | TEXT | 필수 | check / repay_recheck / rehearsal |
| `answer` | TEXT | 필수 |  |
| `matched` | TEXT | 필수 | 충족한 핵심 포인트 번호(JSON) |
| `missed` | TEXT | 필수 |  |
| `verdict` | TEXT | 필수 · 허용값: understood, partial, unknown |  |
| `feedback` | TEXT |  |  |
| `unit_hash` | TEXT | 필수 | 측정 시점의 content_hash |
| `status` | TEXT | 필수 · 기본값 `valid` | valid / expired |
| `measured_at` | TEXT | 필수 |  |

**`llm_cache`**

| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `cache_key` | TEXT | 기본 키 | sha256(task, prompt_ver, model, input) |
| `response` | TEXT | 필수 |  |
| `created_at` | TEXT | 필수 |  |

## 5. 축적 파이프라인

`xh ingest`가 아래 순서로 실행한다. 모든 단계는 다시 실행해도 결과가 같도록(멱등) 만든다.

### 5.1 수집 (`ingest`)

1. 세션 JSONL을 `last_offset`부터 줄 단위로 읽는다. 깨진 줄은 건너뛰고 경고만 남긴다.
2. 사용자·AI 발화는 `messages`에, `Write`/`Edit` 도구 호출과 결과는 짝을 맞춰 `edits`에 저장한다.
3. 프로젝트 밖 파일, `.py`가 아닌 파일의 편집은 1차에서 제외한다.
4. 발화 텍스트에서 비밀값으로 보이는 문자열(API 키, 토큰, 비밀번호 대입 등)을 정규식으로 가린 뒤 저장한다. 이후 AI에 보내는 텍스트도 이 가린 버전만 쓴다.

### 5.2 코드 색인 (`codeindex`)

1. 프로젝트의 Git 추적 대상 `.py` 파일을 `ast`로 파싱해 함수, 메서드, 클래스를 단위(unit)로 뽑는다. `qualname`은 `클래스.메서드` 형식이다.
2. **해시:** `ast.dump(node, include_attributes=False)`의 SHA-256. 공백, 줄바꿈, 주석만 바뀐 경우에는 해시가 그대로라서 이해가 만료되지 않는다. 로직이 바뀌면 해시가 바뀐다.
3. 클래스 단위의 해시는 메서드 본문을 뺀 클래스 골격(이름, 상속, 클래스 변수)으로 계산해, 메서드 하나가 바뀌었다고 클래스 전체가 만료되지 않게 한다.
4. 문법 오류로 파싱이 안 되는 파일은 건너뛰고 표시만 한다.

### 5.3 작성 출처 (`provenance`)

1. 세션의 편집 이력에서 AI가 추가한 줄(`structuredPatch`의 `+` 줄, `Write`의 `content`)을 파일별로 모은다.
2. 현재 파일의 각 줄을 아래 순서로 분류한다.
   - AI가 추가한 줄과 공백을 무시하고 같음 → `ai`
   - 같지는 않지만 유사도(`difflib.SequenceMatcher` 비율)가 0.6 이상인 AI 줄이 있음 → `ai_then_human`
   - 해당 편집의 `userModified`가 참이면 `ai` 대신 `ai_then_human`
   - 나머지 → `human`
3. 빈 줄과 닫는 괄호처럼 의미 없는 줄은 집계에서 뺀다.
4. 단위별로 줄 수를 합산해 `units.ai_lines` 등에 저장한다. **AI 작성 비율** = (`ai` + 0.5 × `ai_then_human`) ÷ 전체.

한계: 같은 줄을 사람이 우연히 똑같이 쓴 경우를 구분하지 못한다. 1차에서는 허용한다.

### 5.4 위험 태그 (`risk`)

규칙은 `~/.xhuman/risk_rules.toml`로 분리해 사용자가 고칠 수 있게 한다. 기본 규칙:

| 등급 | 태그 | 감지 패턴 (AST 기준) |
|---|---|---|
| 3 높음 | `db_write` | `execute`/`executemany` 호출의 SQL 문자열에 `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER` 포함, `commit()`, ORM의 `.save()`, `.delete()`, `bulk_*` |
| 3 높음 | `auth` | 함수명·인자명에 `auth`, `login`, `token`, `password`, `permission`, `role` 포함, `jwt`·`bcrypt`·`hashlib` 사용, `login_required` 류 데코레이터 |
| 3 높음 | `payment` | 함수명에 `pay`, `charge`, `refund`, `billing`, `invoice` 포함 |
| 3 높음 | `migration` | 경로에 `migrations/`, `alembic/` 포함 |
| 3 높음 | `irreversible_fs` | `os.remove`, `os.unlink`, `shutil.rmtree`, `Path.unlink` |
| 2 중간 | `external_write` | `requests`/`httpx`의 `post`, `put`, `patch`, `delete` |
| 2 중간 | `process` | `subprocess.*`, `os.system`, `eval`, `exec` |
| 2 중간 | `concurrency` | `threading`, `asyncio.Lock`, `multiprocessing` 사용 |
| 1 낮음 | — | 그 외 |

단위의 `risk_level`은 붙은 태그 중 가장 높은 등급이다.

### 5.5 테스트 변경 감지 (`test_watch`)

테스트 파일 판정: `test_*.py`, `*_test.py`, `tests/` 아래 파일.

AI 편집 중 **원래 있던** 테스트 파일을 고친 것(`Write`로 새로 만든 파일은 제외)을 검사한다.

| 종류 | 판정 기준 | 처리 |
|---|---|---|
| `assertion_changed` | 지워진 줄과 추가된 줄에 모두 `assert`, `self.assert*`, `pytest.raises`, `pytest.approx`가 있고 내용이 다름 | 최우선 질문 |
| `test_removed` | 편집 전 파일에 있던 `test_*` 함수가 편집 후 사라짐 (`originalFile`과 결과 비교) | 최우선 질문 |
| `test_skipped` | `@pytest.mark.skip`, `@pytest.mark.xfail`, `pytest.skip(`, `unittest.skip` 추가 | 최우선 질문 |
| `test_added` | 새 테스트 함수만 추가됨 | 기록만 함 |

### 5.6 결정 추출 (`decisions.extract`, AI)

1. **입력 만들기:** 세션을 압축한 텍스트를 만든다.
   - 사용자·AI 발화는 앞에 `[m:<uuid 앞 8자리>|user]`처럼 메시지 표식을 붙인다.
   - 도구 호출은 `[edit: payment/retry.py +12/-3]`처럼 한 줄로 요약한다.
   - 긴 도구 출력(명령 실행 결과 등)은 넣지 않는다.
2. **분할:** 약 40,000자 단위로 나누고, 앞 덩어리의 마지막 메시지 2개를 다음 덩어리에 겹쳐 넣는다.
3. **호출:** 덩어리마다 한 번 호출한다. 출력 JSON 스키마:

```json
{
  "decisions": [
    {
      "summary": "PG 응답이 5xx/타임아웃일 때만 지수 백오프로 최대 3회 재시도",
      "reason": "4xx는 재시도해도 결과가 같고 5xx는 일시적 장애일 가능성이 높음",
      "alternatives": [{ "option": "고정 간격 재시도", "why_rejected": "PG 호출 제한" }],
      "level": "implementation",
      "quotes": [
        { "message_ref": "b7e2c1a0", "text": "5xx나 타임아웃일 때만 지수 백오프로 최대 3회 재시도하겠습니다" }
      ],
      "related_files": ["payment/retry.py"],
      "related_symbols": ["charge_with_retry"]
    }
  ]
}
```

4. **프롬프트 규칙** (프로토타입 `extract-v0.3`에서 검증):
   - 코드 구현에 영향을 준 결정만 뽑는다. 인용은 원문을 글자 그대로 10~200자로 한다.
   - 근거는 발화(`m:`) 또는 AI 편집 코드(`e:`)에서 인용한다. 대화 없이 코드에만 나타난 결정도 코드 줄을 근거로 뽑는다.
   - 결정이 대화에서 처음 등장한 발화를 **첫 번째 근거**로 단다. 이게 없으면 AI가 제안하고 사용자가 수락한 결정이 코드 근거만 달려 "AI 단독"으로 잘못 분류된다.
   - 사용자 지시를 구현하면서 AI가 **스스로 덧붙인 예외·조건·기본값은 별도 결정**으로 분리한다. 합치면 AI 단독 결정이 "사람 지시" 안에 가려진다.
   - `reason`은 인용한 항목에 실제로 나온 이유만 쓰고, 없으면 `"기록에 근거 없음"`으로 둔다.

### 5.7 인용 검증 (프로그램)

1. 인용문과 원문을 정규화한다(유니코드 NFC, 연속 공백을 하나로, 앞뒤 공백 제거).
2. `ref`가 가리키는 발화나 AI 편집 코드 안에 인용문이 **부분 문자열로 그대로** 있는지 확인한다. 8자 미만 인용("좋아" 등)은 인정하지 않는다.
3. 없으면 같은 세션의 모든 발화와 편집에서 찾는다. 찾으면 `ref`를 고친다.
4. 인용문이 하나도 확인되지 않은 결정은 **저장하지 않는다.** 일부만 확인되면 `confidence = low`로 저장하고 화면에서 확인 버튼을 보여 준다.

### 5.8 결정 주체 분류 (프로그램 규칙)

인용문의 위치와 바로 다음 사용자 발화를 보고 정한다. **보류 판정을 가장 먼저 한다.**

| 조건 | `decided_by` |
|---|---|
| 결정 근처의 사용자 발화(근거로 인용된 사용자 발화, 결정이 처음 나오기 직전의 요청, 결정을 제안한 AI 발화 직후의 응답) 중 한 절에 보류 표현("나중에", "추후", "보류", "미루", "생각해 보자", "다음에 정하자" 등)이 있고, 그 절이 결정 요약과 핵심 단어를 1개 이상 공유함. 단, 근거에 보류 표현이 없는 사용자 지시 발화가 있으면(보류 뒤에 사람이 직접 정함) 제외 | `deferred` |
| 확인된 근거 중에 사용자 발화가 있음 | `human_directed` |
| 확인된 근거가 AI 편집 코드뿐임 (대화에서 언급되지 않음) | `ai_autonomous` |
| 첫 인용이 AI 발화이고, 다음 사용자 발화가 그 결정을 구체적으로 언급하며 수락함 | `ai_proposed_accepted` |
| 첫 인용이 AI 발화이고, 다음 사용자 발화가 짧은 수락("좋아", "그렇게 해", "ok", "진행해" 등)이며, 같은 AI 발화에서 결정이 2개 이상 나옴 | `blanket_accepted` |
| 첫 인용이 AI 발화이고, 결정 1개에 대한 짧은 수락 | `ai_proposed_accepted` |
| 사용자의 반응 없이 AI가 진행함(다음 사용자 발화가 없거나 다른 주제) | `ai_autonomous` |

`deferred`는 "사람이 미뤘는데 코드에는 이미 들어간 결정"이다. 추출 대상이 '코드에 영향을 준 결정'뿐이므로, AI가 보류를 존중해 아무것도 넣지 않은 경우는 결정으로 잡히지 않는다. "다음에"는 순서 표현("다음에 테스트도 해 줘")으로도 쓰여서, 뒤에 생각·결정 동사가 올 때만 보류로 본다.

"구체적으로 언급"은 결정 요약의 핵심 단어가 사용자 발화에 들어 있는지로 판단한다. 수락 표현 목록은 설정 파일로 둔다. 애매한 경우는 보수적으로 이해 부채가 큰 쪽(`blanket_accepted`, `ai_autonomous`)으로 분류한다.

### 5.9 코드 연결과 만료

1. **연결:** `related_symbols`가 `units.qualname`과 일치하면 연결한다. 일치하는 게 없으면, 인용 메시지와 다음 사용자 발화 사이에 일어난 편집의 hunk와 줄 범위가 겹치는 단위에 연결한다. 연결 시점의 해시를 `anchored_hash`로 저장한다.
2. **연결 실패:** 어느 단위에도 연결되지 않은 결정은 프로젝트 수준 결정으로 저장하고 질문 대상에서는 뺀다.
3. **만료:** `xh scan`을 실행할 때마다 단위 해시를 다시 계산한다.
   - 해시가 바뀐 단위 → 그 단위의 `understanding` 기록은 `expired`, 연결된 결정은 `needs_recheck`
   - 단위가 사라짐 → `units.status = deleted`, 연결된 결정은 `archived`

## 6. 측정과 상환

### 6.1 질문 우선순위

대상은 AI 작성 비율 0.3 이상인 단위(또는 열린 테스트 변경 이벤트가 있는 단위)다.

```
priority = R × S × L × A × U
```

| 기호 | 의미 | 값 |
|---|---|---|
| R | 위험도 | 낮음 1.0 / 중간 1.5 / 높음 2.5 |
| S | 결정 주체 (연결된 결정 중 최댓값) | human_directed 0.6 / ai_proposed_accepted 1.0 / blanket_accepted 1.4 / ai_autonomous 1.8 / deferred 2.0 / 결정 없음 1.2 |
| L | 결정 중요도 | 구조 1.5 / 구현 1.0 |
| A | AI 작성 비율 | 0.3 ~ 1.0 |
| U | 현재 이해 상태 | 미측정 1.0 / 만료 1.1 / 모름 1.0 / 부분 0.7 / 이해 0.05 |

- 열린 테스트 변경 이벤트(`assertion_changed`, `test_removed`, `test_skipped`)는 점수와 상관없이 **맨 앞**에 둔다. 단, 한 번에 1개까지([contracts.md](contracts.md) 1.2 규칙 7).
- 한 번에 3개를 고르되 같은 단위에서 2개 이상 고르지 않는다.
- 가중치는 설정 파일로 둔다. 위 값은 시작값이며 시연 데이터로 조정한다.

### 6.2 질문 생성 (AI)

입력: 단위의 코드, 연결된 결정(요약, 이유, 버린 대안, 인용), 위험 태그, 테스트 변경 내용(있으면).

출력 스키마:

```json
{
  "question": "재시도할 때 멱등성 키를 새로 만들지 않고 같은 키를 쓰는 이유는 무엇인가요?",
  "qtype": "why",
  "key_points": [
    "첫 요청이 PG사에서 이미 처리됐을 수 있다",
    "같은 키를 쓰면 PG사가 중복 요청으로 보고 한 번만 결제한다",
    "새 키를 쓰면 이중 결제가 발생할 수 있다"
  ]
}
```

규칙:

- 결정이 있으면 `why`, 없으면 `how`(동작 흐름, 경계 조건, 실패 시 동작) 질문을 만든다. 이유가 기록에 없는 결정(보류 후 반영, AI 단독에 많음)은 동기를 묻지 않고 "그 결정 때문에 어떤 상황에서 무슨 일이 생기는가"를 묻는다. 세부는 [prompts/question.md](prompts/question.md).
- 코드를 보면 바로 읽히는 사실(변수 이름, 줄 수)은 묻지 않는다.
- 핵심 포인트는 2~4개, 각각 한 문장. 채점 기준이 되므로 서로 겹치지 않게 한다. 나누다 보니 4개를 넘으면 질문의 핵심과 거리가 먼 것부터 버린다.
- 각 포인트는 답에 그 내용이 있는지 없는지 판정할 수 있는 구체적 사실로 쓴다. "~해야 한다", "~가 중요하다" 같은 원칙·당위 문장은 쓰지 않는다(11/10).
- 포인트 하나에 주장 하나만 쓴다. 따로 충족될 수 있는 내용은 나눈다(11/10). 좋은 예·나쁜 예는 [prompts/question.md](prompts/question.md) 규칙 6.
- 생성된 포인트를 실행 중에 AI로 다시 검토하는 단계는 두지 않는다. 시험해 보니 검토 AI도 실행마다 지적 개수가 4~8개로 흔들리고 과하게 쪼갰다. 시연용 질문은 개발 중에 미리 점검한다.
- 테스트 변경 질문은 고정 틀을 쓴다: "이 테스트는 원래 어떤 상황을 막고 있었나요? 기대값을 바꾼 것이 맞는 판단인가요?"
- 사용자 수준 설정(`junior`/`senior`)에 따라 용어 설명 여부를 조절한다.

### 6.3 채점 (AI 판정 + 프로그램 집계)

- 답변 3개를 **한 번의 호출로** 판정한다(대기 시간을 줄이기 위해).
- AI는 질문마다 각 핵심 포인트를 충족했는지만 판정하고(`matched`, `missed`), 피드백을 2문장 이내로 쓴다.
- `verdict`는 프로그램이 정한다: 충족 수 = 전체 포인트 수 → `understood`, 1개 이상 → `partial`, 0개 → `unknown`. 충족은 `matched`로만 계산하고 누락·중복 포인트는 미충족([contracts.md](contracts.md) 1.2 규칙 1).
- 목적만 말하고 사실이 없는 짧은 답("로그인을 유지하려고요")은 미충족이다(11/10 발표자 결정).
- 판정 결과는 측정 시점의 단위 해시와 함께 `understanding`에 저장한다.

### 6.4 상환 (AI)

1. `partial`/`unknown`인 질문에 대해 놓친 핵심 포인트만 넘겨 설명을 만든다. 형식은 고정한다.
   - 동작 흐름 한 문장
   - 핵심 결정 2~3개 (각 1문장, 근거 인용 포함)
   - 버린 대안 1개
2. 설명 뒤에 **응용 재확인 질문**을 만든다. 같은 질문을 다시 묻지 않고, 놓친 핵심 포인트를 다른 상황에 적용해야 답할 수 있게 묻는다(11/10 결정, 상환 직후의 단기 기억만 재는 것을 줄이기 위해). 답을 받아 다시 채점한다(`mode = repay_recheck`).
3. 상환 전후 점수를 함께 보여 준다.

### 6.5 리뷰 리허설 (AI)

- 입력: 이번 변경의 단위 목록, 결정 요약, 위험 태그, 테스트 변경.
- AI가 리뷰어 역할로 질문 3개를 만든다. 답을 받으면 보완할 점을 알려 준다.
- 결과는 `mode = rehearsal`로 저장하지만, 커버리지 계산에는 넣지 않는다(질문 품질이 통제되지 않으므로).

### 6.6 이해 커버리지 (프로그램)

- 단위의 이해 상태 = 가장 최근의 `valid` 기록의 `verdict`. 기록이 없으면 `미측정`.
- 대상 단위: AI 작성 비율 0.3 이상인 활성 단위. 테스트 파일 단위는 제외([contracts.md](contracts.md) 1.2 규칙 5).

```
위험 가중 커버리지 = Σ w(u) · [상태(u) = understood] / Σ w(u)
w(u) = 1 (낮음) / 2 (중간) / 4 (높음)
```

- 단순 커버리지(가중치 없음)도 함께 보여 줘서, "전체로는 80%인데 위험 코드는 30%" 같은 차이가 드러나게 한다.

## 7. 사용자 인터페이스

### 7.1 CLI (`xh`)

| 명령 | 동작 |
|---|---|
| `xh init` | 현재 Git 저장소를 프로젝트로 등록하고, 사용자 설정(`~/.claude/settings.json`)에 SessionEnd 훅 추가를 제안한다 |
| `xh ingest [--session PATH \| --latest]` | 세션 기록을 수집하고 5장의 파이프라인을 실행한다 |
| `xh scan` | 코드 색인, 작성 출처, 만료 처리만 다시 실행한다 |
| `xh status` | 커버리지, 이해 부채 상위 단위, 열린 테스트 변경을 요약한다 |
| `xh check` | 질문 3개를 터미널에서 묻고 채점한 뒤, 원하면 바로 상환으로 이어간다 |
| `xh why <파일::함수>` | 해당 단위의 결정 기록을 근거 인용과 함께 보여 준다 (리뷰에서 질문받았을 때) |
| `xh rehearse` | 리뷰 리허설 |
| `xh report` | 로컬 웹 리포트를 만들어 브라우저로 연다 |

### 7.2 자동 실행 (Claude Code 훅)

- **SessionEnd 훅:** 표준 입력으로 받은 JSON에서 세션 기록 경로(`transcript_path`)와 `cwd`를 읽어 `xh ingest --session <경로>`를 **백그라운드로** 실행한다. 세션 종료를 늦추지 않기 위해서다. (훅 입력 필드 이름은 구현 시 공식 문서로 다시 확인한다.)
- **재귀 방지:** 훅 스크립트는 환경 변수 `XHUMAN_CHILD=1`이면 바로 종료한다. XHuman이 띄우는 분석용 CLI는 이 변수를 설정한다(8.2).
- 훅은 사용자 설정에 한 번만 등록하고, 스크립트가 등록된 프로젝트인지 확인한 뒤 실행한다. 사용자 프로젝트에 설정 파일을 만들지 않는다.
- 시연 사고를 막기 위해 **기본 동작은 CLI 수동 실행**으로 두고 훅은 선택으로 둔다.

### 7.3 로컬 웹 리포트 (`xh report`)

정적 HTML 한 장을 `~/.xhuman/report/`에 만들고 브라우저로 연다. 서버가 필요 없다.

| 화면 | 내용 |
|---|---|
| 이해 지도 | 파일 → 단위 트리. 색: 초록(이해) / 연두(부분) / 빨강(모름·미측정) / 노랑(만료). 위험 배지, AI 작성 비율 막대 |
| 단위 상세 | 결정 기록(근거 인용, 결정 주체 배지, 버린 대안), 테스트 변경 이벤트, 측정 이력 |
| 요약 | 위험 가중 커버리지와 단순 커버리지, 상환 전후 변화, 이해 부채 상위 5개 |

웹에서 퀴즈를 푸는 기능은 2일 차에 시간이 남으면 추가한다(로컬 서버 필요).

## 8. AI 호출 (`llm`)

### 8.1 인터페이스

모든 백엔드는 메서드 하나만 가진다: `complete_json`. 인자는 키워드로 받는 `task`(문자열), `prompt`(문자열), `schema`(JSON 스키마 사전), `stdin_text`(문자열, 기본 빈 값)이고, 스키마에 맞는 JSON 사전을 돌려준다.

- `task`: `extract` / `question` / `grade` / `repay` / `rehearse`
- 모든 호출은 캐시를 먼저 조회한다. 캐시 키 = `sha256(task, prompt_ver, model, prompt, stdin_text)`.
- 응답이 스키마에 맞지 않으면 한 번 재시도하고, 그래도 실패하면 해당 항목을 건너뛰고 기록한다.

### 8.2 ClaudeCLIBackend (기본값)

```bash
claude -p "<지시문>" \
  --model <작업별 모델> \
  --tools "" \
  --no-session-persistence \
  --setting-sources "" \
  --output-format json \
  --json-schema '<스키마 JSON>'
```

- 긴 입력(세션 압축 텍스트, 코드)은 **표준 입력**으로 넘긴다.
- 결과 JSON의 `structured_output`을 사용하고, `is_error`가 참이면 실패로 처리한다.
- 시간 제한 120초.
- **환경 변수:** 자식 프로세스에서 `CLAUDE_CODE_SESSION_ID`를 지우고 `XHUMAN_CHILD=1`을 넣는다. 실측해 보니 Claude Code 안에서 CLI를 띄우면 부모의 세션 ID를 이어받았다.
- **재귀 방지:** `--no-session-persistence`로 분석 세션의 기록을 남기지 않고, `--setting-sources ""`로 훅을 포함한 사용자 설정을 불러오지 않는다. `--bare`는 API 키 인증만 지원해서 구독 로그인 환경에서는 쓰지 않는다.
- 작업별 모델(설정으로 변경 가능):

| 작업 | 모델 | 이유 |
|---|---|---|
| `extract`, `question` | sonnet | 품질이 결과를 좌우함 |
| `grade`, `repay`, `rehearse` | haiku | 가볍고 자주 호출함 |

- 실측: 짧은 대화의 결정 추출 1회에 약 6초(시작 시간 포함), 스키마에 맞는 JSON 반환을 확인했다.

### 8.3 InternalOSSBackend (선택)

- OpenAI 호환 `/v1/chat/completions` 호출을 가정한다(사내 API 정보를 받은 뒤 확정).
- `response_format`의 JSON 스키마를 지원하면 사용하고, 지원하지 않으면 JSON 모드와 프로그램 검증으로 대신한다.
- 작업별로 백엔드를 고를 수 있게 한다. 예: `grade`만 사내 모델.

### 8.4 프롬프트 관리

- 프롬프트는 `xhuman/prompts/<task>.md` 파일로 두고, 맨 위에 버전을 적는다.
- 결정과 질문 레코드에 `prompt_ver`를 저장해, 프롬프트를 바꾼 뒤 결과를 비교할 수 있게 한다.

## 9. 보안과 개인정보

- 데이터는 `~/.xhuman/` 아래에만 저장하고 DB 파일 권한은 600으로 만든다.
- 사용자 프로젝트에는 파일을 만들지 않는다.
- AI에 보내기 전에 비밀값으로 보이는 문자열을 가린다(5.1).
- 분석은 사용자가 이미 쓰는 Claude Code(또는 승인된 사내 모델)로만 한다. XHuman 자체는 네트워크로 데이터를 보내지 않는다.
- 이해 기록은 본인만 본다. 공유 기능은 1차에 없다.

## 10. 코드 구조

```
hackathon_26/
├── docs/
│   ├── proposal.md          기획서
│   └── design.md            설계서 (이 문서)
├── xhuman/
│   ├── cli.py               xh 명령
│   ├── config.py            설정, 경로, 가중치
│   ├── store.py             SQLite 스키마와 접근
│   ├── ingest.py            세션 JSONL 파서, 비밀값 가리기
│   ├── codeindex.py         ast 색인, 해시
│   ├── provenance.py        작성 출처
│   ├── risk.py              위험 태그 규칙
│   ├── test_watch.py        테스트 변경 감지
│   ├── decisions.py         추출, 인용 검증, 주체 분류, 연결
│   ├── quiz.py              우선순위, 질문 생성, 채점
│   ├── repay.py             상환, 재확인
│   ├── coverage.py          커버리지 계산
│   ├── report.py            정적 HTML 리포트
│   ├── hook.py              SessionEnd 훅 진입점
│   ├── llm/
│   │   ├── base.py          LLMBackend, 캐시, 재시도
│   │   ├── claude_cli.py
│   │   └── internal_oss.py
│   └── prompts/             작업별 프롬프트
├── tests/
│   ├── fixtures/            샘플 세션 JSONL, 샘플 Python 프로젝트
│   └── test_*.py
└── pyproject.toml
```

외부 의존성은 최소로 한다. 1차는 Python 표준 라이브러리만으로 구현할 수 있다(`ast`, `sqlite3`, `difflib`, `hashlib`, `subprocess`, `json`, `tomllib`). CLI 편의를 위해 필요하면 `typer` 정도만 추가한다.

## 11. 테스트와 품질 검증

| 대상 | 방법 |
|---|---|
| 세션 파서 | 실제 세션에서 만든 JSONL 픽스처로 메시지·편집 추출 결과를 검증. 깨진 줄, 모르는 레코드 타입 포함 |
| 해시 안정성 | 공백·주석만 바꾼 코드는 해시 동일, 로직을 바꾼 코드는 해시 변경 |
| 작성 출처 | AI 편집 → 사람 수정 시나리오 픽스처로 `ai` / `ai_then_human` / `human` 분류 확인 |
| 위험 태그, 테스트 변경 | 패턴별 최소 예제 코드로 단위 테스트 |
| 인용 검증 | 일치, 공백 차이, 다른 메시지에 있음, 지어낸 인용 각각의 처리 확인 |
| 결정 주체 분류 | 사람 지시 / 구체적 수락 / 포괄 수락 / 무반응 / 보류 후 반영 대화 픽스처 |
| **결정 추출 품질** | 실제 세션 3~5개에 사람이 결정을 직접 표시한 정답셋을 만들고, 정밀도·재현율을 측정한다. 기획서의 "결정 추출 정확도" 지표가 이것이다 |

AI 호출이 들어가는 테스트는 캐시나 가짜 백엔드로 고정해, 테스트가 사용량을 쓰지 않게 한다.

## 12. 구현 계획 (1박 2일)

### 12.1 우선순위

| 구분 | 기능 |
|---|---|
| **필수** | 세션 수집, 코드 색인·해시, 작성 출처, 결정 추출·인용 검증·주체 분류·연결, 위험 태그, 질문·채점·상환(CLI), 커버리지, 정적 리포트 |
| **가능하면** | 테스트 변경 감지, 만료 표시, 리뷰 리허설, SessionEnd 훅 |
| **이번에는 뺌** | 웹 퀴즈, 망각 곡선, 중복 결정 병합, PR·지라 연동, 사내 OSS 백엔드 실제 연결 |

테스트 변경 감지는 시연 효과가 커서, 필수 기능이 일찍 끝나면 가장 먼저 붙인다.

### 12.2 일정

| 시간 | 작업 | 완료 기준 |
|---|---|---|
| 1일 차 오전 | `store`, `ingest`, `codeindex`, `provenance` | 샘플 세션을 넣으면 단위별 AI 작성 비율이 나온다 |
| 1일 차 오후 | `llm`(CLI 백엔드, 캐시), `decisions` 전체, `risk` | 결정이 근거 인용과 함께 단위에 연결된다 |
| 1일 차 저녁 | `quiz`, `repay`, `coverage`, `xh check`/`status`/`why` | 터미널에서 질문 3개 → 채점 → 상환 → 재측정이 된다 |
| 2일 차 새벽~오전 | `report`, `test_watch`, 만료 처리, `rehearse` | 리포트에서 지도와 단위 상세를 볼 수 있다 |
| 2일 차 오후 | 시연 데이터 점검, 가중치 조정, 리허설, 발표 준비 | 3분 시연이 끊김 없이 된다 |

### 12.3 사전 준비 (해커톤 규정이 허용하는 범위에서)

- 결정 추출 프롬프트를 실제 세션 몇 개로 미리 검증한다. 가장 큰 불확실성이다.
- 시연용 샘플 프로젝트(예: 결제 재시도와 멱등성 키, 이를 검증하는 테스트)를 Claude와 2~3시간 개발해 세션 기록을 확보한다. 이 과정에 AI가 기존 테스트를 고치는 장면이 하나 들어가면 시연에 쓸 수 있다.

## 13. 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 결정 추출 품질이 낮음 | 핵심 가치 훼손 | 사전 검증, 인용 검증으로 지어낸 기록 차단, `confidence = low`는 사용자 확인 |
| 결정 단위 크기가 실행마다 다름 | 질문 대상과 커버리지 흔들림 | 프로토타입에서 같은 세션이 6~12개로 나뉘어 확인됨. 정답셋으로 기준을 정하고, 같은 함수·같은 근거의 결정은 질문 단계에서 묶는다 |
| 세션 기록 형식 변경 | 수집 실패 | 방어적 파싱, 모르는 필드 무시, `cc_version` 저장, 파서 테스트 |
| 구독 사용량 한도 | 분석 중단 | 세션 종료 시 한 번 일괄 분석, 캐시, 가벼운 작업은 haiku |
| CLI 호출 지연(회당 5초 안팎) | 퀴즈 대기 | 채점 일괄 처리, 질문은 미리 생성해 두기 |
| 분석 세션이 다시 분석되는 재귀 | 무한 실행 | 세션 기록 끄기, 설정 불러오지 않기, `XHUMAN_CHILD` 검사, 세션 ID 환경 변수 제거 |
| 긴 세션 | 입력 길이 초과 | 압축 텍스트, 분할과 겹침 |
| 채점이 흔들림 | 점수 신뢰도 하락 | 핵심 포인트 충족 여부만 AI가 판정, 판정 결과는 프로그램이 규칙으로 집계 |
| 작성 출처 오분류 | 우선순위 왜곡 | 유사도 기준을 설정으로 두고 시연 데이터로 조정 |

## 14. 시연 시나리오 (3분)

1. **고백 (30초):** "Claude와 3시간 동안 만든 이 PR, 저는 설명하지 못합니다." 세션 리캡을 띄워 보여 주며 "요약은 읽었지만 리뷰 질문에는 여전히 답을 못 합니다."
2. **지도 (30초):** `xh report`. 결제 함수가 빨강, 위험 배지. 위험 가중 커버리지 30%.
3. **테스트 변경 (30초):** "AI가 기존 테스트의 기대값을 바꿨습니다. 이 테스트는 원래 무엇을 막고 있었을까요?"
4. **측정과 상환 (60초):** `xh check` → 멱등성 키 질문에 "부분 이해" → 상환 설명 → 재확인 → 85%.
5. **왜 (30초):** 리뷰어 질문에 `xh why payment/retry.py::charge_with_retry`로 근거 인용과 함께 답한다. 코드를 조금 고치면 지도의 해당 칸이 노랑으로 바뀐다.

## 15. 확장을 위한 설계 포인트

| 확장 | 지금 설계에서 준비한 곳 |
|---|---|
| 다른 언어 | `codeindex`의 단위 추출을 언어별 플러그인으로 분리할 수 있게 인터페이스로 둔다 (tree-sitter 등) |
| 다른 AI 코딩 도구 | `ingest`의 출력(메시지, 편집)을 공통 형식으로 정의해 파서만 추가하면 되게 한다 |
| PR·지라 연동 | 결정 요약을 PR 본문 형식으로 내보내는 함수를 `report`에 둔다 |
| 사내 OSS 모델 | `LLMBackend` 구현체 추가 |
| 팀 커버리지 | 집계값만 내보내는 명령을 별도로 둔다. 개인 답변은 내보내지 않는다 |
