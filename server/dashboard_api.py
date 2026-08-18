"""FastAPI and WebSocket service for the live VSense dashboard."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TextIO

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard_state import DashboardState, DashboardStateConfig


class DashboardHub:
    """Own dashboard state and broadcast updated snapshots to subscribers."""

    def __init__(self, state: DashboardState | None = None):
        self.state = state or DashboardState()
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def ingest(self, record: dict) -> bool:
        async with self._lock:
            if not self.state.apply(record):
                return False
            snapshot = self.state.snapshot()
            for queue in tuple(self._subscribers):
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(snapshot)
            return True

    async def subscribe(self, max_pending: int = 1) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=max_pending)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        async with self._lock:
            self._subscribers.discard(queue)

    async def snapshot(self) -> dict:
        async with self._lock:
            return self.state.snapshot()


def read_jsonl_input(
    input_stream: TextIO,
    hub: DashboardHub,
    loop: asyncio.AbstractEventLoop,
    error_stream: TextIO,
):
    for line_number, line in enumerate(input_stream, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            print(
                f"Skipping invalid JSON on input line {line_number}: {exc}",
                file=error_stream,
            )
            continue
        if not isinstance(record, dict):
            print(
                f"Skipping non-object JSON on input line {line_number}",
                file=error_stream,
            )
            continue
        future = asyncio.run_coroutine_threadsafe(hub.ingest(record), loop)
        try:
            future.result()
        except Exception as exc:
            print(
                f"Could not ingest input line {line_number}: {exc}",
                file=error_stream,
            )


def create_app(
    hub: DashboardHub | None = None,
    *,
    input_stream: TextIO | None = None,
    error_stream: TextIO | None = None,
    static_dir: Path | str | None = None,
) -> FastAPI:
    dashboard_hub = hub or DashboardHub()
    errors = error_stream or sys.stderr
    reader_thread: threading.Thread | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        nonlocal reader_thread
        if input_stream is not None:
            loop = asyncio.get_running_loop()
            reader_thread = threading.Thread(
                target=read_jsonl_input,
                args=(input_stream, dashboard_hub, loop, errors),
                name="dashboard-jsonl-input",
                daemon=True,
            )
            reader_thread.start()
        yield

    app = FastAPI(title="VSense Dashboard API", version="1.0", lifespan=lifespan)
    app.state.dashboard_hub = dashboard_hub

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/state")
    async def state():
        return await dashboard_hub.snapshot()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        queue = await dashboard_hub.subscribe()
        try:
            await websocket.send_json(await dashboard_hub.snapshot())
            while True:
                await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            await dashboard_hub.unsubscribe(queue)

    if static_dir is not None:
        static_root = Path(static_dir).resolve()
        index_path = static_root / "index.html"
        assets_path = static_root / "assets"
        if not index_path.is_file():
            raise ValueError(f"dashboard index.html not found: {index_path}")
        if assets_path.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

        @app.get("/", include_in_schema=False)
        async def dashboard_index():
            return FileResponse(index_path)

        @app.get("/{frontend_path:path}", include_in_schema=False)
        async def dashboard_route(frontend_path: str):
            candidate = (static_root / frontend_path).resolve()
            if static_root in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(index_path)

    return app


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument(
        "--no-stdin",
        action="store_true",
        help="Do not read dashboard events as JSONL from stdin",
    )
    parser.add_argument(
        "--static-dir",
        type=Path,
        help="Serve a built React dashboard, for example web/dist",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    hub = DashboardHub(
        DashboardState(DashboardStateConfig(max_events=args.max_events))
    )
    app = create_app(
        hub,
        input_stream=None if args.no_stdin else sys.stdin,
        error_stream=sys.stderr,
        static_dir=args.static_dir,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
