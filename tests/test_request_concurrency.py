"""A slow upload must not stall other visitors' requests on the single event loop."""

import asyncio
import time

import httpx
import pytest

import api.main as api_main
import api.routes as routes

SLOW_PARSE_SECONDS = 1.0


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_slow_csv_parsing_does_not_block_other_requests(monkeypatch) -> None:
    real_read_csv = routes.pd.read_csv

    def slow_read_csv(*args, **kwargs):
        time.sleep(SLOW_PARSE_SECONDS)
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(routes.pd, "read_csv", slow_read_csv)
    finished: list[str] = []

    async def request(name: str, call):
        response = await call
        finished.append(name)
        return response

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        upload = asyncio.create_task(
            request(
                "upload",
                client.post(
                    "/api/v1/uploads/preview",
                    files={"file": ("sales.csv", "Invoice,Total\nA001,100", "text/csv")},
                ),
            )
        )
        # Let the upload reach its slow parse before asking for health. A wall-clock
        # timer would be wrong here: a blocked loop also pauses this test.
        await asyncio.sleep(0.2)
        health = await request("health", client.get("/api/v1/health"))
        upload_response = await upload

    assert health.status_code == 200
    assert upload_response.status_code == 200
    # If parsing ran on the event loop, health could only finish after the upload.
    assert finished == ["health", "upload"]
