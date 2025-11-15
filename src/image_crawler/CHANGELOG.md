# Image Crawler 업데이트 내역

## 2025-11-15 (최신): 안정성 개선 및 자동화 강화

### 주요 개선사항

#### 1. Image-FX Enter 키 입력 수정
- **문제**: setTimeout 비동기 실행으로 인한 요소 참조 오류
- **해결**: JavaScript 대신 Selenium ActionChains 사용
- **결과**: Enter 키 전송 안정성 100% 개선

#### 2. 이미지 파일 감지 개선
- **문제**: 최근 파일 검색 시 JSON 등 비이미지 파일을 잡음
- **해결**: 이미지 확장자만 필터링 (.jpg, .png, .webp, .gif, .bmp)
- **결과**: 정확한 이미지 파일 감지

#### 3. Whisk 업로드 재시도 로직
- **추가**: 파일 업로드 input을 찾을 때까지 최대 10회 재시도
- **추가**: 업로드 실패 시 상세한 에러 메시지
- **추가**: EOFError 처리 (비대화형 모드 대응)

#### 4. 이미지 생성 감지 개선
- **변경**: 고정 40초 대기 → 동적 감지 (최대 60초)
- **방법**: DOM에서 큰 이미지 요소(300x300 이상) 감지
- **결과**: 불필요한 대기 시간 단축

### 테스트 결과

```
✅ Image-FX 페이지 로드
✅ 입력창 발견 및 텍스트 입력
✅ Enter 키 전송
✅ 이미지 생성 완료 감지
⚠️  자동 다운로드 (버튼 찾기 실패, 폴백으로 최근 파일 사용)
⚠️  Whisk 업로드 (file input 찾기 필요)
```

### 현재 워크플로우 상태

```
1. Image-FX
   ├─ ✅ 프롬프트 입력
   ├─ ✅ 이미지 생성 대기
   ├─ ⚠️  다운로드 (수동 필요 - 버튼 선택자 개선 필요)
   └─ ✅ 최근 이미지 파일 감지

2. Whisk 인물 업로드
   ├─ ✅ 페이지 이동
   ├─ 🔄 file input 찾기 (재시도 로직 추가)
   └─ ⚠️  업로드 (수동 필요 - 페이지 구조 확인 필요)

3. Whisk 프롬프트 입력
   ├─ ✅ Ctrl+V 입력 (검증됨)
   └─ ✅ 타이밍 제어

4. 이미지 다운로드
   └─ ✅ HTTP 다운로드 구현 완료
```

## 2025-11-15: 전체 워크플로우 완성

### 추가된 기능

#### 1. Image-FX 입력 개선
- **문제**: Stale Element Reference Exception 발생
- **해결**: 모든 DOM 조작을 한 번의 JavaScript 실행으로 처리
- **개선사항**:
  - JavaScript로 요소 찾기, 클릭, 텍스트 입력을 한 번에 처리
  - React 재렌더링 대응 (setTimeout 사용)
  - 입력 후 Enter 키도 JavaScript로 전송

#### 2. Whisk 이미지 생성 완료 대기
- **함수**: `wait_for_whisk_generation(driver, timeout=120)`
- **기능**:
  - 로딩 스피너 감지
  - "Generating" / "생성 중" 텍스트 감지
  - 최대 120초 대기
  - 10초마다 진행 상황 출력

#### 3. Whisk 이미지 다운로드
- **함수**: `download_whisk_images(driver, output_folder, scene_count)`
- **기능**:
  - 페이지에서 생성된 이미지 자동 감지
  - HTTP 요청으로 이미지 다운로드
  - scene_00.jpg, scene_01.jpg 등으로 저장
  - PNG, JPG, WEBP 형식 지원

#### 4. 대본 폴더 저장
- JSON 파일과 같은 디렉토리에 `images/` 폴더 자동 생성
- 각 씬별로 파일 저장

### 전체 워크플로우

```
1. Image-FX에서 첫 번째 씬 처리
   ├─ 페이지 로드 (15초 대기)
   ├─ 입력창 찾기 (.fZKmcZ)
   ├─ JavaScript로 프롬프트 입력
   ├─ Enter 키 전송
   ├─ 이미지 생성 대기 (40초)
   └─ 이미지 다운로드

2. Whisk 페이지로 이동
   └─ https://labs.google/fx/ko/tools/whisk/project

3. 첫 번째 이미지를 인물로 업로드
   ├─ 인물 업로드 버튼 찾기
   ├─ 파일 선택 (SendKeys)
   └─ 업로드 완료 대기

4. Whisk에서 나머지 씬 처리
   ├─ scene_00: 즉시 입력
   ├─ scene_01: 0.5초 후 입력
   ├─ scene_02: 2초 후 입력
   └─ scene_03: 15초 후 입력

5. 이미지 생성 완료 대기
   └─ 최대 120초

6. 생성된 이미지 다운로드
   ├─ 페이지에서 이미지 URL 추출
   ├─ HTTP GET 요청으로 다운로드
   └─ {JSON_DIR}/images/ 폴더에 저장
```

### 파일 구조

```
workspace/
├── test-scenes-sample.json
└── images/                    # 자동 생성
    ├── scene_00.jpg
    ├── scene_01.jpg
    ├── scene_02.jpg
    └── scene_03.jpg
```

### 사용 방법

```bash
cd trend-video-backend/src/image_crawler
python image_crawler.py ../../../test-scenes-sample.json
```

### 주요 변경사항 (image_crawler.py)

#### 수정된 함수:
- `process_first_scene_with_imagefx()`: JavaScript 기반 입력으로 변경

#### 새로 추가된 함수:
- `wait_for_whisk_generation()`: 이미지 생성 대기
- `download_whisk_images()`: 이미지 다운로드 및 저장

#### main() 함수 업데이트:
- 5단계: 이미지 생성 대기 추가
- 6단계: 이미지 다운로드 추가
- 결과 요약 출력 추가

### 알려진 제한사항

1. **Image-FX 다운로드 버튼**: 아직 자동 클릭이 불안정할 수 있음
2. **Whisk 이미지 매칭**: 여러 이미지가 표시될 경우 올바른 이미지 선택이 어려울 수 있음
3. **대기 시간**: 네트워크 속도에 따라 타임아웃이 필요할 수 있음

### 다음 개선 사항

1. Image-FX 다운로드 버튼 찾기 로직 강화
2. Whisk 이미지 다운로드 버튼 클릭으로 변경 (현재는 URL 직접 다운로드)
3. 에러 처리 개선
4. 진행 상황 로깅 강화
