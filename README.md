# Trend Video Backend

AI 기반 트렌드 비디오 생성 백엔드 API 서버

## 주요 기능

- 스토리 생성 (OpenAI GPT 기반)
- 이미지 생성 (DALL-E, Replicate, Hugging Face)
- 음성 나레이션 생성 (Edge TTS, OpenAI TTS)
- 비디오 렌더링 (MoviePy)
- 트렌드 분석 및 추천

## 기술 스택

- **Framework**: FastAPI
- **AI/ML**: OpenAI API, Hugging Face, Replicate
- **Video Processing**: MoviePy, OpenCV, FFmpeg
- **TTS**: Edge-TTS (무료), OpenAI TTS
- **Database**: SQLite (개발), PostgreSQL (프로덕션)

## API 엔드포인트

### 스토리 생성
- `POST /api/v1/story/generate` - 프롬프트로 스토리 생성
- `POST /api/v1/story/from-json` - JSON 스크립트로 비디오 생성
- `GET /api/v1/story/{story_id}` - 스토리 조회

### 비디오 생성
- `POST /api/v1/video/create` - 비디오 생성
- `GET /api/v1/video/{video_id}/status` - 비디오 생성 상태 조회
- `GET /api/v1/video/{video_id}/download` - 비디오 다운로드

### 트렌드 분석
- `GET /api/v1/trends/youtube` - YouTube 트렌드 분석
- `GET /api/v1/trends/recommend` - 트렌드 기반 추천

## 설치 및 실행

### 요구사항
```bash
Python 3.9+
FFmpeg
```

### 설치
```bash
pip install -r requirements.txt
```

### 환경 변수 설정
`.env` 파일 생성:
```env
# OpenAI (선택)
OPENAI_API_KEY=your_openai_api_key

# Groq (무료 대안)
GROQ_API_KEY=your_groq_api_key

# Replicate (저렴한 이미지 생성)
REPLICATE_API_TOKEN=your_replicate_token

# Hugging Face (무료 이미지 생성)
HUGGINGFACE_API_KEY=your_hf_api_key

# 데이터베이스
DATABASE_URL=sqlite:///./trend_video.db

# 서버 설정
API_HOST=0.0.0.0
API_PORT=8000
```

### 실행
```bash
# 개발 모드
uvicorn app.main:app --reload

# 프로덕션 모드
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 디렉토리 구조

```
trend-video-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 앱 진입점
│   ├── config.py               # 설정 관리
│   ├── database.py             # 데이터베이스 설정
│   ├── models/                 # SQLAlchemy 모델
│   │   ├── __init__.py
│   │   ├── story.py
│   │   ├── video.py
│   │   └── user.py
│   ├── schemas/                # Pydantic 스키마
│   │   ├── __init__.py
│   │   ├── story.py
│   │   └── video.py
│   ├── api/                    # API 라우터
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── story.py
│   │   │   ├── video.py
│   │   │   └── trends.py
│   ├── services/               # 비즈니스 로직
│   │   ├── __init__.py
│   │   ├── story_service.py
│   │   ├── video_service.py
│   │   ├── image_service.py
│   │   ├── narration_service.py
│   │   └── trend_service.py
│   └── utils/                  # 유틸리티
│       ├── __init__.py
│       ├── video_utils.py
│       └── file_utils.py
├── prompts/                    # 프롬프트 템플릿
│   └── long_form_prompt.txt
├── tests/                      # 테스트
├── requirements.txt            # Python 의존성
├── .env.example               # 환경 변수 예제
├── .gitignore
└── README.md
```

## 라이센스

MIT License
