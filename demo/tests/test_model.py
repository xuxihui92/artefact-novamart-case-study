"""Unit tests for optional model routing helpers."""
import json
import unittest
from unittest.mock import MagicMock, patch

from return_desk.model import model_route


class TestModelRoute(unittest.TestCase):
    def test_returns_selected_tool(self):
        payload = {
            "output": [
                {"type": "message"},
                {"type": "function_call", "name": "find_policy"},
            ]
        }
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(payload).encode()
        # urlopen yields a file-like object; json.load uses .read via the response object.
        # Prefer mocking json.load path through a fake with readable body via json.load(response).
        with patch("return_desk.model.urlopen") as urlopen, patch(
            "return_desk.model.json.load", return_value=payload
        ):
            urlopen.return_value = response
            self.assertEqual(model_route("key", "gpt-4.1-mini", "Where is my refund sent?"), "find_policy")

    def test_failure_returns_none(self):
        with patch("return_desk.model.urlopen", side_effect=OSError("down")):
            self.assertIsNone(model_route("key", "gpt-4.1-mini", "hello"))

    def test_rejects_unknown_tool_name(self):
        payload = {"output": [{"type": "function_call", "name": "delete_order"}]}
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("return_desk.model.urlopen", return_value=response), patch(
            "return_desk.model.json.load", return_value=payload
        ):
            self.assertIsNone(model_route("key", "gpt-4.1-mini", "hello"))

    def test_redacts_order_ids_in_request_body(self):
        captured = {}

        def fake_urlopen(request, timeout=5):
            captured["body"] = json.loads(request.data.decode())
            raise OSError("stop after capture")

        with patch("return_desk.model.urlopen", side_effect=fake_urlopen):
            model_route("key", "gpt-4.1-mini", "Can I return NM-1042?")
        self.assertEqual(captured["body"]["input"], "Can I return <demo order reference>?")
        self.assertNotIn("NM-1042", captured["body"]["input"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
