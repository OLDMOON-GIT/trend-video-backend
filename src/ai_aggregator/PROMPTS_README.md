# 프롬프트 파일 위치 안내

## 📍 프롬프트 파일 위치

**모든 프롬프트 파일은 프론트엔드에서 관리됩니다:**

```
trend-video-frontend/prompts/
├── prompt_longform.txt   # 롱폼 비디오 스크립트 생성 프롬프트
├── shortform_prompt.txt  # 숏폼 비디오 스크립트 생성 프롬프트
└── sora2_prompt.txt      # Sora2 영상 생성 프롬프트
```

## ⚠️ 중요: 백엔드 프롬프트 파일 삭제됨

이전에 `src/ai_aggregator/` 폴더에 있던 프롬프트 파일들은 **모두 삭제**되었습니다:
- ~~`prompt_longform.txt`~~ (삭제됨)
- ~~`prompt_shortform.txt`~~ (삭제됨)
- ~~`prompt_sora2.txt`~~ (삭제됨)

## 🔄 동작 방식

### 1. 프론트엔드에서 스크립트 생성 시
프론트엔드는 다음과 같이 작동합니다:
1. `trend-video-frontend/prompts/` 폴더에서 프롬프트를 읽음
2. 임시 파일 (`prompt_<timestamp>.txt`)을 백엔드 폴더에 생성
3. 백엔드를 `-f prompt_<timestamp>.txt` 옵션으로 실행
4. 백엔드는 임시 파일을 읽어서 AI에 전달

### 2. 백엔드를 직접 실행 시 (수동 실행)
백엔드는 `main.py`에서 자동으로 프론트엔드 prompts 폴더를 참조합니다:

```bash
# 상대 경로를 사용하면 자동으로 프론트엔드 prompts 폴더를 참조
python -m src.ai_aggregator.main -f prompt_longform.txt -q "제목"
```

`main.py`는 다음과 같이 동작합니다:
1. `-f` 옵션으로 받은 파일 경로가 상대 경로인지 확인
2. 상대 경로인 경우, 프론트엔드 prompts 폴더를 먼저 확인
3. 프론트엔드에 파일이 있으면 해당 파일을 사용
4. 없으면 상대 경로로 fallback

## 📝 프롬프트 수정 방법

### 프롬프트를 수정하려면:
1. `trend-video-frontend/prompts/` 폴더의 파일을 수정
2. **백엔드에서는 아무것도 할 필요 없음** (자동으로 참조됨)

### 예시: 롱폼 프롬프트 수정
```bash
# 프론트엔드 프롬프트 파일 수정
code trend-video-frontend/prompts/prompt_longform.txt

# 수정 완료 후 바로 사용 가능 (동기화 불필요)
npm run dev  # 프론트엔드에서
python -m src.ai_aggregator.main -f prompt_longform.txt -q "테스트"  # 백엔드에서
```

## 🚫 삭제된 기능

### prompt-sync-watcher.js (폐기됨)
이전에는 프론트엔드와 백엔드 간 프롬프트를 동기화하는 스크립트가 있었으나, 더 이상 필요하지 않습니다:
- `npm run watch-prompts` (삭제됨)
- 백엔드가 직접 프론트엔드를 참조하므로 동기화 불필요

## 🎯 Summary

| 항목 | 설명 |
|------|------|
| **프롬프트 위치** | `trend-video-frontend/prompts/*.txt` |
| **백엔드 참조 방식** | `main.py`에서 자동으로 프론트엔드 폴더 참조 |
| **동기화** | 필요 없음 (직접 참조) |
| **수정 방법** | 프론트엔드 prompts 폴더의 파일만 수정 |

## 📚 관련 코드

프론트엔드 프롬프트 참조 로직은 다음 파일에 구현되어 있습니다:
- `src/ai_aggregator/main.py` (Lines 314-355)
