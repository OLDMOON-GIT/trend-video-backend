# YouTube API 설정 가이드

이 가이드는 YouTube Data API v3를 활성화하고 OAuth2 인증을 설정하는 방법을 설명합니다.

## 1. Google Cloud Console 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. 프로젝트 이름: `trend-video-backend` (원하는 이름 입력)

## 2. YouTube Data API v3 활성화

1. Google Cloud Console에서 **API 및 서비스** > **라이브러리** 선택
2. "YouTube Data API v3" 검색
3. **YouTube Data API v3** 선택 후 **사용 설정** 클릭

## 3. OAuth 2.0 클라이언트 ID 생성

### 3.1 OAuth 동의 화면 구성

1. **API 및 서비스** > **OAuth 동의 화면** 선택
2. 사용자 유형: **외부** 선택 (테스트용은 외부로 설정)
3. 앱 정보 입력:
   - 앱 이름: `Trend Video Backend`
   - 사용자 지원 이메일: 본인 이메일
   - 개발자 연락처 정보: 본인 이메일
4. 범위 추가:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube.force-ssl`
5. 테스트 사용자 추가:
   - YouTube 채널을 소유한 Google 계정 이메일 추가
6. **저장 후 계속** 클릭

### 3.2 OAuth 2.0 클라이언트 ID 생성

1. **API 및 서비스** > **사용자 인증 정보** 선택
2. **+ 사용자 인증 정보 만들기** > **OAuth 클라이언트 ID** 선택
3. 애플리케이션 유형: **데스크톱 앱** 선택
4. 이름: `Trend Video Desktop Client`
5. **만들기** 클릭
6. **JSON 다운로드** 버튼 클릭하여 credentials 파일 다운로드

## 4. Credentials 파일 배치

1. 다운로드한 JSON 파일을 `trend-video-backend/config/` 폴더에 복사
2. 파일 이름을 `youtube_client_secret.json`으로 변경

```bash
# 예시 경로
trend-video-backend/
└── config/
    └── youtube_client_secret.json
```

## 5. 백엔드 의존성 설치

```bash
cd trend-video-backend
pip install -r requirements.txt
```

필요한 패키지:
- `google-api-python-client>=2.0.0`
- `google-auth-httplib2>=0.2.0`
- `google-auth-oauthlib>=1.2.0`
- `google-auth>=2.27.0`

## 6. 첫 인증 테스트

프론트엔드에서 YouTube 설정 페이지로 이동하여 채널 연결을 시도합니다:

1. 프론트엔드 실행: `http://localhost:3000`
2. 내 콘텐츠 페이지에서 **YouTube 설정** 버튼 클릭
3. **YouTube 채널 연결** 버튼 클릭
4. 브라우저가 열리며 Google OAuth 인증 화면 표시
5. YouTube 채널을 소유한 Google 계정으로 로그인
6. 권한 승인 후 자동으로 토큰 저장
7. 채널 정보가 표시되면 성공!

## 7. 토큰 저장 위치

인증 완료 후 토큰은 다음 위치에 저장됩니다:

```
trend-video-backend/config/youtube_token_{userId}.json
```

- 각 사용자별로 별도의 토큰 파일 생성
- 토큰은 자동으로 갱신됨 (refresh token 포함)
- `.gitignore`에 추가하여 GitHub에 업로드되지 않도록 주의!

## 8. 문제 해결

### 오류: "redirect_uri_mismatch"

- OAuth 클라이언트 ID 설정에서 리디렉션 URI 확인
- 데스크톱 앱의 경우 `http://localhost` 자동 허용

### 오류: "insufficient permissions"

- OAuth 동의 화면에서 필요한 scope 추가 확인:
  - `https://www.googleapis.com/auth/youtube.upload`
  - `https://www.googleapis.com/auth/youtube.force-ssl`

### 오류: "The user did not consent"

- OAuth 동의 화면의 테스트 사용자 목록에 해당 계정 추가
- 앱이 "테스트" 모드인 경우 최대 100명의 테스트 사용자 추가 가능

### 토큰 만료 오류

- 토큰 파일 삭제 후 재인증:
  ```bash
  rm config/youtube_token_*.json
  ```
- 프론트엔드에서 다시 **YouTube 채널 연결** 실행

## 9. 프로덕션 배포 시 주의사항

현재 설정은 개발/테스트 환경용입니다. 프로덕션 배포 시:

1. OAuth 동의 화면을 "게시" 상태로 변경 (Google 검토 필요)
2. 웹 애플리케이션 타입으로 OAuth 클라이언트 변경
3. 승인된 리디렉션 URI 설정
4. 환경 변수로 credentials 관리
5. HTTPS 사용 필수

## 10. API 할당량

YouTube Data API v3 무료 할당량:
- 일일 할당량: 10,000 units
- 비디오 업로드: 1,600 units/업로드
- 채널 정보 조회: 1 unit/요청

일일 약 6개의 비디오 업로드 가능 (무료 할당량 기준)

할당량 초과 시:
1. [Google Cloud Console](https://console.cloud.google.com/)에서 할당량 증가 요청
2. 또는 유료 플랜 구독

## 참고 자료

- [YouTube Data API v3 문서](https://developers.google.com/youtube/v3)
- [OAuth 2.0 가이드](https://developers.google.com/identity/protocols/oauth2)
- [Python 빠른 시작](https://developers.google.com/youtube/v3/quickstart/python)
