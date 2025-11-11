"""
쿠팡 파트너스 API 클라이언트
기존 Next.js API를 호출하여 제품 검색 및 affiliate 링크 생성
"""
import os
import requests
from typing import List, Dict, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CoupangProduct:
    """쿠팡 제품 정보"""
    product_id: str
    product_name: str
    product_price: int
    product_image: str
    product_url: str
    category_name: str
    is_rocket: bool
    affiliate_link: Optional[str] = None


class CoupangClient:
    """쿠팡 파트너스 클라이언트"""

    def __init__(
        self,
        frontend_url: Optional[str] = None,
        session_cookie: Optional[str] = None
    ):
        """
        Args:
            frontend_url: 프론트엔드 URL (기본값: 환경변수에서 가져옴)
            session_cookie: 인증 세션 쿠키
        """
        self.frontend_url = frontend_url or os.getenv("FRONTEND_URL", "http://localhost:3000")
        self.session_cookie = session_cookie

    def search_products(self, keyword: str) -> List[CoupangProduct]:
        """
        쿠팡에서 제품 검색

        Args:
            keyword: 검색 키워드

        Returns:
            CoupangProduct 리스트
        """
        print(f"🔍 쿠팡 제품 검색: {keyword}")

        url = f"{self.frontend_url}/api/coupang/search"
        headers = {
            "Content-Type": "application/json"
        }

        # 세션 쿠키가 있으면 추가
        if self.session_cookie:
            headers["Cookie"] = self.session_cookie

        try:
            response = requests.post(
                url,
                json={"keyword": keyword},
                headers=headers,
                timeout=30
            )

            if response.status_code == 401:
                print("❌ 인증 실패: 로그인이 필요합니다")
                return []

            if not response.ok:
                print(f"❌ 검색 실패: {response.status_code} - {response.text}")
                return []

            data = response.json()

            if not data.get("success"):
                print(f"❌ 검색 실패: {data.get('error', 'Unknown error')}")
                return []

            products = []
            for item in data.get("products", []):
                products.append(CoupangProduct(
                    product_id=item["productId"],
                    product_name=item["productName"],
                    product_price=item["productPrice"],
                    product_image=item["productImage"],
                    product_url=item["productUrl"],
                    category_name=item["categoryName"],
                    is_rocket=item["isRocket"]
                ))

            print(f"✅ {len(products)}개 제품 검색 완료")
            return products

        except Exception as e:
            print(f"❌ 검색 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

    def generate_affiliate_link(
        self,
        product: CoupangProduct
    ) -> Optional[str]:
        """
        affiliate 링크 생성

        Args:
            product: CoupangProduct 객체

        Returns:
            affiliate 링크 (실패 시 None)
        """
        print(f"🔗 Affiliate 링크 생성: {product.product_name[:50]}...")

        url = f"{self.frontend_url}/api/coupang/generate-link"
        headers = {
            "Content-Type": "application/json"
        }

        if self.session_cookie:
            headers["Cookie"] = self.session_cookie

        try:
            response = requests.post(
                url,
                json={
                    "productId": product.product_id,
                    "productName": product.product_name,
                    "productUrl": product.product_url
                },
                headers=headers,
                timeout=30
            )

            if not response.ok:
                print(f"❌ 링크 생성 실패: {response.status_code} - {response.text}")
                return None

            data = response.json()

            if not data.get("success"):
                print(f"❌ 링크 생성 실패: {data.get('error', 'Unknown error')}")
                return None

            affiliate_link = data.get("affiliateLink")
            print(f"✅ Affiliate 링크 생성 완료")

            # Product 객체에 링크 저장
            product.affiliate_link = affiliate_link

            return affiliate_link

        except Exception as e:
            print(f"❌ 링크 생성 오류: {e}")
            import traceback
            traceback.print_exc()
            return None

    def find_best_matching_product(
        self,
        product_name_ko: str,
        category: Optional[str] = None
    ) -> Optional[CoupangProduct]:
        """
        한국어 제품명으로 가장 일치하는 쿠팡 제품 찾기

        Args:
            product_name_ko: 한국어 제품명
            category: 카테고리 (선택적)

        Returns:
            가장 일치하는 CoupangProduct (없으면 None)
        """
        print(f"🎯 최적 제품 찾기: {product_name_ko}")

        # 1차 검색: 제품명 그대로
        products = self.search_products(product_name_ko)

        if not products:
            # 2차 검색: 제품명에서 키워드만 추출하여 재검색
            # 예: "스마트 청소 로봇" → "청소 로봇"
            keywords = product_name_ko.split()
            if len(keywords) > 1:
                simplified_keyword = ' '.join(keywords[-2:])
                print(f"   재검색: {simplified_keyword}")
                products = self.search_products(simplified_keyword)

        if not products:
            print("❌ 일치하는 제품을 찾을 수 없습니다")
            return None

        # 카테고리 필터링 (선택적)
        if category:
            filtered = [p for p in products if category in p.category_name]
            if filtered:
                products = filtered

        # 로켓배송 우선
        rocket_products = [p for p in products if p.is_rocket]
        if rocket_products:
            best_match = rocket_products[0]
        else:
            best_match = products[0]

        print(f"✅ 최적 제품 발견: {best_match.product_name[:50]}...")
        print(f"   가격: {best_match.product_price:,}원")
        print(f"   로켓배송: {'O' if best_match.is_rocket else 'X'}")

        # Affiliate 링크 생성
        self.generate_affiliate_link(best_match)

        return best_match


def main():
    """테스트 코드"""
    # 테스트용 클라이언트 생성
    client = CoupangClient(
        frontend_url="http://oldmoon.iptime.org:3000"
    )

    # 제품 검색
    keyword = "무선 청소기"
    products = client.search_products(keyword)

    if products:
        print(f"\n📦 검색 결과 ({len(products)}개):")
        for i, product in enumerate(products[:5], 1):
            print(f"\n{i}. {product.product_name}")
            print(f"   가격: {product.product_price:,}원")
            print(f"   로켓배송: {'O' if product.is_rocket else 'X'}")

        # 첫 번째 제품의 affiliate 링크 생성
        first_product = products[0]
        affiliate_link = client.generate_affiliate_link(first_product)

        if affiliate_link:
            print(f"\n🔗 Affiliate 링크:")
            print(affiliate_link)

    # 최적 제품 찾기 테스트
    print("\n" + "="*80)
    best_product = client.find_best_matching_product(
        product_name_ko="스마트 청소 로봇",
        category="가전"
    )

    if best_product and best_product.affiliate_link:
        print(f"\n🎯 최종 추천 제품:")
        print(f"   이름: {best_product.product_name}")
        print(f"   가격: {best_product.product_price:,}원")
        print(f"   링크: {best_product.affiliate_link}")


if __name__ == "__main__":
    main()
