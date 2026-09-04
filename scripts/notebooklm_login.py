"""NotebookLM 로그인 (최초 1회 실행).

실행: python scripts/notebooklm_login.py

브라우저 창이 뜨면 구글 계정으로 로그인하세요. 터미널에 따로 엔터를 칠 필요 없이,
로그인이 끝나서 NotebookLM 홈 화면으로 넘어가면 스크립트가 자동으로 감지해서 저장하고
브라우저를 닫습니다 (최대 10분 대기).

주의: notebooklm-py 패키지의 공식 CLI(`notebooklm login`)는 이 환경의 파이썬 버전과
호환 문제가 있어서, 같은 방식을 이 스크립트로 직접 구현했습니다.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from notebooklm.paths import get_storage_path, get_browser_profile_dir
from state_store import clear_login_needed

LOGIN_WAIT_TIMEOUT_SECONDS = 600


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright가 설치되어 있지 않아요. 다음을 실행하세요:")
        print("  pip install playwright")
        print("  playwright install chromium")
        return

    storage_path = get_storage_path()
    browser_profile = get_browser_profile_dir()
    storage_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    browser_profile.mkdir(parents=True, exist_ok=True, mode=0o700)

    print("브라우저를 여는 중이에요...")
    print(f"저장 위치: {storage_path}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(browser_profile),
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
            ],
            ignore_default_args=["--enable-automation"],
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://notebooklm.google.com/")

        print("\n뜬 브라우저 창에서 구글 계정으로 로그인해주세요.")
        print(f"로그인이 끝나면 자동으로 감지해서 저장할게요 (최대 {LOGIN_WAIT_TIMEOUT_SECONDS // 60}분 대기)...\n", flush=True)

        deadline = time.monotonic() + LOGIN_WAIT_TIMEOUT_SECONDS
        time.sleep(3)  # 구글 로그인 페이지로의 리다이렉트가 시작될 시간을 줌

        def is_logged_in_url(url):
            # 구글이 이름을 "notebook.google.com"으로 바꿔서 두 도메인 다 확인함
            return (
                ("notebooklm.google.com" in url or "notebook.google.com" in url)
                and "accounts.google.com" not in url
            )

        logged_in = False
        last_urls_printed = None
        while time.monotonic() < deadline:
            # 탭이 여러 개 뜰 수 있어 모든 탭을 확인함 (예전 버전은 첫 탭만 봐서 놓치는 문제가 있었음)
            urls = [p.url for p in context.pages]
            if urls != last_urls_printed:
                print(f"[확인 중] 열린 탭: {urls}", flush=True)
                last_urls_printed = urls

            if any(is_logged_in_url(u) for u in urls):
                time.sleep(2)  # 쿠키가 완전히 설정될 시간을 잠깐 더 줌
                logged_in = True
                break
            time.sleep(2)

        if not logged_in:
            print(f"시간 초과: {LOGIN_WAIT_TIMEOUT_SECONDS}초 안에 로그인이 감지되지 않았어요.")
            print("다시 실행해서 시도해주세요.")
            context.close()
            return

        context.storage_state(path=str(storage_path))
        storage_path.chmod(0o600)
        context.close()

    clear_login_needed()

    print(f"로그인 완료, 저장했어요: {storage_path}")


if __name__ == "__main__":
    main()
