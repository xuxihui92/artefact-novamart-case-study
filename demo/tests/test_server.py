"""Unit tests for the local HTTP API surface."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from return_desk import ReturnDesk
from return_desk.server import create_server


class TestServer(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        desk = ReturnDesk(Path(temp.name) / "server.sqlite3")
        self.server = create_server(desk, 0)
        host, port = self.server.server_address
        self.base = f"http://{host}:{port}"
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def _get(self, path):
        with urlopen(self.base + path, timeout=2) as response:
            return response.status, json.loads(response.read().decode())

    def _post(self, path, payload):
        body = json.dumps(payload).encode()
        request = Request(
            self.base + path,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode())

    def test_policies_and_search(self):
        status, payload = self._get("/api/policies")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["policies"]), 3)
        self.assertEqual(payload["store"], "STORE-014")
        status, payload = self._get("/api/search?q=" + quote("proof of purchase"))
        self.assertEqual(status, 200)
        self.assertTrue(payload["results"])
        self.assertEqual(payload["results"][0]["id"], "RET-01.2")

    def test_chat_happy_path(self):
        status, payload = self._post("/api/chat", {"message": "What is the order status for NM-1045?"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["kind"], "order")
        self.assertEqual(payload["order"]["status"], "Ready for pickup")

    def test_chat_rejects_empty_message(self):
        body = json.dumps({"message": ""}).encode()
        request = Request(
            self.base + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
