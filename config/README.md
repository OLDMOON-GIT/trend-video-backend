# Config Directory

이 디렉토리는 YouTube API credentials 및 token 파일을 저장합니다.

## 필요한 파일

1. `youtube_client_secret.json` - Google Cloud Console에서 다운로드한 OAuth 2.0 클라이언트 ID 파일
2. `youtube_token_{userId}.json` - 사용자별 인증 토큰 (자동 생성됨)

## 설정 방법

상위 디렉토리의 `YOUTUBE_SETUP.md` 파일을 참조하세요.

## 주의사항

- 이 디렉토리의 파일들은 `.gitignore`에 포함되어 GitHub에 업로드되지 않습니다.
- credentials 및 token 파일은 절대로 공유하거나 커밋하지 마세요.
- 백업이 필요한 경우 안전한 곳에 별도로 저장하세요.
