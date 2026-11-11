# XHuman (Explainable Human)

> 사람이 정하지 않았는데 코드가 된 결정을 대화 기록에서 찾아, 필요할 때 질문 세 개로 **내가 설명할 수 있게** 만드는 도구

AI 코딩 도구가 코드를 만드는 속도를 사람이 이해하는 속도가 따라가지 못하면서 "이해 부채(Comprehension Debt)"가 쌓이고 있습니다. XHuman은 Claude Code 개발 대화에서 결정과 그 이유를 근거와 함께 뽑아 코드에 연결하고, 질문 3개로 이해도를 확인한 뒤 모르는 부분만 채워 줍니다.

## 목요일 시작 순서 (11/12 08:00, 여기부터 본다)

새 내용은 없다. 아래 순서로 [구현 계획](docs/build-plan.md)을 따라간다.

1. 이 저장소를 클론한다.
2. [구현 계획](docs/build-plan.md) 2장 "S0 셋업"의 **"가장 먼저(10분, 사람이 직접)"**를 한다: `setup/` 삭제 커밋 → 수요일 점검에서 안 된 항목 → 나눠 준 계정으로 `claude -p` 확인.
3. 이 폴더에서 Claude Code를 연다([CLAUDE.md](CLAUDE.md)가 지침이다). S0의 작업 프롬프트를 그대로 붙여 넣는다.
4. 이후는 구현 계획 1.1 시간표 순서(S0 → S1 → S2 → 점심·V1 → S3 → C1·V2 → S4 → S5 → V3 → 20:30 동결 → S6)로, 각 단계의 프롬프트(2장)를 붙여 넣고 단계가 끝나면 커밋한다.
5. C1(16:15)에서 `tests/fixtures/demo_answers.json`을 직접 만든다(구현 계획 C1의 절차 1~3).
6. 늦으면 구현 계획 1.3 컷 라인, 막히면 3장, 검증 세션(V1~V3) 프롬프트는 4장. 완료 기준은 [시연 대본](docs/demo-script.md)이다.

## 문서

- [기획서](docs/proposal.md)
- [설계서](docs/design.md)
- 결정 추출 프로토타입은 사전 검증에만 썼고 해커톤에는 반입하지 않는다([반입 점검](docs/carry-in.md))

### 해커톤 구현 준비

- [CLAUDE.md](CLAUDE.md): 당일 Claude Code 지침, 이번 구현 범위
- [구현 계획](docs/build-plan.md): 시간표, 단계별 작업 프롬프트, 컷 라인
- [모듈 간 계약](docs/contracts.md): 축소 스키마, AI 출력 스키마, CLI 입출력
- [프롬프트](docs/prompts/): extract·question·grade·repay(11/10 녹화본으로 실측, 결과 응답은 반입하지 않음)
- [시연 대본](docs/demo-script.md): 라이브 데모 + 캡처본 백업
- [시연용 세션 기록 만들기](docs/session-script.md)
- [테스트 시나리오](docs/test-cases.md) · [리포트 화면](docs/report-wireframe.md) · [실측 사실과 함정](docs/verified-facts.md) · [발표 준비](docs/qa-prep.md) · [반입 점검](docs/carry-in.md) · [발표자료 초안](docs/slides-draft.md) · [제출본 대비 변경](docs/submitted-vs-current.md)

## 상태

사내 AX 해커톤 제출용 기획·설계 단계입니다. 1차 구현 범위는 Python 코드와 Claude Code 개발 대화입니다.
