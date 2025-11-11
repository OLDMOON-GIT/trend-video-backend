"""
더우인 영상 제품 분석기
AI를 활용하여 영상에서 제품 정보를 추출하고 한국어 쇼츠 대본을 생성합니다.
"""
import os
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

import openai
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProductInfo:
    """제품 정보"""
    product_name_ko: str  # 한국어 제품명
    product_name_cn: str  # 중국어 원제품명
    category: str  # 카테고리 (예: 전자제품, 패션, 뷰티 등)
    key_features: List[str]  # 주요 특징
    price_range: Optional[str] = None  # 가격대
    target_audience: str = "일반"  # 타겟층


@dataclass
class ShortsScript:
    """쇼츠 대본"""
    hook: str  # 첫 3초 훅 (시선 잡기)
    main_content: str  # 메인 내용 (제품 소개, 특징 설명)
    call_to_action: str  # 행동 유도 (쿠팡 링크 클릭 유도)
    estimated_duration: int  # 예상 길이 (초)


class ProductAnalyzer:
    """제품 분석 및 대본 생성기"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: OpenAI API 키 (None이면 환경변수에서 가져옴)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다")

        openai.api_key = self.api_key

    def analyze_video_and_extract_product(
        self,
        video_title: str,
        video_description: Optional[str] = None,
        video_tags: Optional[List[str]] = None
    ) -> ProductInfo:
        """
        영상 메타데이터에서 제품 정보 추출

        Args:
            video_title: 영상 제목 (중국어)
            video_description: 영상 설명
            video_tags: 영상 태그

        Returns:
            ProductInfo
        """
        print(f"🔍 제품 정보 추출 중...")
        print(f"   제목: {video_title}")

        # AI 프롬프트 구성
        prompt = f"""
다음은 중국 더우인(Douyin)의 쇼핑 영상 정보입니다.
이 영상에서 소개하는 제품의 정보를 추출하고 한국어로 번역해주세요.

영상 제목: {video_title}
"""

        if video_description:
            prompt += f"\n영상 설명: {video_description}"

        if video_tags:
            prompt += f"\n태그: {', '.join(video_tags)}"

        prompt += """

