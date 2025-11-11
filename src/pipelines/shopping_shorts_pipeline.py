"""
쇼핑 쇼츠 자동화 파이프라인
더우인 크롤링 → 다운로드 → AI 분석 → 쿠팡 연동 → TTS → 자막 → 업로드
"""
import asyncio
import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

# 프로젝트 모듈
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.douyin.crawler import DouyinCrawler, DouyinVideo
from src.douyin.downloader import DouyinDownloader
from src.douyin.product_analyzer import ProductAnalyzer, ProductInfo, ShortsScript
from src.coupang.client import CoupangClient, CoupangProduct


@dataclass
class PipelineConfig:
    """파이프라인 설정"""
    # 더우인
    douyin_video_limit: int = 5
    douyin_category: str = "electronics"

    # 출력 디렉토리
    output_dir: Path = Path("shopping_shorts_output")
    videos_dir: Path = Path("shopping_shorts_output/videos")
    scripts_dir: Path = Path("shopping_shorts_output/scripts")

    # 쿠팡
    frontend_url: str = "http://oldmoon.iptime.org:3000"
    session_cookie: Optional[str] = None

    # OpenAI
    openai_api_key: Optional[str] = None


@dataclass
class PipelineResult:
    """파이프라인 실행 결과"""
    success: bool
    video_id: str
    douyin_video: Optional[DouyinVideo] = None
    downloaded_video: Optional[Path] = None
    product_info: Optional[ProductInfo] = None
    coupang_product: Optional[CoupangProduct] = None
    shorts_script: Optional[ShortsScript] = None
    error: Optional[str] = None


