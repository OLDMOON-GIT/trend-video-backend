# 🚀 Quick Start - AI Aggregator

백엔드에 통합된 AI Aggregator를 **3단계**로 시작하세요!

## ⚡ 3단계 시작하기

### 1️⃣ Playwright 설치 (최초 1회)
```bash
cd C:\Users\oldmoon\workspace\trend-video-backend
playwright install chromium
```

### 2️⃣ 실행해보기
```bash
# 방법 A: Python 스크립트
python run_ai_aggregator.py -q "파이썬이란?" -a claude

# 방법 B: PowerShell 스크립트 (Windows)
.\run_ai_aggregator.ps1 -q "파이썬이란?" -a claude
```

### 3️⃣ 결과 확인
- 브라우저가 자동으로 열리고 Claude에게 질문
- 응답이 완료되면 콘솔과 파일에 저장
- `ai_responses_YYYYMMDD_HHMMSS.txt` 파일 확인

---

## 📌 주요 명령어

### 단일 AI 사용
```bash
python run_ai_aggregator.py -q "질문 내용" -a claude
```

### 여러 AI 동시 사용
```bash
python run_ai_aggregator.py -q "질문 내용" -a claude,chatgpt,gemini
```

### 프롬프트 파일 사용
```bash
python run_ai_aggregator.py -f "prompts/my_prompt.txt" -a claude
```

### 인터랙티브 모드
```bash
python run_ai_aggregator.py -i
```

---

## 🎯 실전 예시

### 비디오 스크립트 생성
```bash
python run_ai_aggregator.py \
  -q "중년층을 위한 3분짜리 감동 스토리 스크립트를 JSON으로 작성해줘" \
  -a claude
```

### 여러 AI 비교
```bash
python run_ai_aggregator.py \
  -q "2024년 숏폼 비디오 트렌드는?" \
  -a claude,chatgpt,gemini
```

---

## 📁 파일 위치

```
trend-video-backend/
├── run_ai_aggregator.py        ← 실행 스크립트 (Python)
├── run_ai_aggregator.ps1       ← 실행 스크립트 (PowerShell)
├── example_usage.py            ← 코드 예시
├── AI_AGGREGATOR_GUIDE.md      ← 상세 가이드
└── src/
    └── ai_aggregator/          ← 소스 코드
        ├── main.py
        ├── agents/
        └── ...
```

---

## ⚙️ 주요 옵션

| 옵션 | 설명 |
|------|------|
| `-q "질문"` | 질문 내용 |
| `-a claude` | 사용할 AI (claude, chatgpt, gemini, grok) |
| `-f "파일"` | 프롬프트 파일 경로 |
| `-i` | 대화형 모드 |
| `--headless` | 백그라운드 실행 (브라우저 안보임) |

---

## 🆘 문제 해결

### Chrome 충돌 오류
```bash
# 프로필 사용 안함
python run_ai_aggregator.py -q "질문" -a claude --no-chrome-profile
```

### Playwright 오류
```bash
# 재설치
playwright install chromium
```

---

## 📚 더 알아보기

- **상세 가이드**: [AI_AGGREGATOR_GUIDE.md](AI_AGGREGATOR_GUIDE.md)
- **코드 예시**: [example_usage.py](example_usage.py)
- **전체 문서**: [README.md](README.md)

---

**시작했나요? 이제 [AI_AGGREGATOR_GUIDE.md](AI_AGGREGATOR_GUIDE.md)에서 고급 기능을 확인하세요!** 🚀
