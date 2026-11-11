# 해커톤 PC 환경 세팅 (수 11/11 17:00~18:00)

이 파일 하나만 보고 위에서부터 하면 된다. 시간이 모자라면 아래부터 버린다. 결과(됨/안 됨, 걸린 시간, 오류 문구)를 적어 온다.

목표: 목요일 08:00에 설치·로그인·버전 문제로 1분도 쓰지 않는 것.

## 가져갈 것

- 이 저장소 주소: `https://github.com/samsung-sds-hackathon/xhuman` (11/11 21시부터 주최 측 저장소. 이전 주소 SWCET-DEV/xhuman-hackathon은 쓰지 않는다)
- 주최 측이 나눠 줄 Claude 계정, Codex 계정 정보
- 결과를 적을 메모(휴대폰 메모도 됨)

## 사전에 설치할 것 (없으면 17:00~18:00에 설치)

| 도구 | 확인 명령 | 기준 | 비고 |
|---|---|---|---|
| Claude Code | `claude --version` | 녹화본 2.1.322, 이상이면 된다 | 설치 방식(네이티브, npm)에 따라 Node.js가 필요할 수 있다. 어느 쪽인지 적는다 |
| Python | `python --version` 또는 `py --version` | 3.11 이상 | Windows는 `py` 런처를 쓸 수도 있다 |
| pytest | `python -m pytest --version` | 설치만 하면 된다(녹화본 9.2.0) | `python -m pip install pytest` |
| git | `git --version` | 아무 최신 버전 | Windows는 Git Bash가 같이 깔린다. 두 번째 명령(JSON 스키마)은 Git Bash에서 돌린다 |
| VSCode | 실행 | 아무 최신 버전 | 터미널 2개를 쓴다 |
| 브라우저 | 실행 | 아무 최신 버전 | 리포트를 `file://`로 연다 |
| Codex | 앱 또는 CLI 로그인 | 주최 측 계정 | 교차 리뷰용. 필수는 아님 |

**설치하지 않는 것:** 프로젝트 의존성(`pip install -e .[dev]`)은 목요일 S0에서 한다. 지금 깔 필요 없다. 라이브러리는 표준 라이브러리만 쓴다.

**추가 확인이 필요한 것:** Claude Code를 어떤 방식으로 설치하는지는 주최 측이 준 PC에 따라 다르다. 설치 방식이 확인되지 않으면 `where claude`(Windows) 결과와 함께 적어 온다.

## 0. 도착하면 먼저 물어볼 것 (2분)

1. "환경 점검용 스크립트(`setup/check_env.py`)를 한 번 돌려도 되나요? 설치·수정 없이 확인만 합니다."
   - 된다 → 아래 3단계에서 스크립트를 쓴다.
   - 안 된다 → 스크립트는 돌리지 않고, 3단계를 손으로 한다.
2. "목요일에 만든 코드는 어느 저장소에 올리나요?" (이 저장소인지, 주최 측이 준 저장소인지)
3. "나눠 주는 Claude 계정은 구독 로그인인가요, API 키인가요? 사용량 한도는 얼마인가요?"

## 1. 계정 로그인 (10분)

- [ ] 나눠 준 **Claude 계정**으로 Claude Code에 로그인한다. 개인 계정은 쓰지 않는다.
- [ ] 나눠 준 **Codex 계정**으로 로그인한다(교차 리뷰와 Claude 장애 때의 대체용).
- [ ] 터미널에서 `claude --version`을 적는다(녹화본은 2.1.322, 더 높아도 된다).

## 2. 저장소 받기 (5분)

```bash
git clone https://github.com/samsung-sds-hackathon/xhuman.git
cd xhuman
```

- [ ] 폴더에 `CLAUDE.md`, `README.md`, `docs/`, `tests/fixtures/`, `setup/`이 있다.
- [ ] `pip install pytest`가 된다(주최 측: 가능).

## 3. 한 번에 점검 (10분)

### 스크립트를 써도 될 때

```bash
python setup/check_env.py
```

`python`이 안 되면 `python3` 또는 `py`로 바꾼다. 출력 전체를 사진이나 복사로 남긴다.

