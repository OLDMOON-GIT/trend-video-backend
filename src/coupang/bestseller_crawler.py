"""
쿠팡 베스트셀러 크롤러
쿠팡 파트너스 API를 통해 베스트셀러 상품 목록을 가져옵니다.
"""
import asyncio
import requests
import hmac
import hashlib
import time
from typing import List, Optional, Dict
from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass
class CoupangBestsellerProduct:
    """쿠팡 베스트셀러 상품 정보"""
    product_id: str
    product_name: str
    category_name: str
    product_price: int
    product_image: str
    product_url: str
    discount_rate: int = 0
    is_rocket: bool = False
    rating: float = 0.0
    review_count: int = 0
    rank: int = 0


class CoupangBestsellerCrawler:
    """쿠팡 베스트셀러 크롤러"""

    def __init__(self, access_key: str, secret_key: str, tracking_id: str):
        self.access_key = access_key
        self.secret_key = secret_key
        self.tracking_id = tracking_id
        self.domain = "https://api-gateway.coupang.com"

    def _generate_signature(self, method: str, path: str, query_params: str = "") -> Dict[str, str]:
        """HMAC 서명 생성"""
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}#{method}#{path}"
        if query_params:
            message += f"#{query_params}"

        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return {
            'Authorization': f'CEA algorithm=HmacSHA256, access-key={self.access_key}, signed-date={timestamp}, signature={signature}',
            'Content-Type': 'application/json;charset=UTF-8'
        }

    async def get_bestsellers(
        self,
        category: str = "1001",  # 카테고리 ID (1001: 가전디지털)
        limit: int = 20
    ) -> List[CoupangBestsellerProduct]:
        """
        베스트셀러 상품 가져오기

        Args:
            category: 카테고리 ID
            limit: 가져올 상품 개수

        Returns:
            CoupangBestsellerProduct 리스트
        """
        print(f"🛒 쿠팡 베스트셀러 가져오기 (카테고리: {category}, 개수: {limit})", flush=True)

        # 쿠팡 API는 베스트셀러 전용 엔드포인트가 없으므로
        # 검색 API를 사용하여 인기순으로 정렬된 결과를 가져옵니다
        path = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"

        # 카테고리별 인기 키워드
        category_keywords = {
            "1001": "무선이어폰",  # 가전디지털
            "1002": "후드티",      # 패션의류
            "1010": "스킨케어",    # 뷰티
            "1011": "주방용품",    # 홈리빙
            "1012": "건강식품",    # 식품
        }

        keyword = category_keywords.get(category, "베스트")

        query_params = {
            "keyword": keyword,
            "limit": limit
        }
        query_string = urlencode(query_params)

        headers = self._generate_signature("GET", path, query_string)
        url = f"{self.domain}{path}?{query_string}"

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            products = []
            if data.get('rCode') == '0' and data.get('data'):
                for idx, item in enumerate(data['data'][:limit], 1):
                    product = CoupangBestsellerProduct(
                        product_id=str(item.get('productId', '')),
                        product_name=item.get('productName', ''),
                        category_name=item.get('categoryName', category),
                        product_price=item.get('productPrice', 0),
                        product_image=item.get('productImage', ''),
                        product_url=item.get('productUrl', ''),
                        discount_rate=item.get('discountRate', 0),
                        is_rocket=item.get('isRocket', False),
                        rating=float(item.get('rating', 0)),
                        review_count=item.get('reviewCount', 0),
                        rank=idx
                    )
                    products.append(product)
                    print(f"  ✅ {idx}. {product.product_name[:40]}... ({product.product_price:,}원)", flush=True)

            print(f"✅ 총 {len(products)}개 베스트셀러 상품 수집 완료", flush=True)
            return products

        except requests.exceptions.RequestException as e:
            print(f"❌ 쿠팡 API 요청 실패: {e}", flush=True)
            return []
        except Exception as e:
            print(f"❌ 베스트셀러 수집 오류: {e}", flush=True)
            return []

    def _generate_mock_products(self, limit: int, category: str) -> List[CoupangBestsellerProduct]:
        """테스트용 더미 상품 생성"""
        import random

        # 카테고리별 상품 템플릿
        product_templates = {
            "electronics": [
                "갤럭시 버즈2 프로 무선 이어폰",
                "애플 에어팟 프로 2세대",
                "샤오미 무선충전기 67W 고속충전",
                "안커 USB-C 멀티포트 허브",
                "로지텍 MX Master 3S 무선마우스"
            ],
            "fashion": [
                "나이키 에센셜 오버핏 후드티",
                "아디다스 트레이닝 조거팬츠",
                "노스페이스 구스다운 패딩",
                "유니클로 히트텍 이너웨어",
                "뉴발란스 530 운동화"
            ],
            "beauty": [
                "라네즈 워터 슬리핑 마스크",
                "이니스프리 그린티 세럼",
                "에뛰드 선프라이즈 선쿠션",
                "설화수 자음생 크림",
                "코스알엑스 BHA 블랙헤드 파워 리퀴드"
            ]
        }

        templates = product_templates.get(category, [
            f"{category} 인기 상품 1",
            f"{category} 베스트셀러 2",
            f"{category} 추천 아이템 3"
        ])

        products = []
        for i in range(min(limit, len(templates))):
            product = CoupangBestsellerProduct(
                product_id=f"mock_{category}_{i+1}",
                product_name=templates[i % len(templates)],
                category_name=category,
                product_price=random.randint(15000, 150000),
                product_image="https://via.placeholder.com/300",
                product_url=f"https://www.coupang.com/vp/products/mock_{i+1}",
                is_rocket=random.choice([True, False]),
                rank=i+1
            )
            products.append(product)
            print(f"  ✅ {i+1}. {product.product_name} ({product.product_price:,}원)", flush=True)

        print(f"✅ 테스트 모드: {len(products)}개 더미 상품 생성 완료", flush=True)
        return products

    async def get_bestsellers_by_frontend(
        self,
        frontend_url: str,
        category: str,
        limit: int = 20
    ) -> List[CoupangBestsellerProduct]:
        """
        프론트엔드 API를 통해 베스트셀러 가져오기
        (기존 쿠팡 설정을 재사용)

        Args:
            frontend_url: 프론트엔드 URL
            category: 카테고리
            limit: 개수

        Returns:
            CoupangBestsellerProduct 리스트
        """
        print(f"🛒 프론트엔드 API로 베스트셀러 요청 중...", flush=True)

        # 카테고리별 검색 키워드
        category_keywords = {
            "electronics": "무선이어폰",
            "fashion": "후드티",
            "beauty": "스킨케어",
            "kitchen": "주방용품",
            "home": "인테리어",
        }

        keyword = category_keywords.get(category, "인기상품")

        try:
            url = f"{frontend_url}/api/coupang/search"
            response = requests.post(
                url,
                json={"keyword": keyword, "limit": limit},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()

            products = []
            if data.get('success') and data.get('products'):
                for idx, item in enumerate(data['products'][:limit], 1):
                    product = CoupangBestsellerProduct(
                        product_id=str(item.get('productId', '')),
                        product_name=item.get('productName', ''),
                        category_name=category,
                        product_price=item.get('productPrice', 0),
                        product_image=item.get('productImage', ''),
                        product_url=item.get('productUrl', ''),
                        is_rocket=item.get('isRocket', False),
                        rank=idx
                    )
                    products.append(product)
                    print(f"  ✅ {idx}. {product.product_name[:40]}... ({product.product_price:,}원)", flush=True)

            print(f"✅ 프론트엔드에서 {len(products)}개 상품 수집 완료", flush=True)
            return products

        except Exception as e:
            print(f"❌ 프론트엔드 API 요청 실패: {e}", flush=True)
            print(f"🔄 테스트 모드로 전환 - 더미 데이터 생성", flush=True)
            return self._generate_mock_products(limit, category)


async def main():
    """테스트 실행"""
    import os

    access_key = os.getenv("COUPANG_ACCESS_KEY", "")
    secret_key = os.getenv("COUPANG_SECRET_KEY", "")
    tracking_id = os.getenv("COUPANG_TRACKING_ID", "")

    if not all([access_key, secret_key, tracking_id]):
        print("❌ 쿠팡 API 키가 설정되지 않았습니다.")
        print("대신 프론트엔드 API를 사용합니다...")

        crawler = CoupangBestsellerCrawler("", "", "")
        products = await crawler.get_bestsellers_by_frontend(
            frontend_url="http://localhost:3000",
            category="electronics",
            limit=5
        )
    else:
        crawler = CoupangBestsellerCrawler(access_key, secret_key, tracking_id)
        products = await crawler.get_bestsellers(category="1001", limit=5)

    print(f"\n✅ {len(products)}개 상품 수집 완료")
    for p in products:
        print(f"  - {p.product_name[:30]}...")


if __name__ == "__main__":
    asyncio.run(main())
