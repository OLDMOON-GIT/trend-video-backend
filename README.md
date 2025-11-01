# Trend Video Backend 🎬

트렌드 비디오 생성을 위한 통합 백엔드 시스템

## 🚀 주요 기능

### 1. 비디오 생성 (Video Generator)
- **JSON 대본 + 이미지** → 자동 영상 생성
- **롱폼 (16:9)** 및 **숏폼 (9:16)** 지원
- **TTS 나레이션** (Edge TTS, gTTS)
- **ASS 자막** 자동 생성
- **Google Image Search** / **DALL-E 3** 이미지 생성

### 2. 비디오 병합 (Video Merger)
- **여러 비디오 클립 병합** (concat)
- **TTS 나레이션 추가**
- **ASS 자막 오버레이**
- 비디오 길이 유지 (오디오 짧으면 나머지 무음)

### 3. SORA2 통합
- SORA2 AI 시네마틱 영상 생성
- JSON 프롬프트 기반 워크플로우

### 4. AI 스크립트 생성기 (Multi-AI Aggregator)
- **여러 AI에 동시 질문** (ChatGPT, Claude, Gemini, Grok)
- **병렬 처리**로 빠른 응답 수집
- **자동 답변 취합 및 요약**
- 브라우저 자동화를 통한 실제 AI 챗봇 사용

## 📁 프로젝트 구조

```
trend-video-backend/
├── src/
│   ├── video_generator/    # AutoShortsEditor 코드
│   │   ├── story_video_creator.py
│   │   ├── narrator.py
│   │   └── ...
│   ├── sora/               # SoraExtend 코드
│   │   ├── api.py
│   │   ├── main.py
│   │   └── ...
│   └── ai_aggregator/      # Multi-AI Aggregator
│       ├── main.py         # AI 질문 메인 스크립트
│       ├── aggregator.py   # 답변 취합 및 요약
│       ├── agents/         # AI 에이전트들
│       │   ├── chatgpt_agent.py
│       │   ├── claude_agent.py
│       │   ├── gemini_agent.py
│       │   └── grok_agent.py
│       └── refine_and_send.py  # 대본 개선 및 전송
├── create_video_from_folder.py  # 메인 비디오 생성 스크립트
├── video_merge.py               # 비디오 병합 스크립트
├── config/                      # 설정 파일
├── fonts/                       # 자막용 폰트
├── input/                       # 입력 파일
├── output/                      # 출력 비디오
├── logs/                        # 로그 파일
└── requirements.txt             # 의존성

```

## 🛠️ 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/YOUR_USERNAME/trend-video-backend.git
cd trend-video-backend
```

### 2. 가상 환경 생성 (권장)
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

### 4. FFmpeg 설치
- Windows: [FFmpeg 다운로드](https://ffmpeg.org/download.html)
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

## 📖 사용 방법

### 비디오 생성

```bash
python create_video_from_folder.py --folder "input/my_project"
```

**input 폴더 구조:**
```
input/my_project/
├── story.json         # 대본 JSON
├── image_01.jpg       # 씬 1 이미지
├── image_02.jpg       # 씬 2 이미지
└── ...
```

**story.json 예시:**
```json
{
  "title": "나의 영상",
  "scenes": [
    {
      "scene_number": 1,
      "text": "첫 번째 장면의 나레이션"
    },
    {
      "scene_number": 2,
      "text": "두 번째 장면의 나레이션"
    }
  ]
}
```

### 비디오 병합

```bash
python video_merge.py config.json
```

**config.json 예시:**
```json
{
  "video_files": [
    "output/video1.mp4",
    "output/video2.mp4",
    "output/video3.mp4"
  ],
  "narration_text": "전체 나레이션 텍스트",
  "add_subtitles": true,
  "output_dir": "output/merged"
}
```

### AI 스크립트 생성 (Multi-AI Aggregator)

```bash
cd src/ai_aggregator
python main.py -q "중년층을 위한 감동적인 스토리 아이디어 3개 알려줘"
```

**인터랙티브 모드:**
```bash
cd src/ai_aggregator
python main.py -i
```

**특정 AI만 사용:**
```bash
python main.py -q "질문" -a chatgpt,claude
```

**Playwright 브라우저 설치 (최초 1회):**
```bash
playwright install chromium
```

## 🎨 주요 옵션

### 비디오 생성 옵션
- `--aspect-ratio`: `16:9` (롱폼) 또는 `9:16` (숏폼)
- `--image-source`: `none` (직접 업로드), `google` (Google 검색), `dalle` (DALL-E 생성)
- `--voice`: TTS 음성 (기본: `ko-KR-SoonBokNeural`)

### 비디오 병합 옵션
- `add_subtitles`: 자막 추가 여부
- `narration_text`: TTS 나레이션 텍스트

## 🔧 환경 변수

`.env` 파일 생성:
```env
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_API_KEY=your_google_api_key_here
GOOGLE_CSE_ID=your_custom_search_engine_id_here
```

## 📝 기술 스택

- **Python 3.8+**
- **MoviePy**: 비디오 편집
- **OpenCV**: 이미지/비디오 처리
- **Edge TTS**: 고품질 무료 TTS
- **FFmpeg**: 비디오 인코딩
- **OpenAI API**: GPT, DALL-E (옵션)

## 🤝 기여

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

MIT License

## 👥 개발자

- **AutoShortsEditor**: 원본 비디오 생성 엔진
- **SoraExtend**: SORA2 통합 및 비디오 병합
- **Trend Video Backend**: 통합 시스템

## 🙏 감사의 말

- MoviePy 팀
- OpenAI
- Microsoft Edge TTS
- FFmpeg 커뮤니티

---

Made with ❤️ for creating viral shorts