**됨이 나와야 하는 것:** Python 3.11 이상, pip, pytest, git, 전달 저장소 폴더, 사전 작성 코드 없음, 샘플 테스트 43개, 대화 기록 133줄, claude 명령, 1·2·3번 Claude 호출.

**"안 됨"이 나오면:**

| 항목 | 할 일 |
|---|---|
| pytest | `python -m pip install pytest` 후 다시 실행 |
| 1. 한 번 호출 | 로그인 상태 확인(`claude`를 그냥 실행해 로그인 화면이 뜨는지) |
| 2·3. 형식 지정, 모델 선택 | 아래 "손으로 할 때"의 2·3번 명령을 **직접 한 번 더** 해 본다. 스크립트는 실패하고 손으로는 성공하면 꼭 적는다(목요일 구현에 영향) |
| claude 실행 파일 종류 "주의" | `.cmd` 래퍼라는 뜻. 위와 같이 2·3번을 손으로도 해 본다 |
| 그 밖 | 오류 문구를 그대로 적어 온다 |

### 손으로 할 때 (스크립트를 못 쓰거나, 2·3번이 실패했을 때)

```bash
python --version
python -m pytest --version
cd tests/fixtures/demo-payment
python -m pytest -q          # 43 passed
cd ../../..
```

Claude 4가지:

1. 한 번 호출 → JSON이 나오고 `"is_error": false`

   ```bash
   claude -p "ok" --output-format json
   ```

2. 형식 지정 → 결과에 `"structured_output": {"ok": true}`

   ```bash
   claude -p "ok라고만 답해" --model haiku --tools "" --no-session-persistence --setting-sources "" --output-format json --json-schema '{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}'
   ```

   Windows 명령 프롬프트(cmd)에서는 작은따옴표가 안 통한다. Git Bash나 PowerShell 7에서 위 명령을 그대로 쓴다. 따옴표 때문에 실패한 것과 기능이 없어서 실패한 것을 구분해 적는다.

3. 모델 선택 → 2번 명령의 `haiku`를 `sonnet`으로 바꿔 한 번 더. 둘 다 되어야 한다.

4. 한도와 방식 → 0단계에서 물은 답을 적는다. Claude Code 안에서 `/status`로도 볼 수 있다.

## 4. 그 밖 (10분)

- [ ] 푸시 인증: `git push --dry-run` (빈 커밋을 만들지 않는다)
- [ ] 브라우저에서 로컬 HTML 파일이 열리는지(아무 `.html`이나 더블클릭. 리포트가 `file://`로 열린다)
- [ ] VSCode에서 `xhuman` 폴더 열기, 터미널 2개(개발용, `xh` 실행용)

## 5. 시간이 남으면

- [ ] 발표 화면 연결: 외부 모니터·프로젝터, 터미널 글자 18pt 이상, 밝은 테마
- [ ] 캡처 도구 동작과 저장 위치

## 6. 끝나고 적어 올 것

| 항목 | 결과 |
|---|---|
| Claude 계정 방식(구독/API 키), 한도 | |
| `claude --version` | |
| Claude 1·2·3번(스크립트 / 손) | |
| claude 실행 파일 종류(`.exe` / `.cmd`) | |
| Python 버전, pytest | |
| 샘플 테스트 43개 | |
| 푸시 인증, 목요일 코드를 올릴 저장소 | |
| 로컬 HTML 열기 | |
| 안 된 것과 오류 문구 | |

## 목요일 08:00에 가장 먼저

1. 오늘 안 된 것이 있으면 그것부터.
2. **`setup/` 폴더를 지우고 커밋한다.** 이 폴더는 XHuman 코드가 아니고 환경 점검용이다. 제품 코드에 사전 작성 코드가 섞이지 않게 한다.

   ```bash
   git rm -r setup
   git commit -m "환경 점검 도구 삭제(구현 시작 전)"
   ```

3. 그다음은 `docs/build-plan.md` 1장 시간표의 S0부터.

자세한 배경은 `docs/build-plan.md` 0장에 있다.
