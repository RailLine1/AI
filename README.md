# Daybit AI 작업 공간

Daybit 과목의 복습 문제를 **내 Claude · ChatGPT 구독**으로 만드는 저장소입니다. Daybit 앱의 "AI 작업 공간" 1단계에서 이 템플릿을 복사해 내 GitHub 계정에 비공개 저장소(`daybit-workspace`)가 만들어집니다.

- 구독 로그인 정보는 이 저장소의 Secret에만 저장되고 Daybit 서버는 보지 않습니다.
- Daybit 서버는 이 저장소의 GitHub Actions를 실행시키기만 하고, 결과는 GitHub가 서명한 토큰(OIDC)으로 이 저장소에서 왔는지 확인합니다.
- 실행이 실패하거나 로그인이 만료되면 Daybit는 자동으로 기본 AI(Gemini)로 바꾸고 관리자에게 알립니다.

## 쓰는 방법 (Daybit 앱의 3단계)

1. **GitHub 권한 허용**: 앱에서 [GitHub 연결]을 누르면 이 저장소가 내 계정에 생깁니다.
2. **구독 로그인**: 앱의 [Codespace 열기]로 이 저장소의 Codespace를 열고 터미널에서 실행합니다.
   ```
   daybit-setup claudecode   # Claude Pro · Max
   daybit-setup codex        # ChatGPT Plus · Pro
   ```
3. **샘플 테스트**: 앱에서 [테스트]를 누르면 샘플 3문항을 만들어 봅니다. 성공하면 과목 환경설정의 퀴즈 출처에서 이 AI를 고를 수 있습니다.

## 구성

| 경로 | 내용 |
|---|---|
| `.github/workflows/daybit-generate.yml` | Daybit가 실행을 요청하면 도는 워크플로 |
| `scripts/run_job.py` | 작업 받기 → AI 실행 → 결과 보내기 |
| `bin/daybit-setup` | 구독 로그인 후 Secret 저장 |
| `.devcontainer/` | Codespace 설정 (Claude Code · Codex · GitHub CLI 설치) |
| `eval/` | Daybit 팀의 문제 품질 실험 도구. 작업 공간 동작과는 관계없습니다 |

## 저장되는 Secret

| 이름 | 언제 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `daybit-setup claudecode` (`claude setup-token`으로 만든 장기 토큰) |
| `CODEX_AUTH_JSON` | `daybit-setup codex` (`~/.codex/auth.json`을 base64로) |

로그인을 끊으려면 저장소 Settings › Secrets and variables › Actions에서 지웁니다.
