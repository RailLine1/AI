"""
GitHub Actions 에서 Daybit 작업 하나를 처리해요.

1. GitHub OIDC 토큰을 받아요 (audience=daybit). Daybit 는 이 토큰으로 요청한 저장소를 확인해요.
2. Daybit 에서 작업 내용(출제 규칙 · 응답 스키마 · 자료 본문)을 받아요.
3. 내 구독 AI(Claude Code 또는 Codex)를 비대화 모드로 실행해 문제 JSON 을 만들어요.
4. 결과를 Daybit 로 보내요. 어느 단계든 실패하면 오류 내용을 보내요(Daybit 가 Gemini 로 전환).

표준 라이브러리만 써요. [검증 필요] 두 CLI 의 비대화 실행 옵션은 실제 Actions 에서 확인해야 해요.
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

AUDIENCE = "daybit"
TIMEOUT_SEC = 15 * 60
# Claude Code 내장 도구를 모두 꺼요. 자료 본문에 숨긴 지시로 파일(/proc/self/environ 등)을 읽어 토큰을 빼내지 못하게 해요
CLAUDE_TOOLS = "Bash,BashOutput,KillShell,Edit,MultiEdit,Write,Read,NotebookEdit,Glob,Grep,LS,WebFetch,WebSearch,Task,TodoWrite,SlashCommand,Skill"


def oidc_token():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    url += ("&" if "?" in url else "?") + "audience=" + urllib.parse.quote(AUDIENCE)
    req = urllib.request.Request(url, headers={"Authorization": "bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read())["value"]


def call(method, url, token, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


def build_prompt(job):
    return (
        job["system"]
        + "\n\n응답은 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력한다. 설명이나 코드 블록 표시는 붙이지 않는다.\n"
        + json.dumps(job["schema"], ensure_ascii=False)
        + "\n\n"
        + job["prompt"]
    )


def run_ai(ai, prompt):
    """AI 가 낸 글(문제 JSON 이 들어 있는 텍스트)을 돌려줘요"""
    if ai == "claudecode":
        # -p: 비대화 실행. 도구는 하나도 쓰지 않고 답만 내게 해요. MCP 설정도 읽지 않아요
        cmd = ["claude", "-p", "--output-format", "json", "--disallowedTools", CLAUDE_TOOLS, "--strict-mcp-config"]
        out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SEC)
        if out.returncode != 0:
            raise RuntimeError("claude 실행 실패: " + (out.stderr or out.stdout)[-500:])
        result = json.loads(out.stdout)
        if result.get("is_error"):
            raise RuntimeError("claude 오류: " + str(result.get("result"))[:500])
        return result.get("result", "")
    if ai == "codex":
        # exec: 비대화 실행. "-" 면 프롬프트를 표준 입력으로 받아요
        # 읽기 전용 샌드박스. [검증 필요] 셸로 파일을 읽는 것까지는 못 막아서 보내기 전에 check_no_secrets 로 한 번 더 걸러요
        cmd = ["codex", "exec", "--sandbox", "read-only", "--skip-git-repo-check", "--output-last-message", "codex-out.txt", "-"]
        out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SEC)
        if out.returncode != 0:
            raise RuntimeError("codex 실행 실패: " + (out.stderr or out.stdout)[-500:])
        with open("codex-out.txt", encoding="utf-8") as f:
            return f.read()
    raise RuntimeError("알 수 없는 AI: " + ai)


def extract_questions(text):
    """답에서 JSON 객체를 꺼내요. 코드 블록이나 앞뒤 설명이 붙어 있어도 첫 { 부터 마지막 } 까지 읽어요"""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("답에서 JSON 을 찾지 못했어요: " + text[:300])
    questions = json.loads(text[start:end + 1]).get("questions")
    if not isinstance(questions, list) or not questions:
        raise RuntimeError("questions 가 비었어요")
    return questions


def secret_values():
    """이 실행에서 쓰는 구독 토큰 값들. 결과에 섞여 나가면 안 돼요"""
    values = []
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if token:
        values.append(token)
    auth = os.path.expanduser("~/.codex/auth.json")
    if os.path.exists(auth):
        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
            elif isinstance(node, str) and len(node) >= 20:
                values.append(node)
        try:
            with open(auth, encoding="utf-8") as f:
                walk(json.load(f))
        except Exception:
            pass
    return values


def check_no_secrets(questions, secrets):
    """결과에 토큰 원문이나 base64 가 들어 있으면 보내지 않고 실패 처리해요 (자료 속 지시로 토큰을 빼내는 경로 차단)"""
    text = json.dumps(questions, ensure_ascii=False)
    compact = re.sub(r"\s+", "", text)
    for value in secrets:
        encoded = base64.b64encode(value.encode()).decode()
        for needle in (value, value[:24], encoded[:32]):
            if needle and (needle in text or needle in compact):
                raise RuntimeError("결과에 로그인 정보로 보이는 값이 있어 보내지 않았어요")


def main():
    server = os.environ["DAYBIT_SERVER"].rstrip("/")
    job_id = os.environ["DAYBIT_JOB_ID"]
    ai = os.environ["DAYBIT_AI"]
    base = f"{server}/internal/workspace/jobs/{job_id}"

    token = oidc_token()
    try:
        job = call("GET", base, token)
        questions = extract_questions(run_ai(ai, build_prompt(job)))
        check_no_secrets(questions, secret_values())
        call("POST", base + "/result", oidc_token(), {"questions": questions})
        print(f"문제 {len(questions)}개를 보냈어요")
    except Exception as e:  # 실패 내용을 Daybit 에 알려야 Gemini 로 전환돼요
        message = f"{type(e).__name__}: {e}"[:500]
        print("실패:", message, file=sys.stderr)
        try:
            call("POST", base + "/result", oidc_token(), {"error": message})
        except Exception as report_error:
            print("실패 보고도 못 했어요:", report_error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
