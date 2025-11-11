"""
쿠팡 베스트셀러 → Douyin 영상 찾기 파이프라인
1. 쿠팡 베스트셀러 가져오기
2. 상품명을 중국어로 번역
3. Douyin에서 영상 검색
4. 영상 다운로드
5. 쿠팡 제휴 링크 생성
6. 한국어 TTS + 자막 생성 (TODO)
7. 멀티 플랫폼 업로드 (TODO)
"""
import asyncio
import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict
import json

# 프로젝트 모듈
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.coupang.bestseller_crawler import CoupangBestsellerCrawler, CoupangBestsellerProduct
from src.coupang.product_translator import ProductTranslator
from src.douyin.crawler import DouyinCrawler, DouyinVideo
from src.douyin.downloader import DouyinDownloader


@dataclass
class PipelineConfig:
    """파이프라인 설정"""
    # 쿠팡
    coupang_category: str = "electronics"
    product_limit: int = 5
    frontend_url: str = "http://oldmoon.iptime.org:3000"

    # Douyin
    videos_per_product: int = 3  # 각 상품당 가져올 영상 개수

    # OpenAI
    openai_api_key: Optional[str] = None

    # 출력
    output_dir: Path = Path("coupang_shorts_output")
    videos_dir: Path = Path("coupang_shorts_output/videos")
    data_dir: Path = Path("coupang_shorts_output/data")


@dataclass
class PipelineResult:
    """파이프라인 실행 결과"""
    success: bool
    product: Optional[CoupangBestsellerProduct] = None
    chinese_keywords: List[str] = None
    douyin_videos: List[DouyinVideo] = None
    downloaded_videos: List[Path] = None
    error: Optional[str] = None


