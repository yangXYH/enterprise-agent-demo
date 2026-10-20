import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils import ecom_knowledge_service as service
from utils import operating_analysis_ai


class _CompletionStub:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            async def chunks():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="好"))])
            return chunks()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="好"))])


class KnowledgeModelRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_operating_client_wins_over_generic_llm_for_both_response_modes(self):
        completions = _CompletionStub()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        env = {
            "OPERATING_AI_KEY": "working-operating-key",
            "OPERATING_AI_MODEL": "working-operating-model",
            "LLM_API_KEY": "other-account-key",
            "LLM_BASE_URL": "https://example.invalid",
            "LLM_MODEL": "other-account-model",
        }
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"), patch.object(
            operating_analysis_ai, "_client", return_value=client
        ) as operating_client, patch("openai.AsyncOpenAI") as generic_client:
            answer = await service._qa_chat([{"role": "user", "content": "你好"}])
            stream = await service._qa_chat([{"role": "user", "content": "你好"}], stream=True)
            streamed = [part async for part in stream]
            displayed_model = service._get_active_llm_model()

        self.assertEqual(answer, "好")
        self.assertEqual(streamed, ["好"])
        self.assertEqual(displayed_model, "working-operating-model")
        self.assertEqual([call["model"] for call in completions.calls], ["working-operating-model"] * 2)
        self.assertEqual(operating_client.call_count, 2)
        generic_client.assert_not_called()

    async def test_generic_client_remains_available_without_operating_key(self):
        completions = _CompletionStub()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        env = {
            "LLM_API_KEY": "standalone-key",
            "LLM_BASE_URL": "https://example.invalid",
            "LLM_MODEL": "standalone-model",
        }
        with patch.dict(os.environ, env, clear=True), patch("dotenv.load_dotenv"), patch.object(
            operating_analysis_ai, "_client"
        ) as operating_client, patch("openai.AsyncOpenAI", return_value=client) as generic_client:
            answer = await service._qa_chat([{"role": "user", "content": "你好"}])
            displayed_model = service._get_active_llm_model()

        self.assertEqual(answer, "好")
        self.assertEqual(displayed_model, "standalone-model")
        self.assertEqual(completions.calls[0]["model"], "standalone-model")
        self.assertEqual(generic_client.call_args.kwargs["api_key"], "standalone-key")
        self.assertEqual(generic_client.call_args.kwargs["base_url"], "https://example.invalid")
        operating_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
