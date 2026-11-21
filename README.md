# Discord Moderation Bot

## GitHub Secrets 설정

1. GitHub 저장소의 **Settings → Secrets and variables → Actions**로 이동합니다.
2. **New repository secret**을 누릅니다.
3. Name에 `DISCORD_TOKEN`, Secret에 Discord Developer Portal의 봇 토큰을 입력합니다.
4. `main.py`의 `GUILD_ID`, `LOG_CHANNEL_ID`를 실제 ID로 변경합니다.
   - 로그 채널을 사용하지 않으려면 `LOG_CHANNEL_ID = 0`으로 설정합니다.

## 실행

GitHub 저장소의 **Actions → Discord Moderation Bot → Run workflow**에서 실행할 수 있습니다.
`main` 브랜치에 push해도 워크플로가 시작됩니다.

## 주의

- 봇 토큰을 코드, README, 커밋 메시지에 직접 입력하지 마세요.
- 이 워크플로는 GitHub Actions의 실행 시간 제한을 받으므로 24시간 상시 호스팅 용도로 적합하지 않습니다.
- GitHub Actions 실행 환경은 임시 환경입니다. `warnings.db`는 실행이 끝난 뒤 보존되지 않을 수 있습니다. 경고 기록을 영구 보존하려면 외부 DB 또는 별도 영구 저장소가 필요합니다.
