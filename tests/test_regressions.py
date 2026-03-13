import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

if "arq" not in sys.modules:
    sys.modules["arq"] = SimpleNamespace(ArqRedis=object)

from app.routes.generate import GenerateOptions, GenerateRequest, generate
from app.services import narration


class GenerateRouteRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_instagram_request_does_not_queue_google_voice_when_omitted(self) -> None:
        create_job_mock = AsyncMock(return_value="job-123")
        redis = SimpleNamespace(enqueue_job=AsyncMock())
        body = GenerateRequest(
            type="instagram",
            content="<p>Story</p>",
            options=GenerateOptions(),
        )

        with (
            patch("app.routes.generate.create_job", create_job_mock),
            patch("app.routes.generate.get_redis", return_value=redis),
        ):
            response = await generate(body, _="secret")

        self.assertEqual(response.job_id, "job-123")
        self.assertEqual(create_job_mock.await_args.kwargs["options"], {})
        redis.enqueue_job.assert_awaited_once_with("run_job", "job-123")


class NarrationRegressionTests(unittest.TestCase):
    def test_openai_narration_prompt_includes_requested_word_limit(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Narration script"))]
        )
        create_mock = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        fake_settings = SimpleNamespace(openai_api_key="sk-test")

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("app.services.narration.get_settings", return_value=fake_settings),
        ):
            result = narration._script_openai("Article body", "en", 123)

        self.assertEqual(result, "Narration script")
        system_prompt = create_mock.call_args.kwargs["messages"][0]["content"]
        self.assertIn("123 words maximum", system_prompt)


if __name__ == "__main__":
    unittest.main()