class CoupangToDouyinPipeline:
    """쿠팡 → Douyin 파이프라인"""

    def __init__(self, config: PipelineConfig):
        self.config = config

        # 출력 디렉토리 생성
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.videos_dir.mkdir(parents=True, exist_ok=True)
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        # 모듈 초기화
        self.coupang_crawler = CoupangBestsellerCrawler("", "", "")  # API 키는 프론트엔드에서 가져옴

        self.translator = None
        if self.config.openai_api_key:
            self.translator = ProductTranslator(self.config.openai_api_key)
            print("✅ 번역기 초기화 완료", flush=True)
        else:
            print("⚠️ OpenAI 미설정 - 기본 번역 사용", flush=True)

        self.douyin_crawler = DouyinCrawler(headless=True, filter_chinese=False)  # 중국어 필터링 OFF (중국 영상이니까)
        self.downloader = DouyinDownloader(output_dir=self.config.videos_dir)

    async def run(self) -> List[PipelineResult]:
        """전체 파이프라인 실행"""
        print("=" * 80, flush=True)
        print("🚀 쿠팡 → Douyin 쇼츠 자동화 파이프라인 시작", flush=True)
        print("=" * 80, flush=True)

        results: List[PipelineResult] = []

        try:
            # Step 1: 쿠팡 베스트셀러 가져오기
            print("\n" + "=" * 80, flush=True)
            print("🛒 Step 1: 쿠팡 베스트셀러 가져오기", flush=True)
            print("=" * 80, flush=True)

            products = await self.coupang_crawler.get_bestsellers_by_frontend(
                frontend_url=self.config.frontend_url,
                category=self.config.coupang_category,
                limit=self.config.product_limit
            )

            if not products:
                print("❌ 쿠팡 상품을 찾지 못했습니다.", flush=True)
                return results

            print(f"✅ {len(products)}개 상품 수집 완료\n", flush=True)

            # Step 2-6: 각 상품 처리
            for i, product in enumerate(products, 1):
                print("\n" + "=" * 80, flush=True)
                print(f"🎁 상품 {i}/{len(products)}: {product.product_name[:50]}...", flush=True)
                print("=" * 80, flush=True)

                result = await self.process_single_product(product)
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

    async def process_single_product(self, product: CoupangBestsellerProduct) -> PipelineResult:
        """단일 상품 처리"""
        result = PipelineResult(
            success=False,
            product=product,
            chinese_keywords=[],
            douyin_videos=[],
            downloaded_videos=[]
        )

        try:
            # Step 2: 상품명 → 중국어 번역
            print(f"\n🔤 Step 2: 상품명 번역", flush=True)
            if self.translator:
                keywords = self.translator.translate_to_chinese_keywords(
                    product.product_name,
                    product.category_name
                )
            else:
                # 폴백: 간단한 번역
                keywords = self.translator._fallback_translation(product.product_name) if self.translator else ["商品"]

            result.chinese_keywords = keywords
            print(f"✅ 중국어 키워드: {' / '.join(keywords)}", flush=True)

            # Step 3: Douyin에서 영상 검색
            print(f"\n🔍 Step 3: Douyin 영상 검색", flush=True)

            videos = []
            for keyword in keywords[:2]:  # 상위 2개 키워드만 사용
                print(f"\n검색 키워드: {keyword}", flush=True)

                try:
                    await self.douyin_crawler.start()
                    keyword_videos = await self.douyin_crawler.search_videos_by_keyword(
                        keyword=keyword,
                        limit=self.config.videos_per_product,
                        use_mock_data=False
                    )
                    videos.extend(keyword_videos)

                    if videos:
                        break  # 영상을 찾았으면 다음 키워드는 스킵

                except Exception as e:
                    print(f"⚠️ Douyin 검색 실패 ({keyword}): {e}", flush=True)
                    continue

            # 검색 실패 시 더미 데이터
            if not videos and keywords:
                print(f"🔄 실제 검색 실패 - 테스트 모드로 전환", flush=True)
                videos = await self.douyin_crawler.search_videos_by_keyword(
                    keyword=keywords[0],
                    limit=self.config.videos_per_product,
                    use_mock_data=True
                )

            result.douyin_videos = videos
            print(f"✅ {len(videos)}개 영상 찾음", flush=True)

            # Step 4: 영상 다운로드
            print(f"\n📥 Step 4: 영상 다운로드", flush=True)

            for video in videos[:self.config.videos_per_product]:
                # 더미 데이터는 스킵
                if video.video_id.startswith('mock_'):
                    print(f"  ⏭️ 테스트 모드 - 다운로드 스킵", flush=True)
                    continue

                try:
                    download_result = self.downloader.download(
                        video_url=video.video_url,
                        video_id=video.video_id,
                        check_watermark=True
                    )

                    if download_result.success:
                        result.downloaded_videos.append(download_result.video_path)
                        print(f"  ✅ 다운로드 완료: {video.title[:30]}...", flush=True)
                    else:
                        print(f"  ❌ 다운로드 실패: {download_result.error}", flush=True)

                except Exception as e:
                    print(f"  ⚠️ 다운로드 오류: {e}", flush=True)
                    continue

            # Step 5: TTS + 자막 (TODO)
            print(f"\n🔊 Step 5: TTS 음성 및 자막 생성", flush=True)
            print("⏳ 추후 구현...", flush=True)

            # Step 6: 업로드 (TODO)
            print(f"\n⬆️ Step 6: 멀티 플랫폼 업로드", flush=True)
            print("⏳ 추후 구현...", flush=True)

            result.success = True
            return result

        except Exception as e:
            print(f"❌ 상품 처리 오류: {e}", flush=True)
            import traceback
            traceback.print_exc()
            result.error = str(e)
            return result

    def save_result(self, result: PipelineResult):
        """결과 저장"""
        if not result.product:
            return

        output_file = self.config.data_dir / f"{result.product.product_id}.json"

        data = {
            "success": result.success,
            "error": result.error,
            "product": asdict(result.product),
            "chinese_keywords": result.chinese_keywords,
            "douyin_videos": [asdict(v) for v in result.douyin_videos] if result.douyin_videos else [],
            "downloaded_videos": [str(p) for p in result.downloaded_videos] if result.downloaded_videos else [],
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n💾 결과 저장: {output_file}", flush=True)

    def print_summary(self, results: List[PipelineResult]):
        """최종 요약"""
        print("\n" + "=" * 80, flush=True)
        print("📊 파이프라인 실행 완료 - 최종 요약", flush=True)
        print("=" * 80, flush=True)

        total = len(results)
        success = len([r for r in results if r.success])
        total_videos = sum(len(r.douyin_videos) for r in results if r.douyin_videos)
        total_downloads = sum(len(r.downloaded_videos) for r in results if r.downloaded_videos)

        print(f"\n총 처리: {total}개 상품", flush=True)
        print(f"성공: {success}개 ✅", flush=True)
        print(f"실패: {total - success}개 ❌", flush=True)
        print(f"수집된 영상: {total_videos}개", flush=True)
        print(f"다운로드 완료: {total_downloads}개", flush=True)

        print("\n" + "=" * 80, flush=True)


async def main():
    """메인 실행 함수 - 환경변수에서 설정 읽기"""
    config = PipelineConfig(
        coupang_category=os.getenv("COUPANG_CATEGORY", "electronics"),
        product_limit=int(os.getenv("PRODUCT_LIMIT", "3")),
        videos_per_product=int(os.getenv("VIDEOS_PER_PRODUCT", "2")),
        frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000"),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

    print(f"📋 파이프라인 설정:", flush=True)
    print(f"  - 카테고리: {config.coupang_category}", flush=True)
    print(f"  - 상품 개수: {config.product_limit}", flush=True)
    print(f"  - 상품당 영상 개수: {config.videos_per_product}", flush=True)
    print(f"  - Frontend URL: {config.frontend_url}", flush=True)
    print(f"  - OpenAI: {'설정됨' if config.openai_api_key else '미설정'}", flush=True)
    print("", flush=True)

    pipeline = CoupangToDouyinPipeline(config)
    results = await pipeline.run()

    print(f"\n✅ 파이프라인 완료! {len(results)}개 상품 처리됨", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
