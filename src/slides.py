"""NotebookLM으로 슬라이드 요약(PDF) 생성.

notebooklm-py 라이브러리는 저장된 로그인 쿠키를 꺼내서 별도 프로그램(httpx)으로
재사용하는 방식인데, 구글이 최근 "세션을 브라우저에 묶는" 보안을 강화하면서
그 방식이 막힌 것을 실제로 확인함. 그래서 실제 API 호출과 파일 다운로드는 저장된
로그인 세션을 가진 "살아있는 브라우저(Playwright)"를 거쳐서 실행하도록 우회함.

또한 라이브러리의 `wait_for_completion`이 "대기 중(PENDING)" 상태를 "완료"로 잘못
판단하는 버그가 있는 것도 실제 테스트로 확인해서, 완료 여부는 직접 폴링해서 확인함.
실제 슬라이드 생성은 30분 가까이 걸릴 수 있어서(실측), 넉넉한 시간을 기다린다.

최초 1회 `python scripts/notebooklm_login.py`로 로그인해둬야 동작한다.
"""
import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright
import notebooklm._core as _core_module
from notebooklm import NotebookLMClient, SlideDeckFormat
from notebooklm.auth import AuthTokens, DEFAULT_STORAGE_PATH, extract_csrf_from_html, extract_session_id_from_html
from notebooklm.paths import get_browser_profile_dir
from notebooklm.rpc import encode_rpc_request, build_request_body, decode_response
from notebooklm._artifacts import ArtifactStatus, StudioContentType

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "config" / "slides"

# notebooklm-py가 만드는 요청 URL이 구글의 옛 도메인(notebooklm.google.com)을 가리키는데,
# 실제 로그인 페이지는 notebook.google.com이라 그대로 쓰면 다른 도메인(cross-origin) 요청이
# 되어 브라우저가 막아버림. 같은 도메인으로 바꿔서 우회함.
_OLD_DOMAIN = "notebooklm.google.com"
_NEW_DOMAIN = "notebook.google.com"

# 실측 결과 슬라이드 생성이 30분 가까이 걸리는 경우가 있어 넉넉하게 잡음
SLIDE_GENERATION_TIMEOUT_SECONDS = 40 * 60
SLIDE_POLL_INTERVAL_SECONDS = 20


class NotebookLMAuthError(Exception):
    """로그인 세션이 만료되어 재로그인이 필요할 때 발생시키는 예외."""


def is_logged_in():
    return DEFAULT_STORAGE_PATH.exists()


def _make_browser_rpc_call(page):
    """RPC 호출을 (httpx 대신) 실제 로그인된 브라우저 안에서 실행하도록 만드는 함수."""

    async def browser_rpc_call(self, method, params, source_path="/", allow_null=False):
        url = self._build_url(method, source_path).replace(_OLD_DOMAIN, _NEW_DOMAIN)
        rpc_request = encode_rpc_request(method, params)
        body = build_request_body(rpc_request, self.auth.csrf_token)

        result = await page.evaluate(
            """async ({url, body}) => {
                const resp = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'},
                    body: body,
                    credentials: 'include',
                });
                return {status: resp.status, text: await resp.text()};
            }""",
            {"url": url, "body": body},
        )
        if result["status"] >= 400:
            raise RuntimeError(f"{method.name} 호출 실패 (상태코드 {result['status']})")
        return decode_response(result["text"], method.value, allow_null=allow_null, debug=False)

    return browser_rpc_call


async def _wait_for_slide_deck(client, notebook_id):
    """슬라이드덱 아티팩트가 실제로 완료(status==COMPLETED)될 때까지 직접 폴링한다.

    (라이브러리 자체 wait_for_completion은 PENDING을 완료로 착각하는 버그가 있어 미사용)
    """
    deadline = time.monotonic() + SLIDE_GENERATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        raw_artifacts = await client.artifacts._list_raw(notebook_id)
        for art in raw_artifacts:
            if len(art) > 4 and art[2] == StudioContentType.SLIDE_DECK and art[4] == ArtifactStatus.COMPLETED:
                return art
        await asyncio.sleep(SLIDE_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"{SLIDE_GENERATION_TIMEOUT_SECONDS}초 안에 슬라이드 생성이 끝나지 않았어요.")


async def generate_slide_deck(video_title, video_url):
    """영상 하나를 NotebookLM에 넣어 슬라이드 PDF를 만든다. 완성된 PDF 경로를 반환한다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(get_browser_profile_dir()),
            headless=True,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(f"https://{_NEW_DOMAIN}/", wait_until="domcontentloaded")

        html = await page.content()
        try:
            csrf = extract_csrf_from_html(html)
            session_id = extract_session_id_from_html(html)
        except ValueError as e:
            await context.close()
            raise NotebookLMAuthError(str(e)) from e
        auth = AuthTokens(cookies={}, csrf_token=csrf, session_id=session_id)

        # RPC 호출을 브라우저 경유 방식으로 교체 (전역 클래스 패치라, 이 프로세스에서는 항상 이 방식 사용)
        _core_module.ClientCore.rpc_call = _make_browser_rpc_call(page)

        async with NotebookLMClient(auth) as client:
            notebook = await client.notebooks.create(title=video_title[:100])

            source = await client.sources.add_url(notebook.id, video_url, wait=True, wait_timeout=180)

            await client.artifacts.generate_slide_deck(
                notebook.id,
                source_ids=[source.id],
                language="ko",
                slide_format=SlideDeckFormat.DETAILED_DECK,
            )
            completed_artifact = await _wait_for_slide_deck(client, notebook.id)

            # 다운로드도 라이브러리 기본 방식(httpx) 대신 브라우저 컨텍스트로 직접 받음
            # (context.request는 브라우저 세션 쿠키를 그대로 써서 cross-origin이어도 정상 동작함, 실측 확인)
            pdf_url = completed_artifact[16][3]
            safe_name = "".join(c for c in video_title if c.isalnum() or c in " _-")[:80].strip()
            output_path = OUTPUT_DIR / f"{safe_name or notebook.id}.pdf"

            response = await context.request.get(pdf_url)
            output_path.write_bytes(await response.body())

        await context.close()

    return str(output_path)