class ShoppingShortsPipeline:
    """쇼핑 쇼츠 자동화 파이프라인"""

    def __init__(self, config: PipelineConfig):
        self.config = config

        # 출력 디렉토리 생성
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.videos_dir.mkdir(parents=True, exist_ok=True)
        self.config.scripts_dir.mkdir(parents=True, exist_ok=True)

        # 모듈 초기화
        self.douyin_crawler = DouyinCrawler(headless=True, filter_chinese=True)  # 중국어 필터링 활성화
        self.downloader = DouyinDownloader(output_dir=self.config.videos_dir)

        print("✅ 더우인 크롤러 초기화 (중국어 텍스트 필터링 활성화)", flush=True)

        # ProductAnalyzer는 optional (openai_api_key가 있을 때만)
        try:
            if self.config.openai_api_key:
                self.product_analyzer = ProductAnalyzer(api_key=self.config.openai_api_key)
            else:
                self.product_analyzer = None
                print("⚠️ AI 분석 비활성화 (OpenAI API 키 미설정)")
        except Exception as e:
            self.product_analyzer = None
            print(f"⚠️ ProductAnalyzer 초기화 실패: {e}")

        # 쿠팡 클라이언트는 optional (frontend_url이 있을 때만)
        try:
            if self.config.frontend_url:
                self.coupang_client = CoupangClient(
                    frontend_url=self.config.frontend_url,
                    session_cookie=self.config.session_cookie
                )
            else:
                self.coupang_client = None
                print("⚠️ 쿠팡 연동 비활성화 (frontend_url 미설정)")
        except Exception as e:
            self.coupang_client = None
            print(f"⚠️ 쿠팡 클라이언트 초기화 실패: {e}")

    async def run(self) -> List[PipelineResult]:
        """
        전체 파이프라인 실행

        Returns:
            PipelineResult 리스트
        """
        print("="*80, flush=True)
        print("🚀 쇼핑 쇼츠 자동화 파이프라인 시작", flush=True)
        print("="*80, flush=True)

        results: List[PipelineResult] = []

        try:
            # Step 1: 더우인 크롤링
            print("\n" + "="*80, flush=True)
            print("📱 Step 1: 더우인 트렌딩 영상 크롤링", flush=True)
            print("="*80, flush=True)

            videos = []
            crawl_success = False

            try:
                await self.douyin_crawler.start()
                videos = await self.douyin_crawler.get_trending_shopping_videos(
                    limit=self.config.douyin_video_limit,
                    category=self.config.douyin_category,
                    use_mock_data=False  # 실제 크롤링 시도
                )
                crawl_success = True
            except Exception as e:
                print(f"⚠️ 실제 더우인 크롤링 실패: {str(e)[:200]}", flush=True)
                print(f"🔄 테스트 모드로 전환 - 더미 데이터 사용", flush=True)

            # 크롤링 실패 또는 비어있으면 더미 데이터 사용
            if not crawl_success or not videos:
                videos = await self.douyin_crawler.get_trending_shopping_videos(
                    limit=self.config.douyin_video_limit,
                    category=self.config.douyin_category,
                    use_mock_data=True  # 더미 데이터 사용
                )

            if not videos:
                print("❌ 크롤링된 영상이 없습니다.", flush=True)
                return results

            print(f"✅ {len(videos)}개 영상 크롤링 완료\n", flush=True)

            # Step 2-7: 각 영상 처리
            for i, video in enumerate(videos, 1):
                print("\n" + "="*80, flush=True)
                print(f"🎬 영상 {i}/{len(videos)} 처리: {video.title[:50]}...", flush=True)
                print("="*80, flush=True)

                result = await self.process_single_video(video)
                results.append(result)

                # 결과 저장
                self.save_result(result)

            # 최종 요약
            self.print_summary(results)

            return results

        except Exception as e:
            print(f"\n❌ 파이프라인 오류: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return results

        finally:
            await self.douyin_crawler.close()

    async def process_single_video(self, video: DouyinVideo) -> PipelineResult:
        """
        단일 영상 처리

        Args:
            video: DouyinVideo

        Returns:
            PipelineResult
        """
        result = PipelineResult(
            success=False,
            video_id=video.video_id,
            douyin_video=video
        )

        try:
            # Step 2: 영상 다운로드
            print(f"\n📥 Step 2: 영상 다운로드", flush=True)

            # 더미 데이터는 다운로드 스킵
            if video.video_id.startswith('mock_'):
                print(f"⏭️ 테스트 모드 - 다운로드 스킵 (더미 데이터)", flush=True)
                result.downloaded_video = None
            else:
                download_result = self.downloader.download(
                    video_url=video.video_url,
                    video_id=video.video_id,
                    check_watermark=True
                )

                if not download_result.success:
                    result.error = f"다운로드 실패: {download_result.error}"
                    return result

                result.downloaded_video = download_result.video_path
                print(f"✅ 다운로드 완료: {result.downloaded_video}", flush=True)

            # Step 3: AI 제품 분석 (Optional)
            print(f"\n🤖 Step 3: AI 제품 정보 추출", flush=True)
            if self.product_analyzer:
                try:
                    product_info = self.product_analyzer.analyze_video_and_extract_product(
                        video_title=video.title,
                        video_description=None,
                        video_tags=None
                    )
                    result.product_info = product_info
                    print(f"✅ 제품명: {product_info.product_name_ko}", flush=True)
                    print(f"   카테고리: {product_info.category}", flush=True)
                except Exception as e:
                    print(f"⚠️ AI 분석 실패 (계속 진행): {e}", flush=True)
                    product_info = None
            else:
                print("⚠️ OpenAI 미설정 - AI 제품 분석 스킵", flush=True)
                product_info = None

            # Step 4: 쿠팡 제품 검색 & 링크 생성 (Optional)
            print(f"\n🛒 Step 4: 쿠팡 제품 검색 및 링크 생성", flush=True)
            try:
                if self.coupang_client and self.config.frontend_url and product_info:
                    coupang_product = self.coupang_client.find_best_matching_product(
                        product_name_ko=product_info.product_name_ko,
                        category=product_info.category
                    )

                    if not coupang_product:
                        print("⚠️ 쿠팡에서 일치하는 제품을 찾지 못함", flush=True)
                    else:
                        result.coupang_product = coupang_product
                        print(f"✅ 쿠팡 제품: {coupang_product.product_name[:50]}...", flush=True)
                        print(f"   가격: {coupang_product.product_price:,}원", flush=True)
                        if coupang_product.affiliate_link:
                            print(f"   Affiliate 링크: {coupang_product.affiliate_link[:60]}...", flush=True)
                else:
                    print("⚠️ 쿠팡 API 미설정 - 제품 검색 스킵", flush=True)
            except Exception as e:
                print(f"⚠️ 쿠팡 연동 실패 (계속 진행): {e}", flush=True)

            # Step 5: 쇼츠 대본 생성 (Optional)
            print(f"\n✍️ Step 5: 한국어 쇼츠 대본 생성", flush=True)
            if self.product_analyzer and product_info:
                try:
                    shorts_script = self.product_analyzer.generate_shorts_script(
                        product_info=product_info,
                        target_length=60
                    )
                    result.shorts_script = shorts_script
                    print(f"✅ 대본 생성 완료 (예상 길이: {shorts_script.estimated_duration}초)", flush=True)
                    print(f"\n[대본 미리보기]", flush=True)
                    print(f"훅: {shorts_script.hook}", flush=True)
                    print(f"메인: {shorts_script.main_content[:100]}...", flush=True)
                    print(f"CTA: {shorts_script.call_to_action}", flush=True)
                except Exception as e:
                    print(f"⚠️ 대본 생성 실패 (계속 진행): {e}", flush=True)
            else:
                print("⚠️ OpenAI 미설정 또는 제품 정보 없음 - 대본 생성 스킵", flush=True)

            # Step 6: TTS 생성 (TODO - 기존 edge-tts 연동)
            print(f"\n🔊 Step 6: TTS 음성 생성", flush=True)
            print("⏳ TTS 생성은 추후 구현...", flush=True)

            # Step 7: 자막 합성 (TODO - 기존 moviepy 연동)
            print(f"\n📝 Step 7: 자막 합성", flush=True)
            print("⏳ 자막 합성은 추후 구현...", flush=True)

            # Step 8: 업로드 (TODO - 기존 YouTube API 연동)
            print(f"\n⬆️ Step 8: 유튜브/SNS 업로드", flush=True)
            print("⏳ 업로드는 추후 구현...", flush=True)

            result.success = True
            return result

        except Exception as e:
            print(f"❌ 영상 처리 오류: {e}", flush=True)
            import traceback
            traceback.print_exc()
            result.error = str(e)
            return result

    def save_result(self, result: PipelineResult):
        """결과를 JSON으로 저장"""
        if not result.douyin_video:
            return

        output_file = self.config.scripts_dir / f"{result.video_id}.json"

        data = {
            "video_id": result.video_id,
            "success": result.success,
            "error": result.error,
            "douyin_video": asdict(result.douyin_video) if result.douyin_video else None,
            "downloaded_video": str(result.downloaded_video) if result.downloaded_video else None,
            "product_info": asdict(result.product_info) if result.product_info else None,
            "coupang_product": asdict(result.coupang_product) if result.coupang_product else None,
            "shorts_script": asdict(result.shorts_script) if result.shorts_script else None,
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n💾 결과 저장: {output_file}", flush=True)

    def print_summary(self, results: List[PipelineResult]):
        """최종 요약 출력"""
        print("\n" + "="*80)
        print("📊 파이프라인 실행 완료 - 최종 요약")
        print("="*80)

        total = len(results)
        success = len([r for r in results if r.success])
        failed = total - success

        print(f"\n총 처리: {total}개")
        print(f"성공: {success}개 ✅")
        print(f"실패: {failed}개 ❌")

        if failed > 0:
            print(f"\n실패한 영상:")
            for result in results:
                if not result.success:
                    print(f"  - {result.video_id}: {result.error}")

        print("\n" + "="*80)


async def main():
    """메인 실행 함수 - 커맨드라인 인자 파싱"""
    import argparse

    parser = argparse.ArgumentParser(description='쇼핑 쇼츠 자동화 파이프라인')
    parser.add_argument('--video-limit', type=int, default=5, help='크롤링할 영상 개수 (기본값: 5)')
    parser.add_argument('--category', type=str, default='electronics', help='카테고리 (기본값: electronics)')
    parser.add_argument('--frontend-url', type=str, default='http://localhost:3000', help='프론트엔드 URL')
    parser.add_argument('--openai-api-key', type=str, default='', help='OpenAI API 키')

    args = parser.parse_args()

    # OpenAI API 키는 환경변수 또는 인자에서 가져옴
    openai_key = args.openai_api_key or os.getenv("OPENAI_API_KEY")

    config = PipelineConfig(
        douyin_video_limit=args.video_limit,
        douyin_category=args.category,
        frontend_url=args.frontend_url,
        openai_api_key=openai_key if openai_key else None
    )

    print(f"📋 설정:")
    print(f"  - 영상 개수: {config.douyin_video_limit}")
    print(f"  - 카테고리: {config.douyin_category}")
    print(f"  - Frontend URL: {config.frontend_url}")
    print(f"  - OpenAI: {'설정됨' if config.openai_api_key else '미설정'}")
    print(f"", flush=True)  # 즉시 출력

    pipeline = ShoppingShortsPipeline(config)
    results = await pipeline.run()

    print(f"\n✅ 파이프라인 완료! {len(results)}개 영상 처리됨", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
