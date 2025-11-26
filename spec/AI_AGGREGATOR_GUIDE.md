# AI Aggregator 사용 가이드 🤖

여러 AI (Claude, ChatGPT, Gemini, Grok)에 동시에 질문하고 답변을 수집하는 도구입니다.

## 📋 목차
1. [빠른 시작](#빠른-시작)
2. [설치 및 설정](#설치-및-설정)
3. [사용 방법](#사용-방법)
4. [고급 기능](#고급-기능)
5. [문제 해결](#문제-해결)

---

## 빠른 시작

### 1️⃣ Playwright 브라우저 설치 (최초 1회만)
```bash
playwright install chromium
```

### 2️⃣ AI에게 질문하기
```bash
# Claude에게만 질문
python run_ai_aggregator.py -q "파이썬 비동기 프로그래밍 설명해줘" -a claude

# 여러 AI에게 동시 질문
python run_ai_aggregator.py -q "효과적인 숏폼 비디오 전략은?" -a claude,chatgpt,gemini
```

### 3️⃣ 결과 확인
- 브라우저가 자동으로 열리고 AI 사이트에 접속합니다
- 질문이 자동으로 입력되고 전송됩니다
- 모든 AI의 응답이 완료되면 콘솔에 결과가 출력됩니다
- `ai_responses_YYYYMMDD_HHMMSS.txt` 파일로 자동 저장됩니다

---

## 설치 및 설정

### 필수 의존성
```bash
pip install playwright colorama
playwright install chromium
```

### 로그인 설정 (최초 1회)
AI 사이트에 로그인이 필요합니다. 처음 실행 시 수동으로 로그인하세요:

1. 스크립트 실행
2. 브라우저가 열리면 수동으로 각 AI 사이트에 로그인
3. 다음부터는 자동으로 로그인 유지됨 (쿠키 저장)

**지원하는 AI:**
- ✅ Claude (claude.ai)
- ✅ ChatGPT (chatgpt.com)
- ✅ Gemini (gemini.google.com)
- ✅ Grok (x.com/i/grok)

---

## 사용 방법

### 기본 사용법

#### 명령줄 인터페이스

```bash
# 기본 사용 (Claude만)
python run_ai_aggregator.py -q "질문 내용" -a claude

# PowerShell (Windows)
.\run_ai_aggregator.ps1 -q "질문 내용" -a claude
```

#### 옵션 설명

| 옵션 | 설명 | 예시 |
|------|------|------|
| `-q`, `--question` | 질문 내용 | `-q "파이썬이란?"` |
| `-a`, `--agents` | 사용할 AI (쉼표로 구분) | `-a claude,chatgpt` |
| `-f`, `--file` | 프롬프트 파일 경로 | `-f prompts/story.txt` |
| `-i`, `--interactive` | 대화형 모드 | `-i` |
| `--headless` | 백그라운드 실행 (브라우저 안보임) | `--headless` |
| `--no-chrome-profile` | 프로필 사용 안함 (로그인 필요) | `--no-chrome-profile` |

### 실전 예시

#### 1. 비디오 스크립트 작성 의뢰
```bash
python run_ai_aggregator.py \
  -q "중년층을 위한 3분짜리 감동적인 스토리 스크립트 작성해줘. 주제는 '가족의 소중함'" \
  -a claude
```

#### 2. 여러 AI에게 동시 질문
```bash
python run_ai_aggregator.py \
  -q "2024년 숏폼 비디오 트렌드는 무엇인가?" \
  -a claude,chatgpt,gemini
```

#### 3. 프롬프트 파일 사용
**prompts/story_request.txt:**
```
중년층을 위한 감동적인 스토리 3개를 작성해주세요.

요구사항:
- 각 스토리는 3-5분 분량
- 감동과 공감을 줄 수 있는 내용
- 한국 문화에 맞는 소재
- 각 스토리는 시작-전개-절정-결말 구조

JSON 형식으로 출력:
{
  "stories": [
    {
      "title": "제목",
      "duration": "3분",
      "scenes": [
        {"scene_number": 1, "text": "장면 내용"}
      ]
    }
  ]
}
```

**실행:**
```bash
python run_ai_aggregator.py -f prompts/story_request.txt -a claude
```

#### 4. 인터랙티브 모드
연속으로 여러 질문을 할 때 유용합니다:

```bash
python run_ai_aggregator.py -i
```

```
Your question: 효과적인 유튜브 숏츠 전략은?
[질문 전송 및 답변 수신...]

Your question: 방금 답변을 바탕으로 구체적인 예시 3가지 알려줘
[질문 전송 및 답변 수신...]

Your question: quit
Goodbye!
```

---

## 고급 기능

### Python 코드에서 사용

다른 Python 스크립트에서 AI Aggregator를 라이브러리처럼 사용할 수 있습니다:

```python
import asyncio
import sys
from pathlib import Path

# 백엔드 경로 추가
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir / "src"))

from ai_aggregator.main import main

async def generate_video_script():
    """AI에게 비디오 스크립트 생성 요청"""
    question = """
    중년층을 위한 3분짜리 감동적인 스토리 스크립트를 JSON 형식으로 작성해주세요.

    주제: 가족의 소중함
    """

    await main(
        question=question,
        agents_to_use=['claude'],
        headless=True,  # 백그라운드 실행
        use_real_chrome=True
    )

# 실행
asyncio.run(generate_video_script())
```

### 큐 시스템 사용 (서버 환경)

여러 요청이 동시에 들어올 때 순차 처리:

```python
from src.ai_aggregator.queue_manager import QueueManager
import uuid
import asyncio

def process_ai_request(question, agents):
    """큐를 사용한 AI 요청 처리"""
    task_id = str(uuid.uuid4())

    # 큐 잠금 획득 (다른 요청이 진행중이면 대기)
    with QueueManager() as qm:
        # 작업 추가
        qm.add_to_queue(task_id, {
            "question": question,
            "agents": agents
        })

        # 작업 처리
        qm.update_task_status(task_id, "processing")

        # AI 질의 실행
        asyncio.run(main(
            question=question,
            agents_to_use=agents,
            headless=True
        ))

        # 완료
        qm.update_task_status(task_id, "completed")
        qm.remove_from_queue(task_id)

    return task_id

# 사용
task_id = process_ai_request(
    "비디오 스크립트 작성해줘",
    ['claude']
)
print(f"Task {task_id} completed!")
```

### 응답 후처리

AI 응답을 받아서 추가 처리:

```python
from src.ai_aggregator.aggregator import ResponseAggregator

# 응답 수집
aggregator = ResponseAggregator()
# ... (AI 질의 후)

# 응답 가져오기
responses = aggregator.responses

# Claude 응답만 추출
claude_response = responses.get('Claude', '')

# JSON 파싱 (AI가 JSON을 반환한 경우)
import json
try:
    story_data = json.loads(claude_response)
    print(f"생성된 스토리 개수: {len(story_data['stories'])}")
except:
    print("JSON 파싱 실패")
```

---

## 문제 해결

### 1. Chrome 프로필 충돌 오류

**증상:**
```
TargetClosedError: Browser has been closed
```

**해결:**
```bash
# 옵션 1: 프로필 사용 안함
python run_ai_aggregator.py -q "질문" -a claude --no-chrome-profile

# 옵션 2: 프로필 삭제 후 재실행
rm -rf src/ai_aggregator/.chrome-automation-profile
python run_ai_aggregator.py -q "질문" -a claude

# 옵션 3: 컴퓨터 재부팅 후 다시 시도
```

### 2. 로그인이 안됨

**증상:**
AI 사이트에 접속했는데 로그인이 안되어 있음

**해결:**
1. `--no-chrome-profile` 없이 실행
2. 브라우저가 열리면 수동으로 로그인
3. 다음부터는 자동으로 로그인 유지됨

### 3. 응답을 받지 못함

**증상:**
질문은 전송되는데 응답을 받지 못함

**해결:**
1. AI 사이트가 응답 중인지 브라우저에서 확인
2. 네트워크 연결 확인
3. `--headless` 옵션 제거하고 브라우저 확인
4. 타임아웃 시간 늘리기 (코드 수정 필요)

### 4. Playwright 설치 오류

**증상:**
```
playwright._impl._errors.Error: Executable doesn't exist
```

**해결:**
```bash
# Chromium 재설치
playwright install chromium

# 또는 모든 브라우저 설치
playwright install
```

### 5. 한글 인코딩 오류

**증상:**
한글이 깨져서 출력됨

**해결:**
Windows에서는 자동으로 UTF-8 인코딩이 설정됩니다.
만약 문제가 계속되면 PowerShell에서:
```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

---

## 팁과 요령

### 💡 효과적인 프롬프트 작성

1. **구조화된 질문**
   ```
   질문: 비디오 스크립트 작성
   - 주제: [주제]
   - 길이: [시간]
   - 대상: [타겟 청중]
   - 형식: JSON
   ```

2. **예시 제공**
   ```
   다음과 같은 형식으로 응답해주세요:
   {
     "title": "제목",
     "scenes": [...]
   }
   ```

3. **단계별 요청**
   - 먼저 아이디어 3개 요청
   - 그 중 1개 선택해서 상세 스크립트 요청
   - 최종 검토 및 수정 요청

### 💡 성능 최적화

1. **필요한 AI만 사용**
   - 품질: Claude만 사용 (`-a claude`)
   - 비교: 여러 AI 사용 (`-a claude,chatgpt,gemini`)

2. **headless 모드 사용**
   - 프로덕션: `--headless` 사용
   - 디버깅: `--headless` 제거

3. **큐 시스템 활용**
   - 서버 환경에서는 QueueManager 사용
   - 동시 요청을 순차 처리로 안정성 확보

### 💡 자동화 워크플로우

```bash
# 1. AI에게 스토리 아이디어 요청
python run_ai_aggregator.py -f prompts/story_ideas.txt -a claude

# 2. 생성된 응답 확인
cat ai_responses_*.txt

# 3. 선택한 아이디어로 상세 스크립트 요청
python run_ai_aggregator.py -f prompts/detailed_script.txt -a claude

# 4. 비디오 생성
python create_video_from_folder.py --folder input/generated_story
```

---

## 📚 참고 자료

- [Playwright 문서](https://playwright.dev/python/)
- [trend-video-backend README](README.md)
- [예시 코드](example_usage.py)

---

## 🆘 지원

문제가 발생하면:
1. 이 가이드의 [문제 해결](#문제-해결) 섹션 확인
2. GitHub Issues에 문제 보고
3. 로그 파일 확인: `logs/ai_aggregator.log`

---

Made with ❤️ for automated content creation
