/**
 * 상품 스크립트 DB 폴백 테스트
 *
 * productInfo가 API에 전달되지 않아도 DB에서 자동으로 로드되는지 확인
 */

const TEST_TITLE = '[광고] 바디인솔 프리미엄 무지 중목 양말, 20켤레';

async function testProductScriptGeneration() {
  console.log('='.repeat(60));
  console.log('상품 스크립트 생성 테스트 (DB 폴백)');
  console.log('='.repeat(60));
  console.log('');

  console.log(`📝 테스트 제목: ${TEST_TITLE}`);
  console.log('⚠️ productInfo를 전달하지 않음 (DB에서 자동 로드되어야 함)');
  console.log('');

  try {
    const response = await fetch('http://localhost:3000/api/scripts/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Request': 'automation-system' // Internal request from automation
      },
      body: JSON.stringify({
        title: TEST_TITLE,
        type: 'product',
        // productInfo는 전달하지 않음 - DB에서 로드되어야 함
        model: 'gemini',
        useClaudeLocal: false,
        userId: 'b5d1f064-60b9-45ab-9bcd-d36948196459', // Test user ID
        category: '상품'
      })
    });

    const result = await response.json();

    if (!response.ok) {
      console.error('❌ API 호출 실패:', result);
      return false;
    }

    console.log('✅ API 호출 성공');
    console.log('');

    // 결과 확인
    if (result.script && result.script.id) {
      console.log(`✅ 스크립트 생성됨: ${result.script.id}`);
      console.log('');

      // 스크립트 내용에서 플레이스홀더 확인
      const content = result.script.content || '';
      const hasThumbnailPlaceholder = content.includes('{thumbnail}');
      const hasProductLinkPlaceholder = content.includes('{product_link}');
      const hasDescriptionPlaceholder = content.includes('{product_description}');

      if (hasThumbnailPlaceholder || hasProductLinkPlaceholder || hasDescriptionPlaceholder) {
        console.log('❌ 플레이스홀더가 치환되지 않음:');
        if (hasThumbnailPlaceholder) console.log('   - {thumbnail} 발견');
        if (hasProductLinkPlaceholder) console.log('   - {product_link} 발견');
        if (hasDescriptionPlaceholder) console.log('   - {product_description} 발견');
        console.log('');
        console.log('스크립트 미리보기:');
        console.log(content.substring(0, 500));
        return false;
      } else {
        console.log('✅ 플레이스홀더 없음 - 정상적으로 치환됨');

        // 실제 값이 포함되어 있는지 확인
        const hasImageUrl = content.includes('https://image10.coupangcdn.com');
        const hasProductLink = content.includes('https://link.coupang.com');

        if (hasImageUrl && hasProductLink) {
          console.log('✅ 실제 상품 정보가 포함됨');
          console.log('   - 이미지 URL: 확인됨');
          console.log('   - 상품 링크: 확인됨');
          return true;
        } else {
          console.log('⚠️ 실제 상품 정보가 포함되지 않음');
          return false;
        }
      }
    } else {
      console.error('❌ 스크립트 생성 실패:', result);
      return false;
    }

  } catch (error) {
    console.error('❌ 테스트 실패:', error.message);
    return false;
  }
}

// 테스트 실행
testProductScriptGeneration()
  .then(success => {
    console.log('');
    console.log('='.repeat(60));
    if (success) {
      console.log('✅ 테스트 성공: 상품 정보가 DB에서 로드되어 올바르게 치환됨');
    } else {
      console.log('❌ 테스트 실패: 상품 정보 치환 문제 발생');
    }
    console.log('='.repeat(60));
    process.exit(success ? 0 : 1);
  });
