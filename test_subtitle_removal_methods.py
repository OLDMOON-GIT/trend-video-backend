"""
중국 영상 변환 - 자막 제거 방법 테스트 스크립트

각 자막 제거 방법의 설치 여부 및 사용 가능 여부를 확인합니다.
"""

import sys
import io
from pathlib import Path

# Windows에서 UTF-8 출력
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def test_method_availability():
    """각 자막 제거 방법의 사용 가능 여부 확인"""

    results = {
        "methods": [],
        "total": 0,
        "available": 0,
        "unavailable": 0
    }

    print("=" * 60)
    print("🔍 중국 영상 변환 - 자막 제거 방법 테스트")
    print("=" * 60)
    print()

    # 1. LAMA-VSR (video-subtitle-remover) - 기본 방법
    print("1️⃣ LAMA-VSR (video-subtitle-remover)")
    print("   설명: 자막 제거 전용 AI 모델 (가장 효과적)")
    print("   속도: ⭐⭐⭐ (중간)")
    print("   품질: ⭐⭐⭐⭐⭐ (최고)")

    vsr_dir = Path(__file__).parent / "video-subtitle-remover"
    vsr_backend = vsr_dir / "backend"
    vsr_available = vsr_dir.exists() and vsr_backend.exists()

    if vsr_available:
        try:
            sys.path.insert(0, str(vsr_dir))
            sys.path.insert(0, str(vsr_backend))
            from backend.main import SubtitleRemover
            print("   상태: ✅ 사용 가능 (권장)")
            results["available"] += 1
        except ImportError as e:
            print(f"   상태: ❌ 설치되었으나 import 실패: {e}")
            vsr_available = False
            results["unavailable"] += 1
    else:
        print(f"   상태: ❌ 설치 안됨")
        print(f"   경로: {vsr_dir}")
        results["unavailable"] += 1

    results["methods"].append({
        "name": "LAMA-VSR",
        "code": "lama-vsr",
        "available": vsr_available,
        "speed": "중간",
        "quality": "최고",
        "recommended": True
    })
    results["total"] += 1
    print()

    # 2. LAMA (Big-LaMa)
    print("2️⃣ LAMA (Big-LaMa) 인페인팅")
    print("   설명: 범용 AI 인페인팅 (워터마크 제거용)")
    print("   속도: ⭐⭐ (느림)")
    print("   품질: ⭐⭐⭐⭐ (우수)")

    lama_model_dir = vsr_backend / "models" / "big-lama" if vsr_backend.exists() else None
    lama_available = False

    if lama_model_dir and lama_model_dir.exists():
        model_files = list(lama_model_dir.glob("big-lama_*.pt"))
        if model_files:
            try:
                import torch
                print(f"   상태: ✅ 사용 가능 (모델 {len(model_files)}개)")
                lama_available = True
                results["available"] += 1
            except ImportError:
                print("   상태: ⚠️ 모델은 있으나 PyTorch 없음")
                results["unavailable"] += 1
        else:
            print(f"   상태: ❌ 모델 파일 없음")
            results["unavailable"] += 1
    else:
        print(f"   상태: ❌ 모델 디렉토리 없음")
        results["unavailable"] += 1

    results["methods"].append({
        "name": "LAMA",
        "code": "lama",
        "available": lama_available,
        "speed": "느림",
        "quality": "우수",
        "recommended": False
    })
    results["total"] += 1
    print()

    # 3. 검은색 박스 (FFmpeg)
    print("3️⃣ 검은색 박스 (FFmpeg)")
    print("   설명: 자막 영역을 검은색으로 가림")
    print("   속도: ⭐⭐⭐⭐⭐ (초고속, 1-2초)")
    print("   품질: ⭐ (자막만 가림, AI 처리 없음)")

    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        if result.returncode == 0:
            print("   상태: ✅ 사용 가능 (빠른 테스트용)")
            black_available = True
            results["available"] += 1
        else:
            print("   상태: ❌ FFmpeg 실행 실패")
            black_available = False
            results["unavailable"] += 1
    except Exception as e:
        print(f"   상태: ❌ FFmpeg 없음: {e}")
        black_available = False
        results["unavailable"] += 1

    results["methods"].append({
        "name": "검은색 박스",
        "code": "black",
        "available": black_available,
        "speed": "초고속",
        "quality": "낮음",
        "recommended": False
    })
    results["total"] += 1
    print()

    # 4. STTN
    print("4️⃣ STTN (Spatial-Temporal Transformer)")
    print("   설명: video-subtitle-remover의 STTN 모델")
    print("   속도: ⭐⭐⭐ (중간)")
    print("   품질: ⭐⭐⭐⭐ (우수)")

    sttn_model = vsr_backend / "models" / "sttn" / "infer_model.pth" if vsr_backend.exists() else None
    sttn_available = sttn_model and sttn_model.exists()

    if sttn_available:
        print(f"   상태: ✅ 사용 가능")
        results["available"] += 1
    else:
        print(f"   상태: ❌ 모델 없음")
        results["unavailable"] += 1

    results["methods"].append({
        "name": "STTN",
        "code": "sttn",
        "available": sttn_available,
        "speed": "중간",
        "quality": "우수",
        "recommended": False
    })
    results["total"] += 1
    print()

    # 5. E2FGVI
    print("5️⃣ E2FGVI (Flow-Guided Video Inpainting)")
    print("   설명: EraseSubtitles의 E2FGVI 모델")
    print("   속도: ⭐⭐ (느림)")
    print("   품질: ⭐⭐⭐⭐ (우수)")

    erase_dir = Path(__file__).parent / "EraseSubtitles"
    e2fgvi_model = erase_dir / "E2FGVI" / "release_model" / "E2FGVI-CVPR22.pth"
    e2fgvi_available = e2fgvi_model.exists()

    if e2fgvi_available:
        print(f"   상태: ✅ 사용 가능")
        results["available"] += 1
    else:
        print(f"   상태: ❌ 모델 없음")
        print(f"   다운로드: https://drive.google.com/file/d/1tNJMTJ2gmWdIXJoHVi5-H504uImUiJW9")
        results["unavailable"] += 1

    results["methods"].append({
        "name": "E2FGVI",
        "code": "e2fgvi",
        "available": e2fgvi_available,
        "speed": "느림",
        "quality": "우수",
        "recommended": False
    })
    results["total"] += 1
    print()

    # 6. ProPainter
    print("6️⃣ ProPainter (고품질 AI 인페인팅)")
    print("   설명: 최고 품질의 비디오 인페인팅")
    print("   속도: ⭐ (매우 느림)")
    print("   품질: ⭐⭐⭐⭐⭐ (최고)")

    propainter_dir = Path(__file__).parent / "ProPainter"
    propainter_script = propainter_dir / "inference_propainter.py"
    propainter_available = propainter_script.exists()

    if propainter_available:
        print(f"   상태: ✅ 사용 가능")
        results["available"] += 1
    else:
        print(f"   상태: ❌ 설치 안됨")
        results["unavailable"] += 1

    results["methods"].append({
        "name": "ProPainter",
        "code": "high",
        "available": propainter_available,
        "speed": "매우 느림",
        "quality": "최고",
        "recommended": False
    })
    results["total"] += 1
    print()

    # 7. OpenCV Telea (폴백)
    print("7️⃣ OpenCV Inpainting (Telea)")
    print("   설명: OpenCV 기본 인페인팅 (폴백)")
    print("   속도: ⭐⭐⭐⭐ (빠름)")
    print("   품질: ⭐⭐ (보통)")

    try:
        import cv2
        print(f"   상태: ✅ 사용 가능 (OpenCV {cv2.__version__})")
        opencv_available = True
        results["available"] += 1
    except ImportError:
        print("   상태: ❌ OpenCV 없음")
        opencv_available = False
        results["unavailable"] += 1

    results["methods"].append({
        "name": "OpenCV Telea",
        "code": "fast",
        "available": opencv_available,
        "speed": "빠름",
        "quality": "보통",
        "recommended": False
    })
    results["total"] += 1
    print()

    # 요약
    print("=" * 60)
    print("📊 요약")
    print("=" * 60)
    print(f"✅ 사용 가능: {results['available']}/{results['total']}개")
    print(f"❌ 사용 불가: {results['unavailable']}/{results['total']}개")
    print()

    # 권장 방법
    print("=" * 60)
    print("💡 권장 사용 방법")
    print("=" * 60)

    available_methods = [m for m in results["methods"] if m["available"]]

    if available_methods:
        print("\n사용 가능한 방법:")
        for method in available_methods:
            recommended = " ⭐ 권장" if method["recommended"] else ""
            print(f"  • {method['name']} (code: '{method['code']}')")
            print(f"    속도: {method['speed']}, 품질: {method['quality']}{recommended}")

        # 기본 방법 확인
        default_method = next((m for m in available_methods if m["code"] == "lama-vsr"), None)
        if default_method:
            print(f"\n✅ 현재 기본값: {default_method['name']} ('{default_method['code']}')")
        else:
            print(f"\n⚠️ 기본 방법(LAMA-VSR)을 사용할 수 없습니다.")
            if available_methods:
                fallback = available_methods[0]
                print(f"   대체 방법: {fallback['name']} ('{fallback['code']}')")
    else:
        print("\n❌ 사용 가능한 방법이 없습니다!")
        print("   최소한 FFmpeg(검은색 박스) 또는 OpenCV는 필요합니다.")

    print()
    print("=" * 60)
    print("📝 사용 방법")
    print("=" * 60)
    print("코드에서 quality_mode 파라미터로 방법 선택:")
    print()
    print("  remove_watermark_ai(")
    print("      input_video,")
    print("      output_video,")
    print("      quality_mode='lama-vsr'  # 여기서 방법 선택")
    print("  )")
    print()

    return results

if __name__ == '__main__':
    test_method_availability()
