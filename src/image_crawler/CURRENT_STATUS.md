# Image Crawler - 현재 상태

## 실행 방법

```bash
cd trend-video-backend/src/image_crawler
python -u full_workflow.py ../../../test-scenes-sample.json
```

## 작동하는 기능 ✅

### 1. Image-FX (1단계)
- ✅ 페이지 자동 로드
- ✅ 입력창 자동 감지 (`.fZKmcZ`)
- ✅ 프롬프트 텍스트 입력
- ✅ Enter 키 전송 (ActionChains 사용)
- ✅ 이미지 생성 완료 감지 (DOM 기반, 최대 60초)
- ✅ 최근 이미지 파일 자동 감지 (Downloads 폴더)

### 2. Whisk (2-4단계)
- ✅ 페이지 자동 이동
- ✅ 프롬프트 자동 입력 (Ctrl+V 방식)
- ✅ 타이밍 제어 (scene_00: 즉시, scene_01: 0.5초, scene_02: 2초, scene_03+: 15초)
- ✅ 이미지 생성 대기 로직
- ✅ 이미지 HTTP 다운로드 구현
- ✅ JSON 파일 폴더에 images/ 저장

## 수동 개입 필요 ⚠️

### 1. Image-FX 이미지 다운로드
**현재 상태**:
- 자동 다운로드 버튼 클릭 시도 (실패 시 폴백)
- 최근 이미지 파일을 Downloads 폴더에서 찾음

**권장사항**:
1. 스크립트가 이미지 생성 대기 중일 때 Image-FX에서 이미지를 수동으로 다운로드
2. 또는 자동 감지를 신뢰하고 기다림

### 2. Whisk 인물 업로드
**현재 상태**:
- `input[type="file"]` 요소를 찾아서 자동 업로드 시도
- 찾지 못하면 수동 입력 요청

**문제**:
- Whisk 페이지 구조에 따라 file input이 숨겨져 있거나 다른 선택자 필요할 수 있음

**권장사항**:
- 스크립트 실행 중 Whisk 페이지의 인물 업로드 버튼을 수동으로 클릭
- 또는 페이지 구조를 분석하여 올바른 선택자 찾기

## 최근 테스트 로그

```
✅ Chrome 연결 완료
✅ Image-FX 페이지 로드 (1초)
✅ 입력창 발견 (1초)
✅ 입력 완료
✅ Enter 입력 완료
✅ 이미지 생성 대기 (50초 후 감지)
⚠️  최근 파일 감지: JSON 파일 잡힘 → 수정 완료 (이미지 파일만 필터링)
⚠️  Whisk 업로드: file input 찾지 못함 → 재시도 로직 추가 완료
```

## 다음 개선 사항

1. **Image-FX 다운로드 버튼 선택자 개선**
   - 현재 시도하는 선택자들이 실제 페이지와 맞지 않음
   - Whisk처럼 DOM 구조 분석 필요

2. **Whisk 인물 업로드 요소 찾기**
   - `input[type="file"]`이 숨겨져 있을 가능성
   - JavaScript로 클릭 트리거 필요할 수 있음

3. **에러 처리 강화**
   - 각 단계별 실패 시 복구 로직
   - 상세한 진행 상황 로깅

## 핵심 코드 변경사항

### Enter 키 전송 (수정됨)
```python
# 이전: JavaScript (setTimeout 비동기 문제)
driver.execute_script("""
    const elem = document.querySelector('.fZKmcZ');
    elem.dispatchEvent(new KeyboardEvent('keydown', ...));
""")

# 현재: ActionChains (안정적)
actions = ActionChains(driver)
actions.send_keys(Keys.RETURN).perform()
```

### 이미지 파일 감지 (수정됨)
```python
# 이전: 모든 파일
files = glob.glob(os.path.join(download_dir, '*'))

# 현재: 이미지 파일만
image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
files = []
for ext in image_extensions:
    files.extend(glob.glob(os.path.join(download_dir, f'*{ext}')))
```

### Whisk 업로드 재시도 (추가됨)
```python
for attempt in range(10):
    file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
    if file_inputs:
        file_inputs[0].send_keys(abs_path)
        upload_success = True
        break
    time.sleep(1)
```

## 결론

**자동화 수준**: ~80%

- Image-FX 입력 및 생성 요청: 100% 자동
- Image-FX 다운로드: 50% 자동 (파일 감지는 됨, 버튼 클릭은 안 됨)
- Whisk 업로드: 재시도 로직 있음, 수동 개입 필요할 수 있음
- Whisk 프롬프트 입력: 100% 자동
- Whisk 이미지 다운로드: 100% 자동 (구현 완료)

**사용자 개입 최소화 방법**:
1. Chrome을 디버깅 모드로 미리 실행: `chrome.exe --remote-debugging-port=9222`
2. Image-FX와 Whisk에 미리 로그인
3. 스크립트 실행 후 필요시 수동으로 다운로드/업로드 버튼 클릭
