"""
AI Aggregator 사용 예시
다른 Python 스크립트에서 AI Aggregator를 라이브러리처럼 사용하는 방법
"""
import sys
import asyncio
from pathlib import Path

# Add src to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir / "src"))

from ai_aggregator.main import main
from ai_aggregator.queue_manager import QueueManager


async def query_ai_example():
    """간단한 AI 질의 예시"""
    question = "파이썬으로 비동기 프로그래밍하는 방법을 알려줘"

    # Claude만 사용
    agents = ['claude']

    # headless=True로 백그라운드 실행 (프로덕션 환경)
    # headless=False로 디버깅 시 브라우저 보기
    await main(
        question=question,
        headless=False,  # 디버깅용
        agents_to_use=agents,
        use_real_chrome=True
    )


async def query_multiple_ais():
    """여러 AI 동시 질의"""
    question = "가장 효율적인 데이터베이스 인덱싱 전략은?"

    # 여러 AI 동시 실행
    agents = ['claude', 'chatgpt', 'gemini']

    await main(
        question=question,
        headless=True,  # 백그라운드 실행
        agents_to_use=agents,
        use_real_chrome=True
    )


def queue_example():
    """큐 매니저 사용 예시 (서버 환경에서 동시 요청 처리)"""
    import uuid

    # 고유 작업 ID 생성
    task_id = str(uuid.uuid4())

    # 큐 매니저로 순차 처리 보장
    with QueueManager() as qm:
        # 작업 추가
        qm.add_to_queue(task_id, {
            "question": "비디오 생성 알고리즘 설명",
            "agents": ["claude"]
        })

        # 작업 실행
        qm.update_task_status(task_id, "processing")

        # AI 질의 실행 (여기에 실제 로직)
        print(f"Processing task {task_id}...")

        # 완료 후 큐에서 제거
        qm.update_task_status(task_id, "completed")
        qm.remove_from_queue(task_id)


if __name__ == "__main__":
    print("=== AI Aggregator 사용 예시 ===\n")

    print("1. 단일 AI 질의")
    asyncio.run(query_ai_example())

    # print("\n2. 여러 AI 동시 질의")
    # asyncio.run(query_multiple_ais())

    # print("\n3. 큐 매니저 사용")
    # queue_example()
