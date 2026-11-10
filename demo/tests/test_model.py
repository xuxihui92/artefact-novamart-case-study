"""Unit tests for the Chat Completions client and provider settings."""
import json
from email.message import EmailMessage
from io import BytesIO
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from return_desk.config import DEFAULT_MODEL, GEMINI_BASE_URL, GEMINI_DEFAULT_MODEL, OPENAI_BASE_URL
from return_desk.model import (
    OpenAIClient,
    _has_phrase,
    answer_is_grounded,
    chat_completions_url,
    model_route,
    resolve_settings,
)
from return_desk.tools import tool_specs


def http_error(code, retry_after=None):
    headers = EmailMessage()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPError(
        "https://example.test/chat/completions",
        code,
        "error",
        headers,
        BytesIO(b""),
    )


def tool_payload(name, arguments="{}"):
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_test",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                }
            }
        ]
    }


class TestModelRoute(unittest.TestCase):
    def test_returns_selected_tool(self):
        payload = tool_payload("find_policy")
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("return_desk.model.urlopen", return_value=response), patch(
            "return_desk.model.json.load", return_value=payload
        ):
            self.assertEqual(model_route("key", "gpt-4.1-mini", "Where is my refund sent?"), "find_policy")

    def test_failure_returns_none(self):
        with patch("return_desk.model.urlopen", side_effect=OSError("down")):
            self.assertIsNone(model_route("key", "gpt-4.1-mini", "hello"))

    def test_rejects_unknown_tool_name(self):
        payload = tool_payload("delete_order")
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("return_desk.model.urlopen", return_value=response), patch(
            "return_desk.model.json.load", return_value=payload
        ):
            self.assertIsNone(model_route("key", "gpt-4.1-mini", "hello"))

    def test_redacts_order_ids_in_request_body(self):
        captured = {}

        def fake_urlopen(request, timeout=30):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode())
            raise OSError("stop after capture")

        with patch("return_desk.model.urlopen", side_effect=fake_urlopen):
            model_route("key", "gpt-4.1-mini", "Can I return NM-1042?")
        users = [item["content"] for item in captured["body"]["messages"] if item["role"] == "user"]
        self.assertEqual(users, ["Can I return <demo order reference>?"])
        self.assertNotIn("NM-1042", json.dumps(captured["body"]))
        self.assertNotIn("input", captured["body"])
        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        names = [tool["function"]["name"] for tool in captured["body"]["tools"]]
        self.assertEqual(
            names,
            ["search_policy", "lookup_order", "report_item_condition", "handoff"],
        )

    def test_tool_schema_has_real_parameters(self):
        by_name = {tool["function"]["name"]: tool["function"] for tool in tool_specs()}
        self.assertIn("query", by_name["search_policy"]["parameters"]["properties"])
        self.assertIn("order_id", by_name["lookup_order"]["parameters"]["properties"])
        self.assertIn("purpose", by_name["lookup_order"]["parameters"]["properties"])
        self.assertIn("opened", by_name["report_item_condition"]["parameters"]["properties"])
        self.assertIn("used", by_name["report_item_condition"]["parameters"]["properties"])
        self.assertIn("resalable", by_name["report_item_condition"]["parameters"]["properties"])
        self.assertIn("reason", by_name["handoff"]["parameters"]["properties"])
        for function in by_name.values():
            self.assertNotIn("strict", function)
            self.assertTrue(function["parameters"]["properties"])

    def test_arguments_may_already_be_objects(self):
        payload = tool_payload("lookup_order", arguments={"purpose": "order_status"})
        # tool_payload JSON-encodes only when the test builds a string. Pass the dict through.
        payload["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = {
            "purpose": "order_status"
        }
        response = MagicMock()
        response.__enter__.return_value = response
        with patch("return_desk.model.urlopen", return_value=response), patch(
            "return_desk.model.json.load", return_value=payload
        ):
            self.assertEqual(model_route("key", "gpt-4.1-mini", "Where is NM-1045?"), "lookup_status")


