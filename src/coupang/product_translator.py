"""
쿠팡 상품명 → 중국어 키워드 번역
GPT-4를 사용하여 한국 상품명을 중국 Douyin 검색에 최적화된 키워드로 변환
"""
import asyncio
from typing import List, Optional
from openai import OpenAI


class ProductTranslator:
    """상품명 번역기"""

    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def translate_to_chinese_keywords(
        self,
        product_name: str,
        category: Optional[str] = None
    ) -> List[str]:
        """
        한국어 상품명을 중국어 검색 키워드로 변환

        Args:
            product_name: 한국어 상품명
            category: 카테고리 (선택사항)

        Returns:
            중국어 키워드 리스트 (검색 우선순위순)
        """
        print(f"🔤 상품명 번역 중: {product_name}", flush=True)

        system_prompt = """당신은 한국 상품명을 중국 Douyin(抖音) 검색에 최적화된 중국어 키워드로 변환하는 전문가입니다.

목표:
- 한국 상품명을 보고 중국에서 동일하거나 유사한 제품을 찾을 수 있는 중국어 검색 키워드를 생성
- Douyin에서 실제로 많이 검색되는 키워드 우선
- 브랜드명보다는 제품 카테고리/기능 중심

예시:
- "삼성 갤럭시 버즈2 무선 이어폰" → ["无线蓝牙耳机", "TWS耳机", "降噪耳机"]
- "에어프라이어 6L 대용량" → ["空气炸锅", "无油炸锅", "家用炸锅"]
- "나이키 에어포스 운동화" → ["运动鞋", "板鞋", "休闲鞋"]

규칙:
1. 브랜드명은 중국에서 유명한 경우만 포함
2. 제품 카테고리를 가장 우선으로
3. 핵심 기능/특징 포함
4. 최대 3-5개 키워드
5. 간결하고 검색 가능한 단어

응답 형식: JSON
{"keywords": ["키워드1", "키워드2", "키워드3"]}
"""

        user_prompt = f"""상품명: {product_name}
카테고리: {category or '미지정'}

이 상품을 Douyin에서 찾기 위한 중국어 검색 키워드를 생성해주세요.
검색 성공률이 높은 순서로 3-5개 제시하세요."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            import json
            result = json.loads(response.choices[0].message.content)
            keywords = result.get("keywords", [])

            print(f"  ✅ 번역 완료: {' / '.join(keywords)}", flush=True)
            return keywords

        except Exception as e:
            print(f"  ❌ 번역 실패: {e}", flush=True)
            # 폴백: 간단한 규칙 기반 번역
            return self._fallback_translation(product_name)

    def _fallback_translation(self, product_name: str) -> List[str]:
        """GPT-4 실패 시 폴백 번역"""
        # 간단한 키워드 매칭
        keyword_map = {
            "이어폰": ["无线蓝牙耳机", "TWS耳机"],
            "무선이어폰": ["无线蓝牙耳机", "TWS耳机"],
            "에어프라이어": ["空气炸锅", "无油炸锅"],
            "후드티": ["卫衣", "连帽衫"],
            "운동화": ["运动鞋", "休闲鞋"],
            "마스크": ["面膜", "护肤面膜"],
            "스킨케어": ["护肤品", "面部护理"],
            "충전기": ["充电器", "快充"],
            "보조배터리": ["充电宝", "移动电源"],
            "키보드": ["机械键盘", "游戏键盘"],
            "마우스": ["鼠标", "游戏鼠标"],
        }

        for key, values in keyword_map.items():
            if key in product_name:
                return values

        # 기본값
        return ["热门商品", "推荐"]

    def batch_translate(
        self,
        product_names: List[str],
        categories: Optional[List[str]] = None
    ) -> List[List[str]]:
        """
        여러 상품명 일괄 번역

        Args:
            product_names: 상품명 리스트
            categories: 카테고리 리스트 (선택사항)

        Returns:
            각 상품의 중국어 키워드 리스트
        """
        results = []
        categories = categories or [None] * len(product_names)

        for name, category in zip(product_names, categories):
            keywords = self.translate_to_chinese_keywords(name, category)
            results.append(keywords)

        return results


async def main():
    """테스트 실행"""
    import os

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        return

    translator = ProductTranslator(api_key)

    # 테스트 상품들
    test_products = [
        "삼성 갤럭시 버즈2 프로 무선 이어폰",
        "샤오미 에어프라이어 6L 대용량",
        "나이키 에어포스1 화이트 운동화",
        "메디힐 티트리 진정 마스크팩 10매",
        "앤커 20000mAh 고속충전 보조배터리"
    ]

    print("=" * 80)
    print("🔤 상품명 → 중국어 키워드 번역 테스트")
    print("=" * 80)

    for product in test_products:
        keywords = translator.translate_to_chinese_keywords(product)
        print(f"\n📦 {product}")
        print(f"   🇨🇳 {' / '.join(keywords)}")

    print("\n✅ 번역 테스트 완료!")


if __name__ == "__main__":
    asyncio.run(main())
