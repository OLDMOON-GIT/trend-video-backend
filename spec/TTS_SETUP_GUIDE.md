# TTS (Text-to-Speech) 설정 가이드

이 프로젝트는 3가지 TTS 제공자를 지원합니다:

## 1. Edge TTS (무료) ✅ 기본값

- **상태**: 즉시 사용 가능
- **요금**: 무료
- **품질**: 높음
- **설정 필요**: 없음
- **지원 음성**:
  - 선희, 지민, 서현, 순복, 유진 (여성)
  - 인준, 현수, 봉진, 국민 (남성)

## 2. Google Cloud TTS (프리미엄) 💎

### 요금
- Neural2: 분당 $0.006
- Wavenet: 분당 $0.016

### 지원 음성
- google-ko-KR-Neural2-A (구글A - 여성)
- google-ko-KR-Neural2-B (구글B - 여성)
- google-ko-KR-Neural2-C (구글C - 여성)
- google-ko-KR-Wavenet-D (구글D - 남성)

### 설정 방법

#### 1단계: 패키지 설치
```bash
pip install google-cloud-texttospeech>=2.14.0
```

#### 2단계: Google Cloud Console 설정
1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. Cloud Text-to-Speech API 활성화
   - API 및 서비스 > 라이브러리
   - "Cloud Text-to-Speech API" 검색 및 활성화
4. 결제 계정 연결 (필수)

#### 3단계: 서비스 계정 생성
1. IAM 및 관리자 > 서비스 계정
2. "서비스 계정 만들기" 클릭
3. 이름 입력 (예: "tts-service-account")
4. 역할 선택: "Cloud Text-to-Speech 사용자"
5. 완료 후 서비스 계정 클릭
6. "키" 탭 > "키 추가" > "새 키 만들기"
7. JSON 형식 선택 → 키 파일 다운로드

#### 4단계: 환경 변수 설정
다운로드한 JSON 키 파일을 프로젝트 폴더에 저장하고 환경 변수 설정:

**Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\your-service-account-key.json"
```

**Windows (.env 파일):**
```bash
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\your-service-account-key.json
```

**Linux/Mac:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-service-account-key.json"
```

#### 5단계: 테스트
```bash
python -c "from google.cloud import texttospeech; client = texttospeech.TextToSpeechClient(); print('Google TTS 연결 성공!')"
```

## 3. AWS Polly (프리미엄) 🌟

### 요금
- Neural: 분당 $0.004 (가장 저렴!)

### 지원 음성
- aws-Seoyeon (AWS서연 - 여성)
- aws-Jihye (AWS지혜 - 여성)

### 설정 방법

#### 1단계: 패키지 설치
```bash
pip install boto3>=1.28.0
```

#### 2단계: AWS 계정 설정
1. [AWS Console](https://console.aws.amazon.com/) 접속
2. IAM > 사용자 > "사용자 추가"
3. 액세스 유형: "프로그래밍 방식 액세스" 선택
4. 권한: "AmazonPollyFullAccess" 정책 연결
5. Access Key ID와 Secret Access Key 저장 (한 번만 표시됨!)

#### 3단계: AWS CLI 설정
```bash
aws configure
```

입력 값:
```
AWS Access Key ID: [your-access-key-id]
AWS Secret Access Key: [your-secret-access-key]
Default region name: us-east-1
Default output format: json
```

**또는 .env 파일 사용:**
```bash
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_DEFAULT_REGION=us-east-1
```

#### 4단계: 테스트
```bash
python -c "import boto3; client = boto3.client('polly', region_name='us-east-1'); print('AWS Polly 연결 성공!')"
```

## 자동 대체 (Fallback) 시스템 ✨

설정이 완료되지 않은 경우 자동으로 Edge TTS로 대체됩니다:

```
Google TTS 선택 → Google Cloud 미설정 → Edge TTS로 자동 전환
AWS Polly 선택 → AWS 미설정 → Edge TTS로 자동 전환
```

## 문제 해결

### Google Cloud TTS 오류
```
google.auth.exceptions.DefaultCredentialsError
```
→ `GOOGLE_APPLICATION_CREDENTIALS` 환경 변수 확인

### AWS Polly 오류
```
botocore.exceptions.NoCredentialsError
```
→ `aws configure` 실행 또는 .env 파일 확인

### 패키지 설치 오류
```bash
# 관리자 권한으로 실행 (Windows)
pip install --upgrade pip
pip install -r requirements.txt
```

## 비용 비교

| 제공자 | 음성 품질 | 분당 요금 | 월 100분 기준 | 추천 용도 |
|--------|----------|-----------|--------------|-----------|
| Edge TTS | ⭐⭐⭐⭐⭐ | 무료 | $0 | 일반 사용 |
| AWS Polly | ⭐⭐⭐⭐⭐ | $0.004 | $0.40 | 대량 제작 |
| Google Neural2 | ⭐⭐⭐⭐⭐ | $0.006 | $0.60 | 고품질 |
| Google Wavenet | ⭐⭐⭐⭐⭐ | $0.016 | $1.60 | 최고품질 |

## 추가 정보

- word-level timestamps 지원: 모든 제공자 지원 ✅
- 자막 동기화: 자동 처리 ✅
- 다중 제공자: 프로젝트마다 다른 음성 사용 가능 ✅

---

## 미리듣기 샘플 생성

서버 시작 전에 모든 음성의 미리듣기 샘플을 생성해야 합니다.

### 샘플 생성 명령어

```bash
cd trend-video-backend
python generate_preview_samples.py
```

### 샘플 생성 과정

1. **Edge TTS 샘플** (무료) - 항상 생성됨
   - 10개 음성 × 4개 속도 = 40개 파일

2. **Google Cloud TTS 샘플** (프리미엄) - credential 설정 시에만 생성
   - 4개 음성 × 4개 속도 = 16개 파일

3. **AWS Polly 샘플** (프리미엄) - credential 설정 시에만 생성
   - 2개 음성 × 4개 속도 = 8개 파일

### 파일 저장 위치

```
trend-video-backend/
  └── preview_samples/
      ├── sample_ko-KR-SunHiNeural_1.0.mp3
      ├── sample_google-ko-KR-Neural2-A_1.0.mp3
      ├── sample_aws-Seoyeon_1.0.mp3
      └── ...
```

### 재생성 방지

- 파일이 이미 존재하면 스킵됩니다
- 변경사항이 있을 때만 재생성하면 됩니다
- 삭제 후 재실행하면 모든 파일 재생성됩니다

### 샘플 파일 크기

- Edge TTS: 약 20-30 KB/파일
- Google Cloud TTS: 약 25-35 KB/파일
- AWS Polly: 약 20-30 KB/파일
- **총 용량**: 약 1.5-2.0 MB (모든 음성 포함)

---

**참고**: 관리자 계정만 프리미엄 음성을 선택할 수 있습니다.
