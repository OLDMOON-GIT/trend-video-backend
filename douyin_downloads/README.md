# Douyin 영상 다운로드

## 쿠키 설정 방법

Douyin 영상을 다운로드하려면 Douyin 쿠키가 필요합니다.

### 1. Chrome 확장 프로그램 설치

[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) 설치

### 2. Douyin 로그인

1. https://www.douyin.com 접속
2. 계정 로그인

### 3. 쿠키 추출

1. Douyin 사이트에서 확장 프로그램 아이콘 클릭
2. "Export" 클릭하여 `cookies.txt` 다운로드
3. 다운로드한 `cookies.txt`를 이 폴더(`douyin_downloads/`)에 저장

### 4. 다운로드 테스트

```python
from pathlib import Path
from src.douyin.downloader import DouyinDownloader

downloader = DouyinDownloader(
    output_dir=Path("douyin_downloads"),
    cookies_file=Path("douyin_downloads/cookies.txt")  # 쿠키 파일 지정
)

result = downloader.download(
    video_url="https://www.douyin.com/video/7561626692482026811",
    video_id="test_video"
)

if result.success:
    print(f"✅ 다운로드 성공: {result.video_path}")
else:
    print(f"❌ 다운로드 실패: {result.error}")
```

## 참고사항

- 쿠키는 주기적으로 만료되므로 다운로드가 실패하면 쿠키를 다시 추출해야 합니다
- Douyin 로그인 상태를 유지해야 합니다
- 일부 비공개 영상은 다운로드가 불가능할 수 있습니다
