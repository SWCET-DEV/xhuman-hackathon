"""해커톤 PC 환경 점검 (2026-11-11 사전 설치용).

쓰는 법:  python setup/check_env.py            (전달 저장소를 클론한 폴더에서 실행)
          python setup/check_env.py --no-claude  (Claude 호출 없이 도구만 점검)

하는 일: 확인만 한다. 아무것도 설치하지 않고, 저장소 폴더의 파일을 만들거나 고치지 않는다.
        부수 효과(숨기지 않음): 샘플 테스트 중 일부가 시스템 임시 폴더에 임시 DB를 만들었다 지운다(pytest tmp_path).
        Claude 호출은 3번(짧은 질문)이고, 모두 도구 없음·세션 저장 안 함·사용자 설정 안 읽음으로 부른다.
        API 키 방식 계정이면 합쳐서 1달러 안팎이 청구될 수 있다. 호출 없이 보려면 --no-claude.
못 하는 일: 로그인, 사용량 한도 확인, 화면 연결. 이것은 사람이 직접 한다(맨 아래에 다시 알려 준다).

이 파일은 XHuman 제품 코드가 아니고 환경 점검 도구다. 목요일 구현을 시작하기 전에 setup/ 폴더를 지우고 커밋한다.
구현 중에 이 파일의 claude 호출·JSON 처리 코드를 참고하거나 옮기지 않는다(xhuman/llm은 docs만 보고 새로 쓴다).
표준 라이브러리만 쓴다.
"""

import json
import os
import shutil
import subprocess
import sys
import time

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
NEEDED_FLAGS = ["--json-schema", "--tools", "--no-session-persistence", "--setting-sources", "--output-format", "--model"]
results = []


def record(name, status, detail=""):
    """status: OK / FAIL / WARN / SKIP"""
    results.append((name, status, detail))
    mark = {"OK": "[ 됨 ]", "FAIL": "[안 됨]", "WARN": "[주의]", "SKIP": "[건너뜀]"}[status]
    print(f"{mark} {name}" + (f"  - {detail}" if detail else ""), flush=True)


def run(args, timeout=120, cwd=None):
    """명령을 실행해 (종료 코드, 표준 출력, 표준 오류, 걸린 초)를 돌려준다. 셸을 거치지 않는다."""
    start = time.time()
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")  # 점검 중 __pycache__를 만들지 않는다
        p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, cwd=cwd, stdin=subprocess.DEVNULL, env=env)
        return p.returncode, p.stdout or "", p.stderr or "", time.time() - start
    except subprocess.TimeoutExpired:
        return -1, "", f"{timeout}초 안에 끝나지 않음", time.time() - start
    except OSError as e:
        return -2, "", str(e), time.time() - start


def short(text, n=160):
    text = " ".join((text or "").split())
    return text[:n] + ("..." if len(text) > n else "")


def check_python():
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 11)
    record("Python 3.11 이상", "OK" if ok else "FAIL", f"{v.major}.{v.minor}.{v.micro} ({sys.executable})")
    code, out, err, _ = run([sys.executable, "-m", "pip", "--version"])
    record("pip 동작", "OK" if code == 0 else "FAIL", short(out or err, 80))
    code, out, err, _ = run([sys.executable, "-m", "pytest", "--version"])
    if code == 0:
        record("pytest 설치됨", "OK", short(out or err, 60))
    else:
        record("pytest 설치됨", "FAIL", f"설치: {os.path.basename(sys.executable)} -m pip install pytest  (그 뒤 이 점검을 다시 실행)")


def check_git_and_repo():
    if not shutil.which("git"):
        record("git 설치됨", "FAIL", "git을 찾지 못함")
        return
    code, out, err, _ = run(["git", "--version"])
    record("git 설치됨", "OK" if code == 0 else "FAIL", short(out or err, 60))

    here = os.getcwd()
    wanted = ["CLAUDE.md", "README.md", "docs", os.path.join("tests", "fixtures")]
    missing = [w for w in wanted if not os.path.exists(os.path.join(here, w))]
    if missing:
        record("전달 저장소 폴더", "SKIP", "이 폴더는 전달 저장소가 아님(클론한 폴더 안에서 다시 실행하면 저장소도 점검)")
        return
    record("전달 저장소 폴더", "OK", here)

    stray = []
    for root, dirs, files in os.walk(here):
        dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__", ".pytest_cache")]
        rel = os.path.relpath(root, here).replace("\\", "/")
        in_sample = rel == "tests/fixtures/demo-payment" or rel.startswith("tests/fixtures/demo-payment/")
        for f in files:
            path = f if rel == "." else f"{rel}/{f}"
            if f.endswith(".py") and not in_sample and path != "setup/check_env.py":
                stray.append(path)
    has_proto = os.path.isdir(os.path.join(here, "prototype"))
    if stray or has_proto:
        record("사전 작성 코드 없음", "FAIL", ("prototype 폴더 있음. " if has_proto else "") + "샘플 밖 .py: " + ", ".join(stray[:5]))
    else:
        record("사전 작성 코드 없음", "OK", "샘플 프로젝트 밖에 .py 없음, prototype 폴더 없음")

    sample = os.path.join(here, "tests", "fixtures", "demo-payment")
    code, out, err, sec = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=sample, timeout=180)
    tail = short((out or err).strip().splitlines()[-1] if (out or err).strip() else "", 80)
    record("샘플 프로젝트 테스트(43개)", "OK" if code == 0 and "43 passed" in out else "FAIL", f"{tail} ({sec:.1f}초)")

    session = os.path.join(here, "tests", "fixtures", "demo_session.jsonl")
    try:
        with open(session, encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip() and json.loads(line))
        record("시연 대화 기록 읽기", "OK" if n == 133 else "WARN", f"{n}줄(기대 133)")
    except Exception as e:  # 파일 깨짐, 인코딩 문제 등
        record("시연 대화 기록 읽기", "FAIL", short(str(e), 100))

    code, out, err, _ = run(["git", "remote", "-v"], cwd=here)
    record("git 원격 저장소", "OK" if code == 0 and out.strip() else "WARN", short(out, 120))


