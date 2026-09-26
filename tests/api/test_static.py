"""How the browser application's own files are served and cached."""

import pytest
from app.main import STATIC_CACHE_CONTROL
from httpx import AsyncClient


@pytest.mark.parametrize("path", ["/", "/js/main.js", "/css/base.css", "/i18n/en.json"])
async def test_static_files_are_revalidated_rather_than_guessed_fresh(
    client: AsyncClient, path: str
) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == STATIC_CACHE_CONTROL


async def test_an_unchanged_file_comes_back_as_a_bodyless_304(client: AsyncClient) -> None:
    """What makes revalidating on every use cheap: nothing is re-sent."""
    first = await client.get("/js/main.js")
    again = await client.get("/js/main.js", headers={"If-None-Match": first.headers["ETag"]})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["Cache-Control"] == STATIC_CACHE_CONTROL
