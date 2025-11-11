"""
더우인(Douyin) 영상 다운로더
yt-dlp를 사용하여 더우인 영상을 다운로드합니다.
"""
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class DownloadResult:
    """다운로드 결과"""
    success: bool
    video_path: Optional[Path] = None
    error: Optional[str] = None
    video_info: Optional[Dict] = None


class DouyinDownloader:
    """더우인 영상 다운로더"""

    def __init__(self, output_dir: Path, cookies_file: Optional[Path] = None):
        """
        Args:
            output_dir: 다운로드 영상 저장 디렉토리
            cookies_file: Douyin 쿠키 파일 경로 (선택)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_file = cookies_file

    def _normalize_url(self, url: str) -> str:
        """
        Douyin URL을 정규화합니다.
        검색/모달 URL에서 modal_id를 추출하여 실제 비디오 URL로 변환합니다.

        Args:
            url: 원본 URL

        Returns:
            정규화된 URL
        """
        from urllib.parse import urlparse, parse_qs

        try:
            parsed = urlparse(url)

            # modal_id가 있는 경우 (검색 결과 등)
            if 'modal_id' in url:
                query_params = parse_qs(parsed.query)
                if 'modal_id' in query_params:
                    modal_id = query_params['modal_id'][0]
                    return f"https://www.douyin.com/video/{modal_id}"

            # 이미 올바른 형식이면 그대로 반환
            return url

        except Exception as e:
            print(f"⚠️ URL 정규화 실패: {e}, 원본 URL 사용")
            return url

    def download(
        self,
        video_url: str,
        video_id: str,
        check_watermark: bool = True
    ) -> DownloadResult:
        """
        더우인 영상 다운로드

        Args:
            video_url: 더우인 영상 URL
            video_id: 영상 ID
            check_watermark: 워터마크 확인 여부

        Returns:
            DownloadResult
        """
        print(f"📥 영상 다운로드 시작: {video_url}")

        # URL 정규화 (modal_id 추출 및 변환)
        video_url = self._normalize_url(video_url)
        print(f"🔗 정규화된 URL: {video_url}")

        # 출력 파일 경로
        output_template = str(self.output_dir / f"{video_id}.%(ext)s")

        try:
            # yt-dlp 명령어 구성 (Python 모듈로 실행)
            import sys
            cmd = [
                sys.executable,  # 현재 Python 인터프리터
                "-m", "yt_dlp",
                "--no-warnings",
                "--no-check-certificate",
                # 최고 화질 선택
                "-f", "best",
                # 메타데이터 포함
                "--write-info-json",
                # 출력 템플릿
                "-o", output_template,
            ]

            # 쿠키 파일 추가 (있는 경우)
            if self.cookies_file and self.cookies_file.exists():
                cmd.extend(["--cookies", str(self.cookies_file)])
                print(f"🍪 쿠키 파일 사용: {self.cookies_file}")
            else:
                # 쿠키 없이도 시도 (일부 영상은 가능)
                print("⚠️ 쿠키 파일 없음 - 쿠키 없이 시도")

            cmd.append(video_url)

            print(f"🔧 실행 명령: {' '.join(cmd)}")

            # yt-dlp 실행
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=300  # 5분 타임아웃
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                print(f"❌ 다운로드 실패: {error_msg}")

                # 쿠키 오류인 경우 친절한 메시지 추가
                if "Fresh cookies" in error_msg or "cookies" in error_msg.lower():
                    error_msg += "\n\n💡 해결 방법:\n"
                    error_msg += "1. Chrome에서 'Get cookies.txt LOCALLY' 확장 프로그램 설치\n"
                    error_msg += "2. https://www.douyin.com에 로그인\n"
                    error_msg += "3. 확장 프로그램으로 cookies.txt 추출\n"
                    error_msg += f"4. cookies.txt를 {self.output_dir}/cookies.txt에 저장\n"
                    error_msg += "5. 다시 시도해주세요"

                return DownloadResult(
                    success=False,
                    error=error_msg
                )

            # 다운로드된 파일 찾기
            video_files = list(self.output_dir.glob(f"{video_id}.*"))
            video_files = [f for f in video_files if f.suffix not in ['.json', '.part']]

            if not video_files:
                return DownloadResult(
                    success=False,
                    error="다운로드된 영상 파일을 찾을 수 없습니다"
                )

            video_path = video_files[0]
            print(f"✅ 다운로드 완료: {video_path}")

            # 메타데이터 읽기
            info_json_path = video_path.with_suffix('.info.json')
            video_info = None
            if info_json_path.exists():
                with open(info_json_path, 'r', encoding='utf-8') as f:
                    video_info = json.load(f)

            # 워터마크 확인 (선택적)
            if check_watermark and video_info:
                has_watermark = self._check_watermark(video_info)
                if has_watermark:
                    print("⚠️ 경고: 영상에 워터마크가 있을 수 있습니다")

            return DownloadResult(
                success=True,
                video_path=video_path,
                video_info=video_info
            )

        except subprocess.TimeoutExpired:
            return DownloadResult(
                success=False,
                error="다운로드 타임아웃 (5분 초과)"
            )
        except Exception as e:
            import traceback
            error_msg = f"다운로드 오류: {str(e)}\n{traceback.format_exc()}"
            print(f"❌ {error_msg}")
            return DownloadResult(
                success=False,
                error=error_msg
            )

    def _check_watermark(self, video_info: Dict) -> bool:
        """
        영상에 워터마크가 있는지 확인

        Args:
            video_info: yt-dlp에서 가져온 영상 정보

        Returns:
            True if 워터마크가 있을 가능성이 있음
        """
        # 더우인 영상은 보통 워터마크가 없는 원본을 다운로드 가능
        # 하지만 일부 영상은 워터마크가 포함될 수 있음
        # 여기서는 간단히 False 반환
        return False

    def get_video_info(self, video_url: str) -> Optional[Dict]:
        """
        영상 정보만 가져오기 (다운로드 없이)

        Args:
            video_url: 더우인 영상 URL

        Returns:
            영상 정보 딕셔너리
        """
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--no-check-certificate",
                video_url
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30
            )

            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)

        except Exception as e:
            print(f"❌ 영상 정보 가져오기 실패: {e}")

        return None

    def check_has_text_overlay(self, video_path: Path) -> bool:
        """
        영상에 텍스트 오버레이(자막)가 있는지 확인

        Args:
            video_path: 영상 파일 경로

        Returns:
            True if 텍스트 오버레이가 있음
        """
        # TODO: OCR 또는 영상 프레임 분석으로 텍스트 감지
        # 현재는 간단히 False 반환
        # 실제로는 Tesseract OCR + OpenCV를 사용하여 구현 가능
        return False


def main():
    """테스트 코드"""
    downloader = DouyinDownloader(output_dir=Path("downloads"))

    # 테스트 URL (실제 더우인 URL로 교체)
    test_url = "https://www.douyin.com/video/1234567890"

    # 다운로드
    result = downloader.download(
        video_url=test_url,
        video_id="test_video",
        check_watermark=True
    )

    if result.success:
        print(f"✅ 다운로드 성공!")
        print(f"   파일 경로: {result.video_path}")
        if result.video_info:
            print(f"   제목: {result.video_info.get('title', 'N/A')}")
            print(f"   길이: {result.video_info.get('duration', 0)}초")
    else:
        print(f"❌ 다운로드 실패: {result.error}")


if __name__ == "__main__":
    main()