def claude_call(exe, model, with_schema):
    args = [exe, "-p", "ok라고만 답해", "--output-format", "json",
            "--tools", "", "--no-session-persistence", "--setting-sources", ""]
    if with_schema:
        args += ["--model", model, "--json-schema", json.dumps(SCHEMA)]
    code, out, err, sec = run(args, timeout=150)
    try:
        data = json.loads(out)
    except ValueError:
        return False, f"JSON이 아님: {short(out or err, 140)}", sec, None
    if data.get("is_error"):
        return False, f"is_error: {short(str(data.get('result')), 140)}", sec, data
    if with_schema:
        so = data.get("structured_output")
        if not isinstance(so, dict) or "ok" not in so:
            return False, f"structured_output 없음. result: {short(str(data.get('result')), 100)}", sec, data
    return True, "", sec, data


def check_claude():
    exe = shutil.which("claude")
    if not exe:
        record("claude 명령", "FAIL", "claude를 찾지 못함(Claude Code 설치와 PATH 확인)")
        return
    kind = os.path.splitext(exe)[1].lower()
    record("claude 명령", "OK", exe)
    if os.name == "nt" and kind in (".cmd", ".bat", ".ps1"):
        record("claude 실행 파일 종류", "WARN",
               f"{kind} 래퍼다. 프로그램이 JSON 스키마를 인자로 넘길 때 따옴표가 깨질 수 있다. 아래 2·3번 결과를 꼭 본다")
    code, out, err, _ = run([exe, "--version"])
    record("Claude Code 버전", "OK" if code == 0 else "FAIL", short(out or err, 60) + " (녹화본은 2.1.322)")

    code, out, err, _ = run([exe, "--help"])
    helptext = out + err
    missing = [f for f in NEEDED_FLAGS if f not in helptext]
    record("필요한 옵션이 --help에 있음", "OK" if not missing else "WARN", "없음: " + ", ".join(missing) if missing else "")

    ok, why, sec, data = claude_call(exe, None, with_schema=False)
    record("1. 한 번 호출(claude -p)", "OK" if ok else "FAIL", why or f"{sec:.1f}초")
    if not ok:
        record("2. 형식 지정(--json-schema)", "SKIP", "1번이 안 되어 건너뜀. 로그인 상태를 먼저 확인")
        record("3. 모델 선택(haiku, sonnet)", "SKIP", "")
        return
    ok_h, why_h, sec_h, data_h = claude_call(exe, "haiku", with_schema=True)
    record("2. 형식 지정(--json-schema, haiku)", "OK" if ok_h else "FAIL", why_h or f"{sec_h:.1f}초")
    ok_s, why_s, sec_s, data_s = claude_call(exe, "sonnet", with_schema=True)
    record("3. 모델 선택(sonnet도 됨)", "OK" if ok_s else "FAIL", why_s or f"{sec_s:.1f}초")
    cost = [d.get("total_cost_usd") for d in (data, data_h, data_s) if isinstance(d, dict) and d.get("total_cost_usd") is not None]
    if cost:
        print(f"       참고: 응답에 적힌 비용 합계 ${sum(cost):.4f} (구독이면 실제 청구는 아님)")


def main():
    print("== XHuman 해커톤 환경 점검 ==")
    print(f"운영체제: {sys.platform}, 폴더: {os.getcwd()}\n")
    check_python()
    print()
    check_git_and_repo()
    print()
    if "--no-claude" in sys.argv:
        record("Claude 점검", "SKIP", "--no-claude")
    else:
        check_claude()

    fails = [r for r in results if r[1] == "FAIL"]
    warns = [r for r in results if r[1] == "WARN"]
    print("\n== 요약 ==")
    print(f"됨 {sum(1 for r in results if r[1] == 'OK')}, 안 됨 {len(fails)}, 주의 {len(warns)}, 건너뜀 {sum(1 for r in results if r[1] == 'SKIP')}")
    for name, _, detail in fails:
        print(f"  안 됨: {name} - {detail}")
    for name, _, detail in warns:
        print(f"  주의: {name} - {detail}")
    print("\n== 이 스크립트가 못 하는 것(직접 확인) ==")
    print("  4. Claude 계정이 구독 로그인인지 API 키인지, 사용량 한도가 얼마인지")
    print("  - Codex 계정 로그인")
    print("  - git push 인증(git push --dry-run), 목요일 코드를 올릴 저장소")
    print("  - 브라우저에서 로컬 HTML 열기, 발표 화면 연결")
    print("\n위 출력을 그대로 복사해 두면 된다. 목요일 구현 전에 setup/ 폴더를 지운다.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
