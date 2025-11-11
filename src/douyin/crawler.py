"""
더우인(Douyin) 트렌딩 제품 영상 크롤러
Playwright를 사용하여 더우인 쇼핑 섹션의 인기 영상을 크롤링합니다.
"""
import asyncio
import json
import time
import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from playwright.async_api import async_playwright, Page, Browser


@dataclass
class DouyinVideo:
    """더우인 비디오 정보"""
    video_id: str
    video_url: str
    title: str
    author: str
    author_id: str
    view_count: int
    like_count: int
    share_count: int
    product_info: Optional[str] = None
    has_text_overlay: bool = False  # 중국어 자막 여부
    duration_seconds: int = 0


def has_chinese_text(text: str) -> bool:
    """
    텍스트에 중국어가 포함되어 있는지 확인

    Args:
        text: 확인할 텍스트

    Returns:
        중국어 포함 여부
    """
    # 중국어 유니코드 범위: U+4E00 ~ U+9FFF (CJK Unified Ideographs)
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    return bool(chinese_pattern.search(text))


class DouyinCrawler:
    """더우인 크롤러"""

    def __init__(self, headless: bool = False, filter_chinese: bool = True):
        self.headless = headless
        self.filter_chinese = filter_chinese  # 중국어 필터링 옵션
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def start(self):
        """브라우저 시작"""
        print("🚀 Playwright 브라우저 시작...", flush=True)
        self.playwright = await async_playwright().start()

        # 더우인은 중국 사이트이므로 중국어 locale 설정
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )

        context = await self.browser.new_context(
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            }
        )

        self.page = await context.new_page()

        # 자동화 감지 우회
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
        """)

        print("✅ 브라우저 시작 완료", flush=True)

    async def close(self):
        """브라우저 종료"""
        if self.browser:
            await self.browser.close()
            print("✅ 브라우저 종료")

    async def search_videos_by_keyword(
        self,
        keyword: str,
        limit: int = 20,
        use_mock_data: bool = False
    ) -> List[DouyinVideo]:
        """
        키워드로 영상 검색

        Args:
            keyword: 검색 키워드 (중국어)
            limit: 가져올 영상 개수
            use_mock_data: 테스트용 더미 데이터 사용

        Returns:
            DouyinVideo 리스트
        """
        # 더미 데이터 모드
        if use_mock_data:
            return await self._generate_mock_videos_for_keyword(limit, keyword)

        if not self.page:
            raise RuntimeError("브라우저가 시작되지 않았습니다. start()를 먼저 호출하세요.")

        videos: List[DouyinVideo] = []

        # Douyin 검색 URL
        from urllib.parse import quote
        search_url = f"https://www.douyin.com/search/{quote(keyword)}"

        print(f"🔍 Douyin 키워드 검색: {keyword}", flush=True)
        print(f"   URL: {search_url}", flush=True)

        # 재시도 로직
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🔄 접속 시도 {attempt + 1}/{max_retries}...", flush=True)
                await self.page.goto(search_url, wait_until='load', timeout=60000)
                await asyncio.sleep(5)
                print(f"✅ 검색 페이지 접속 성공!", flush=True)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ 접속 실패 ({attempt + 1}/{max_retries}): {e}", flush=True)
                    await asyncio.sleep(3)
                else:
                    raise Exception(f"Douyin 검색 페이지 접속 실패: {e}")

        try:
            # 영상 탭 클릭 (검색 결과에서 영상만 필터링)
            try:
                video_tab = await self.page.query_selector('div[data-e2e="search-video-tab"]')
                if video_tab:
                    await video_tab.click()
                    await asyncio.sleep(2)
            except:
                pass  # 영상 탭이 없으면 그냥 진행

            # 스크롤하면서 영상 수집
            scroll_count = 0
            max_scrolls = limit // 5 + 2

            while len(videos) < limit and scroll_count < max_scrolls:
                # 영상 요소 찾기
                video_elements = await self.page.query_selector_all('[data-e2e="search-result-video"]')

                print(f"🔍 발견된 영상 수: {len(video_elements)}", flush=True)

                for element in video_elements:
                    if len(videos) >= limit:
                        break

                    try:
                        # 영상 정보 추출
                        video_id = await element.get_attribute('data-video-id')
                        if not video_id:
                            continue

                        # 중복 체크
                        if any(v.video_id == video_id for v in videos):
                            continue

                        # 링크
                        link_element = await element.query_selector('a')
                        video_url = await link_element.get_attribute('href') if link_element else None

                        if not video_url:
                            continue

                        if video_url.startswith('/'):
                            video_url = f"https://www.douyin.com{video_url}"

                        # 제목
                        title_element = await element.query_selector('[data-e2e="search-video-desc"]')
                        title = await title_element.inner_text() if title_element else "제목 없음"

                        # 중국어 필터링
                        if self.filter_chinese and has_chinese_text(title):
                            print(f"  ⏭️ 중국어 텍스트 감지 - 스킵: {title[:30]}...", flush=True)
                            continue

                        # 작성자
                        author_element = await element.query_selector('[data-e2e="search-video-author"]')
                        author = await author_element.inner_text() if author_element else "작성자 없음"

                        # 통계
                        view_count = await self._extract_count(element, '[data-e2e="search-video-views"]')
                        like_count = await self._extract_count(element, '[data-e2e="search-video-likes"]')

                        video = DouyinVideo(
                            video_id=video_id,
                            video_url=video_url,
                            title=title,
                            author=author,
                            author_id="",
                            view_count=view_count,
                            like_count=like_count,
                            share_count=0,
                            has_text_overlay=False,
                        )

                        videos.append(video)
                        print(f"  ✅ 영상 추가: {title[:40]}... (조회: {view_count:,})", flush=True)

                    except Exception as e:
                        print(f"  ⚠️ 영상 정보 추출 실패: {e}", flush=True)
                        continue

                # 스크롤
                await self.page.evaluate('window.scrollBy(0, window.innerHeight)')
                await asyncio.sleep(2)
                scroll_count += 1

            print(f"\n✅ 총 {len(videos)}개 영상 수집 완료 (키워드: {keyword})", flush=True)
            return videos

        except Exception as e:
            print(f"❌ 검색 오류: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return videos

    async def get_trending_shopping_videos(
        self,
        limit: int = 20,
        category: str = "electronics",  # electronics, fashion, beauty, home 등
        use_mock_data: bool = False  # 테스트용 더미 데이터 사용
    ) -> List[DouyinVideo]:
        """
        트렌딩 쇼핑 영상 가져오기

        Args:
            limit: 가져올 영상 개수
            category: 카테고리 (electronics, fashion, beauty, home 등)
            use_mock_data: 테스트용 더미 데이터 사용 여부

        Returns:
            DouyinVideo 리스트
        """
        # 더미 데이터 모드
        if use_mock_data:
            return await self._generate_mock_videos(limit, category)

        if not self.page:
            raise RuntimeError("브라우저가 시작되지 않았습니다. start()를 먼저 호출하세요.")

        videos: List[DouyinVideo] = []

        # 더우인 쇼핑 페이지 URL
        # 실제로는 더우인의 쇼핑 섹션 URL을 사용해야 합니다
        # 예: https://www.douyin.com/discover
        url = "https://www.douyin.com/discover"

        print(f"📱 더우인 트렌딩 페이지 접속 시도: {url}", flush=True)

        # 재시도 로직
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"🔄 접속 시도 {attempt + 1}/{max_retries}...", flush=True)
                await self.page.goto(url, wait_until='load', timeout=60000)  # networkidle → load, 60초로 증가
                await asyncio.sleep(5)
                print(f"✅ 페이지 접속 성공!", flush=True)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ 접속 실패 ({attempt + 1}/{max_retries}): {e}", flush=True)
                    await asyncio.sleep(3)
                else:
                    raise Exception(f"더우인 페이지 접속 실패 (최대 재시도 횟수 초과): {e}")

        try:
            pass  # 아래 기존 로직 계속

            # 페이지 스크롤하면서 영상 수집
            scroll_count = 0
            max_scrolls = limit // 10 + 1

            while len(videos) < limit and scroll_count < max_scrolls:
                # 영상 요소 찾기 (실제 더우인 DOM 구조에 맞게 수정 필요)
                video_elements = await self.page.query_selector_all('[data-e2e="recommend-list-item"]')

                print(f"🔍 발견된 영상 수: {len(video_elements)}")

                for element in video_elements:
                    if len(videos) >= limit:
                        break

                    try:
                        # 영상 정보 추출 (실제 DOM 구조에 맞게 수정 필요)
                        video_id = await element.get_attribute('data-video-id')
                        if not video_id:
                            continue

                        # 중복 체크
                        if any(v.video_id == video_id for v in videos):
                            continue

                        # 영상 링크
                        link_element = await element.query_selector('a')
                        video_url = await link_element.get_attribute('href') if link_element else None

                        if not video_url:
                            continue

                        # 전체 URL로 변환
                        if video_url.startswith('/'):
                            video_url = f"https://www.douyin.com{video_url}"

                        # 제목
                        title_element = await element.query_selector('[data-e2e="video-title"]')
                        title = await title_element.inner_text() if title_element else "제목 없음"

                        # 중국어 필터링 체크
                        if self.filter_chinese and has_chinese_text(title):
                            print(f"  ⏭️ 중국어 텍스트 감지 - 스킵: {title[:30]}...", flush=True)
                            continue

                        # 작성자
                        author_element = await element.query_selector('[data-e2e="video-author"]')
                        author = await author_element.inner_text() if author_element else "작성자 없음"

                        # 설명에서도 중국어 체크
                        desc_element = await element.query_selector('[data-e2e="video-desc"]')
                        description = await desc_element.inner_text() if desc_element else ""

                        if self.filter_chinese and description and has_chinese_text(description):
                            print(f"  ⏭️ 설명에 중국어 감지 - 스킵: {title[:30]}...", flush=True)
                            continue

                        # 통계 정보
                        view_count = await self._extract_count(element, '[data-e2e="video-views"]')
                        like_count = await self._extract_count(element, '[data-e2e="video-likes"]')
                        share_count = await self._extract_count(element, '[data-e2e="video-shares"]')

                        video = DouyinVideo(
                            video_id=video_id,
                            video_url=video_url,
                            title=title,
                            author=author,
                            author_id="",  # 필요시 추출
                            view_count=view_count,
                            like_count=like_count,
                            share_count=share_count,
                            has_text_overlay=False,  # 일단 False, 다운로드 후 검증
                        )

                        videos.append(video)
                        print(f"  ✅ 영상 추가 (중국어 없음): {title[:50]}... (조회: {view_count:,})", flush=True)

                    except Exception as e:
                        print(f"  ⚠️ 영상 정보 추출 실패: {e}")
                        continue

                # 페이지 스크롤
                await self.page.evaluate('window.scrollBy(0, window.innerHeight)')
                await asyncio.sleep(2)
                scroll_count += 1

            print(f"\n✅ 총 {len(videos)}개 영상 수집 완료")
            return videos

        except Exception as e:
            print(f"❌ 크롤링 오류: {e}")
            import traceback
            traceback.print_exc()
            return videos

    async def _generate_mock_videos(self, limit: int, category: str) -> List[DouyinVideo]:
        """
        테스트용 더미 영상 데이터 생성 (중국어 없는 영문 제목)

        Args:
            limit: 생성할 영상 개수
            category: 카테고리

        Returns:
            DouyinVideo 리스트
        """
        import random

        print(f"🧪 테스트 모드: {limit}개 더미 데이터 생성 중...", flush=True)
        await asyncio.sleep(0.5)  # 비동기 작업 시뮬레이션

        mock_titles = {
            "electronics": [
                "Amazing Wireless Earbuds Review",
                "Smart Watch Unboxing 2024",
                "Gaming Keyboard Test",
                "Portable Charger Comparison",
                "4K Webcam Setup Guide",
            ],
            "fashion": [
                "Summer Fashion Trends",
                "Sneaker Collection Showcase",
                "Minimal Wardrobe Essentials",
                "Designer Bag Review",
                "Outfit Ideas for Spring",
            ],
            "beauty": [
                "Skincare Routine Morning",
                "Makeup Tutorial Natural Look",
                "Hair Care Tips 2024",
                "Best Lip Gloss Swatches",
                "Anti-Aging Serum Review",
            ],
        }

        titles = mock_titles.get(category, mock_titles["electronics"])
        videos = []

        for i in range(limit):
            title = random.choice(titles) + f" #{i+1}"
            video_id = f"mock_{category}_{int(time.time())}_{i}"

            video = DouyinVideo(
                video_id=video_id,
                video_url=f"https://www.douyin.com/video/{video_id}",
                title=title,
                author=f"TestUser{random.randint(1, 100)}",
                author_id=f"user_{random.randint(1000, 9999)}",
                view_count=random.randint(10000, 1000000),
                like_count=random.randint(1000, 100000),
                share_count=random.randint(100, 10000),
                has_text_overlay=False,
                duration_seconds=random.randint(15, 60),
            )

            videos.append(video)
            print(f"  ✅ 더미 영상 생성: {title} (조회: {video.view_count:,})", flush=True)

        print(f"✅ {len(videos)}개 더미 영상 생성 완료", flush=True)
        return videos

    async def _generate_mock_videos_for_keyword(self, limit: int, keyword: str) -> List[DouyinVideo]:
        """키워드 기반 더미 영상 생성"""
        import random

        print(f"🧪 테스트 모드: {keyword} 키워드로 {limit}개 더미 데이터 생성 중...", flush=True)
        await asyncio.sleep(0.5)

        videos = []
        for i in range(limit):
            title = f"{keyword} Product Review #{i+1}"
            video_id = f"mock_{keyword}_{int(time.time())}_{i}"

            video = DouyinVideo(
                video_id=video_id,
                video_url=f"https://www.douyin.com/video/{video_id}",
                title=title,
                author=f"TestUser{random.randint(1, 100)}",
                author_id=f"user_{random.randint(1000, 9999)}",
                view_count=random.randint(10000, 1000000),
                like_count=random.randint(1000, 100000),
                share_count=random.randint(100, 10000),
                has_text_overlay=False,
                duration_seconds=random.randint(15, 60),
            )

            videos.append(video)
            print(f"  ✅ 더미 영상 생성: {title} (조회: {video.view_count:,})", flush=True)

        print(f"✅ {len(videos)}개 더미 영상 생성 완료 (키워드: {keyword})", flush=True)
        return videos

    async def _extract_count(self, element, selector: str) -> int:
        """숫자 카운트 추출"""
        try:
            count_element = await element.query_selector(selector)
            if count_element:
                text = await count_element.inner_text()
                # "1.2w" 같은 형식을 숫자로 변환
                text = text.lower().replace('w', '0000').replace('k', '000')
                # 숫자만 추출
                numbers = re.findall(r'\d+', text)
                if numbers:
                    return int(numbers[0])
        except:
            pass
        return 0

    async def check_text_overlay(self, video_url: str) -> bool:
        """
        영상에 텍스트 오버레이(자막)가 있는지 확인

        Args:
            video_url: 영상 URL

        Returns:
            True if 텍스트 오버레이가 있음, False otherwise
        """
        # TODO: OCR 또는 영상 분석을 통해 중국어 자막 감지
        # 지금은 간단히 False 반환
        return False

    def save_videos_to_json(self, videos: List[DouyinVideo], output_path: Path):
        """영상 정보를 JSON 파일로 저장"""
        data = [asdict(video) for video in videos]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"💾 영상 정보 저장: {output_path}")


async def main():
    """테스트 코드"""
    crawler = DouyinCrawler(headless=False)

    try:
        await crawler.start()

        # 트렌딩 영상 가져오기
        videos = await crawler.get_trending_shopping_videos(limit=10)

        # JSON으로 저장
        output_path = Path("douyin_videos.json")
        crawler.save_videos_to_json(videos, output_path)

        print(f"\n📊 수집 결과:")
        for i, video in enumerate(videos, 1):
            print(f"{i}. {video.title}")
            print(f"   조회: {video.view_count:,}, 좋아요: {video.like_count:,}")
            print(f"   URL: {video.video_url}")
            print()

    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
