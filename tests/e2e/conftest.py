"""Fixtures for the browser tests.

The application is started as a real process in demo mode, so these tests
exercise the same server a user would hit, with no network and no keys.
"""

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, Page

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STARTUP_TIMEOUT_SECONDS = 45


def free_port() -> int:
    """Pick a port the operating system says is free."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    """Run the application for the whole session and yield its URL."""
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ,
        "LLM_PROVIDER": "fake",
        # The seed law rows are unreviewed, so the law views need this on to
        # show anything. The UI labels every such row.
        "LAW_DATA_SHOW_UNREVIEWED": "true",
        "LOG_LEVEL": "WARNING",
        "RATE_LIMIT_PER_MINUTE": "1000",
        "EXPORT_RATE_LIMIT_PER_MINUTE": "1000",
    }
    process = subprocess.Popen(  # noqa: S603 - fixed command, no shell
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = (process.stdout.read() if process.stdout else b"").decode()
            pytest.fail(f"the application exited during startup:\n{output}")
        try:
            if httpx.get(f"{url}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.3)
    else:
        process.terminate()
        pytest.fail("the application did not start in time")

    try:
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)
        if process.stdout is not None:
            process.stdout.close()


@pytest.fixture
def page(browser: Browser, base_url: str) -> Iterator[Page]:
    """A page with console and page errors turned into test failures."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    problems: list[str] = []
    page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
    page.on(
        "console",
        lambda message: (
            problems.append(f"console error: {message.text}") if message.type == "error" else None
        ),
    )

    yield page

    context.close()
    assert not problems, "\n".join(problems)


@pytest.fixture
def loaded(page: Page, base_url: str) -> Page:
    """A page with the rental sample loaded and analysed."""
    page.goto(base_url, wait_until="networkidle")
    page.click('[data-sample="leave-licence-v1"]')
    page.wait_for_selector(".seal", timeout=40_000)
    return page