다음 JSON 형식으로 응답해주세요:
{
  "product_name_ko": "한국어 제품명",
  "product_name_cn": "중국어 원제품명",
  "category": "카테고리 (전자제품/패션/뷰티/홈데코/주방용품 등)",
  "key_features": ["특징1", "특징2", "특징3"],
  "price_range": "가격대 추정 (예: 1-3만원)",
  "target_audience": "타겟층 (예: 20-30대 여성)"
}
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "당신은 중국 전자상거래 전문가이자 한국어 번역가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )

            import json
            result = json.loads(response.choices[0].message.content.strip())

            product_info = ProductInfo(
                product_name_ko=result["product_name_ko"],
                product_name_cn=result.get("product_name_cn", video_title),
                category=result["category"],
                key_features=result["key_features"],
                price_range=result.get("price_range"),
                target_audience=result.get("target_audience", "일반")
            )

            print(f"✅ 제품 정보 추출 완료")
            print(f"   제품명: {product_info.product_name_ko}")
            print(f"   카테고리: {product_info.category}")

            return product_info

        except Exception as e:
            print(f"❌ 제품 정보 추출 실패: {e}")
            # 기본값 반환
            return ProductInfo(
                product_name_ko=video_title,
                product_name_cn=video_title,
                category="기타",
                key_features=["제품 특징 1", "제품 특징 2"],
                target_audience="일반"
            )

    def generate_shorts_script(
        self,
        product_info: ProductInfo,
        target_length: int = 60
    ) -> ShortsScript:
        """
        제품 정보를 바탕으로 한국어 쇼츠 대본 생성

        Args:
            product_info: 제품 정보
            target_length: 목표 길이 (초)

        Returns:
            ShortsScript
        """
        print(f"✍️ 쇼츠 대본 생성 중...")

        prompt = f"""
다음 제품에 대한 {target_length}초 길이의 유튜브 쇼츠 대본을 작성해주세요.

제품명: {product_info.product_name_ko}
카테고리: {product_info.category}
주요 특징:
{chr(10).join(f'- {f}' for f in product_info.key_features)}
타겟층: {product_info.target_audience}

대본 작성 가이드:
1. 첫 3초 훅(Hook): 시청자의 시선을 확 잡을 수 있는 문장
   - 질문형, 놀라운 사실, 공감형 중 하나 선택
   - 예: "이거 하나면 청소가 10분 컷?!"

2. 메인 내용 (30-50초):
   - 제품의 핵심 특징 3가지를 자연스럽게 설명
   - 구체적인 사용 상황 제시
   - 한국 소비자에게 어필할 포인트 강조

3. 행동 유도 (마지막 5-10초):
   - 쿠팡에서 구매 가능함을 자연스럽게 언급
   - 설명란 링크 클릭 유도
   - 예: "궁금하시죠? 설명란에 쿠팡 링크 남겨뒀으니 바로 확인해보세요!"

**중요**:
- TTS(음성합성)로 읽을 것이므로 자연스러운 구어체 사용
- 이모지나 특수문자 사용 금지
- 한 문장은 짧고 명확하게

다음 JSON 형식으로 응답:
{{
  "hook": "첫 3초 훅 문장",
  "main_content": "메인 내용 (문장 구분은 마침표로)",
  "call_to_action": "행동 유도 멘트",
  "estimated_duration": 60
}}
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "당신은 한국 유튜브 쇼츠 전문 작가입니다. 짧고 임팩트 있는 대본을 작성합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=600
            )

            import json
            result = json.loads(response.choices[0].message.content.strip())

            script = ShortsScript(
                hook=result["hook"],
                main_content=result["main_content"],
                call_to_action=result["call_to_action"],
                estimated_duration=result.get("estimated_duration", target_length)
            )

            print(f"✅ 대본 생성 완료 (예상 길이: {script.estimated_duration}초)")
            return script

        except Exception as e:
            print(f"❌ 대본 생성 실패: {e}")
            # 기본 대본 반환
            return ShortsScript(
                hook=f"이거 대박이에요! {product_info.product_name_ko}",
                main_content=f"{product_info.product_name_ko}는 {', '.join(product_info.key_features[:2])} 특징이 있습니다. 정말 편리하고 유용한 제품이에요.",
                call_to_action="설명란에 쿠팡 링크 남겼으니 확인해보세요!",
                estimated_duration=target_length
            )

    def get_full_script_text(self, script: ShortsScript) -> str:
        """대본 전체 텍스트 반환"""
        return f"{script.hook} {script.main_content} {script.call_to_action}"


def main():
    """테스트 코드"""
    analyzer = ProductAnalyzer()

    # 테스트용 더우인 영상 정보
    video_title = "🔥超火爆！智能清洁机器人，懒人必备神器！"
    video_description = "一键清洁全屋，智能规划路径，超长续航"

    # 제품 정보 추출
    product_info = analyzer.analyze_video_and_extract_product(
        video_title=video_title,
        video_description=video_description
    )

    print("\n📦 추출된 제품 정보:")
    print(f"  한국어명: {product_info.product_name_ko}")
    print(f"  카테고리: {product_info.category}")
    print(f"  특징: {', '.join(product_info.key_features)}")
    print()

    # 쇼츠 대본 생성
    script = analyzer.generate_shorts_script(product_info, target_length=60)

    print("\n📝 생성된 쇼츠 대본:")
    print(f"\n[훅 (첫 3초)]")
    print(script.hook)
    print(f"\n[메인 내용]")
    print(script.main_content)
    print(f"\n[행동 유도]")
    print(script.call_to_action)
    print(f"\n예상 길이: {script.estimated_duration}초")


if __name__ == "__main__":
    main()
