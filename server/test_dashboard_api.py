import asyncio
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from dashboard_api import DashboardHub, create_app, read_jsonl_input


class DashboardHubTest(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_broadcasts_only_state_changes(self):
        hub = DashboardHub()
        queue = await hub.subscribe()
        self.assertFalse(await hub.ingest({"message_type": "unknown"}))
        self.assertTrue(await hub.ingest({
            "message_type": "activity_prediction",
            "window_end_us": 10,
            "activity": "walking",
        }))
        snapshot = await asyncio.wait_for(queue.get(), timeout=0.1)
        self.assertEqual(snapshot["latest_prediction"]["activity"], "walking")
        await hub.unsubscribe(queue)

    async def test_slow_subscriber_receives_latest_snapshot(self):
        hub = DashboardHub()
        queue = await hub.subscribe(max_pending=1)
        for timestamp in (1, 2, 3):
            await hub.ingest({
                "message_type": "activity_prediction",
                "window_end_us": timestamp,
                "activity": "walking",
            })
        snapshot = queue.get_nowait()
        self.assertEqual(snapshot["latest_prediction"]["window_end_us"], 3)


class DashboardAPITest(unittest.TestCase):
    def setUp(self):
        self.hub = DashboardHub()
        self.client = TestClient(create_app(self.hub))

    def test_health_and_initial_state(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        state = self.client.get("/api/state").json()
        self.assertEqual(state["message_type"], "dashboard_state")
        self.assertEqual(state["revision"], 0)

    def test_websocket_gets_initial_and_updated_snapshot(self):
        with self.client.websocket_connect("/ws") as websocket:
            initial = websocket.receive_json()
            self.assertEqual(initial["revision"], 0)
            asyncio.run(self.hub.ingest({
                "message_type": "activity_prediction",
                "window_end_us": 20,
                "activity": "sitting",
            }))
            updated = websocket.receive_json()
            self.assertEqual(updated["revision"], 1)
            self.assertEqual(updated["latest_prediction"]["activity"], "sitting")

    def test_jsonl_reader_ingests_valid_records_and_reports_bad_lines(self):
        input_stream = io.StringIO("".join([
            "bad-json\n",
            "[]\n",
            json.dumps({
                "message_type": "activity_prediction",
                "window_end_us": 30,
                "activity": "walking",
            }) + "\n",
        ]))
        errors = io.StringIO()

        async def exercise():
            loop = asyncio.get_running_loop()
            await asyncio.to_thread(
                read_jsonl_input,
                input_stream,
                self.hub,
                loop,
                errors,
            )
            return await self.hub.snapshot()

        snapshot = asyncio.run(exercise())
        self.assertEqual(snapshot["latest_prediction"]["activity"], "walking")
        self.assertIn("invalid JSON", errors.getvalue())
        self.assertIn("non-object JSON", errors.getvalue())

    def test_serves_built_dashboard_without_shadowing_api(self):
        with TemporaryDirectory() as temporary_directory:
            static_dir = Path(temporary_directory)
            (static_dir / "assets").mkdir()
            (static_dir / "index.html").write_text(
                "<!doctype html><title>VSense Test</title>",
                encoding="utf-8",
            )
            (static_dir / "assets" / "app.js").write_text(
                "console.log('vsense')",
                encoding="utf-8",
            )
            client = TestClient(create_app(DashboardHub(), static_dir=static_dir))
            self.assertIn("VSense Test", client.get("/").text)
            self.assertIn("VSense Test", client.get("/dashboard/route").text)
            self.assertIn("vsense", client.get("/assets/app.js").text)
            self.assertEqual(client.get("/health").json(), {"status": "ok"})
            self.assertEqual(
                client.get("/api/state").json()["message_type"],
                "dashboard_state",
            )

    def test_rejects_missing_dashboard_build(self):
        with TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "index.html not found"):
                create_app(DashboardHub(), static_dir=temporary_directory)


if __name__ == "__main__":
    unittest.main()