class TestStatusPhrases(unittest.TestCase):
    def test_single_word_status_is_caught(self):
        self.assertTrue(_has_phrase("that order was delivered.", "delivered"))
        self.assertTrue(_has_phrase("the item was collected yesterday", "collected"))
        self.assertFalse(_has_phrase("uncollected orders may be canceled", "collected"))
        self.assertTrue(_has_phrase("it is ready for pickup now", "ready for pickup"))
        self.assertFalse(
            answer_is_grounded("That order was delivered.", "handoff", [], order_visible=False)
        )
        self.assertFalse(
            answer_is_grounded("The carrier shipped it.", "handoff", [], order_visible=False)
        )
        self.assertTrue(
            answer_is_grounded(
                "I can't show an order result for this store.",
                "handoff",
                [],
                order_visible=False,
            )
        )


class TestRetries(unittest.TestCase):
    def _client(self, sleeps):
        return OpenAIClient(
            "key",
            "gemini-3.5-flash",
            base_url=GEMINI_BASE_URL,
            min_interval=0,
            sleeper=sleeps.append,
            provider="gemini",
        )

    def test_retries_429_and_503_then_reads_the_tool_call(self):
        sleeps = []
        calls = {"n": 0}

        def fake_urlopen(request, timeout=30):
            calls["n"] += 1
            if calls["n"] == 1:
                raise http_error(429)
            if calls["n"] == 2:
                raise http_error(503, retry_after="5")
            response = MagicMock()
            response.__enter__.return_value = response
            return response

        payload = tool_payload("handoff", '{"reason":"not a store question"}')
        with patch("return_desk.model.urlopen", side_effect=fake_urlopen), patch(
            "return_desk.model.json.load", return_value=payload
        ):
            proposal = self._client(sleeps).propose("Is the cafeteria open?")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleeps, [1.0, 5.0])
        self.assertEqual(proposal["name"], "handoff")

    def test_other_http_errors_do_not_retry(self):
        sleeps = []
        calls = {"n": 0}

        def fake_urlopen(request, timeout=30):
            calls["n"] += 1
            raise http_error(400)

        with patch("return_desk.model.urlopen", side_effect=fake_urlopen):
            self.assertIsNone(self._client(sleeps).propose("hello"))
        self.assertEqual(calls["n"], 1)
        self.assertEqual(sleeps, [])


