# Image-FX 입력 문제 빠른 해결 방법

## 문제
Image-FX에서 입력창(`.fZKmcZ`)을 찾지 못함

## 해결책

### 방법 1: 수동 첫 이미지 생성
1. Image-FX(https://labs.google/fx/tools/image-fx)에서 첫 씬 프롬프트 수동 입력
2. 이미지 생성 후 다운로드
3. 다운로드된 이미지 경로를 스크립트에 전달

```bash
python image_crawler.py ../../../test-scenes-sample.json --first-image "C:\Users\oldmoon\Downloads\image.jpg"
```

### 방법 2: Whisk만 사용
첫 씬도 Whisk에서 처리 (인물 없이)

```bash
python image_crawler.py ../../../test-scenes-sample.json --skip-imagefx
```

### 방법 3: Image-FX 코드 수정 (권장)
`image_crawler.py`의 `process_first_scene_with_imagefx` 함수에서:

1. 페이지 로드 후 충분히 대기 (15초 → 20초)
2. `.fZKmcZ` 요소가 나타날 때까지 명시적 대기
3. JavaScript로 직접 입력

```python
# 기존:
time.sleep(15)

# 수정:
time.sleep(20)
# .fZKmcZ 요소 기다리기
for i in range(30):
    has_elem = driver.execute_script("""
        return document.querySelector('.fZKmcZ') !== null;
    """)
    if has_elem:
        break
    time.sleep(1)
```

## 현재 워크플로우가 작동하는 부분
- ✅ Whisk 프롬프트 입력 (scene_00~03 모두 성공)
- ✅ Chrome 디버깅 포트 연결
- ✅ 클립보드 복사/붙여넣기

## 작동하지 않는 부분
- ❌ Image-FX 입력창 찾기
- ❌ Image-FX 이미지 다운로드
- ❌ Whisk 인물 업로드 (이미지가 없어서)
- ❌ Whisk 이미지 다운로드 (구현은 되었으나 테스트 안 됨)