class TestGeminiFollowUp(unittest.TestCase):
    def test_follow_up_keeps_thought_signature_on_message_and_tool_call(self):
        assistant = {
            "role": "assistant",
            "content": None,
            "extra_content": {"google": {"thought_signature": "sig-message"}},
            "tool_calls": [
                {
                    "id": "call_gemini",
                    "type": "function",
                    "extra_content": {"google": {"thought_signature": "sig-call"}},
                    "function": {
                        "name": "lookup_order",
                        "arguments": '{"purpose": "order_status"}',
                    },
                }
            ],
        }
        first = {"choices": [{"message": assistant}]}
        second = {"choices": [{"message": {"role": "assistant", "content": "No. I cannot confirm that order."}}]}
        seen = []

        def fake_urlopen(request, timeout=30):
            seen.append(json.loads(request.data.decode()))
            response = MagicMock()
            response.__enter__.return_value = response
            return response

        client = OpenAIClient(
            "gemini-key",
            GEMINI_DEFAULT_MODEL,
            base_url=GEMINI_BASE_URL,
            min_interval=0,
            provider="gemini",
        )
        with patch("return_desk.model.urlopen", side_effect=fake_urlopen), patch(
            "return_desk.model.json.load", side_effect=[first, second]
        ):
            proposal = client.propose("Status for NM-2042? Email jane@example.com card 4111111111111111")
            text = client.complete(
                proposal["messages"],
                proposal["assistant_message"],
                "decision: handoff\nEmail jane@example.com about NM-2042",
            )
        self.assertEqual(text, "No. I cannot confirm that order.")
        self.assertEqual(len(seen), 2)
        self.assertNotIn("NM-2042", json.dumps(seen))
        self.assertNotIn("jane@example.com", json.dumps(seen))
        self.assertNotIn("4111111111111111", json.dumps(seen))
        follow = seen[1]["messages"]
        self.assertEqual([item["role"] for item in follow], ["system", "user", "assistant", "tool"])
        self.assertEqual(follow[2], assistant)
        self.assertEqual(follow[2]["extra_content"]["google"]["thought_signature"], "sig-message")
        self.assertEqual(
            follow[2]["tool_calls"][0]["extra_content"]["google"]["thought_signature"],
            "sig-call",
        )
        self.assertEqual(seen[1]["tool_choice"], "none")
        self.assertEqual(follow[3]["role"], "tool")
        self.assertEqual(follow[3]["tool_call_id"], "call_gemini")
        self.assertIn("<email>", follow[3]["content"])
        self.assertIn("<demo order reference>", follow[3]["content"])

    def test_missing_tool_call_id_is_filled_without_dropping_extra_content(self):
        assistant = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "extra_content": {"google": {"thought_signature": "sig-call"}},
                    "function": {"name": "search_policy", "arguments": '{"query": "refund method"}'},
                }
            ],
        }
        seen = []

        def fake_urlopen(request, timeout=30):
            seen.append(json.loads(request.data.decode()))
            response = MagicMock()
            response.__enter__.return_value = response
            return response

        client = OpenAIClient("key", "gpt-4.1-mini", min_interval=0)
        with patch("return_desk.model.urlopen", side_effect=fake_urlopen), patch(
            "return_desk.model.json.load",
            return_value={"choices": [{"message": {"role": "assistant", "content": "No."}}]},
        ):
            client.complete(
                [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
                assistant,
                "decision: no",
            )
        follow = seen[0]["messages"]
        self.assertEqual(follow[2]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(
            follow[2]["tool_calls"][0]["extra_content"]["google"]["thought_signature"],
            "sig-call",
        )
        self.assertEqual(follow[3]["tool_call_id"], "call_1")
        self.assertEqual(assistant["tool_calls"][0].get("extra_content")["google"]["thought_signature"], "sig-call")


class TestProviderSettings(unittest.TestCase):
    def test_openai_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = resolve_settings("openai")
        self.assertEqual(settings["provider"], "openai")
        self.assertEqual(settings["model"], DEFAULT_MODEL)
        self.assertEqual(settings["model"], "gpt-4.1-mini")
        self.assertEqual(settings["base_url"], OPENAI_BASE_URL)
        self.assertEqual(settings["api_key"], "")

    def test_gemini_default_model_ignores_openai_model(self):
        with patch.dict(
            "os.environ",
            {"OPENAI_MODEL": "gpt-4.1-mini", "GEMINI_API_KEY": "gemini-key", "OPENAI_API_KEY": "openai-key"},
            clear=True,
        ):
            settings = resolve_settings("gemini")
        self.assertEqual(settings["provider"], "gemini")
        self.assertEqual(settings["model"], GEMINI_DEFAULT_MODEL)
        self.assertEqual(settings["model"], "gemini-3.5-flash")
        self.assertTrue(settings["base_url"].startswith("https://generativelanguage.googleapis.com/v1beta/openai"))
        self.assertEqual(settings["api_key"], "gemini-key")

    def test_gemini_model_is_overridable(self):
        with patch.dict("os.environ", {"GEMINI_MODEL": "gemini-3.5-flash-lite"}, clear=True):
            self.assertEqual(resolve_settings("gemini")["model"], "gemini-3.5-flash-lite")

    def test_provider_env_and_endpoint_join(self):
        with patch.dict("os.environ", {"PROVIDER": "gemini"}, clear=True):
            self.assertEqual(resolve_settings(None)["provider"], "gemini")
        self.assertEqual(
            chat_completions_url("https://api.openai.com/v1"),
            "https://api.openai.com/v1/chat/completions",
        )
        self.assertEqual(
            chat_completions_url("https://generativelanguage.googleapis.com/v1beta/openai/"),
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        )
        self.assertEqual(
            chat_completions_url("https://example.test/v1/chat/completions"),
            "https://example.test/v1/chat/completions",
        )
        with self.assertRaises(ValueError):
            resolve_settings("anthropic")
        with self.assertRaises(ValueError):
            OpenAIClient("key", "gpt-4.1-mini", base_url="file:///tmp/nope")


if __name__ == "__main__":
    unittest.main(verbosity=2)
