import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

if "arq" not in sys.modules:
    sys.modules["arq"] = SimpleNamespace(ArqRedis=object)

from app.routes.generate import GenerateOptions, GenerateRequest, generate
from app.services import instagram, narration, podcast


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
            choices=[SimpleNamespace(message=SimpleNamespace(content="Narration script"))],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
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
            script, usage = narration._script_openai("Article body", "en", 123)

        self.assertEqual(script, "Narration script")
        self.assertEqual(
            usage,
            {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        )
        system_prompt = create_mock.call_args.kwargs["messages"][0]["content"]
        self.assertIn("123 words maximum", system_prompt)


class InstagramRegressionTests(unittest.TestCase):
    def test_openai_instagram_script_handles_missing_usage(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hook text"))],
            usage=None,
        )
        create_mock = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        fake_settings = SimpleNamespace(openai_api_key="sk-test")

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("app.services.instagram.get_settings", return_value=fake_settings),
        ):
            script, usage = instagram._script_openai("Article body", "en")

        self.assertEqual(script, "Hook text")
        self.assertEqual(
            usage,
            {
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            },
        )


class PodcastChunkTranscriptTests(unittest.TestCase):
    def test_malformed_transcript_raises_no_turns(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            podcast._chunk_transcript("No Host or Guest labels here.")
        self.assertIn("No dialogue turns found", str(ctx.exception))

    def test_valid_transcript_returns_chunks(self) -> None:
        t = "Host: One.\nGuest: Two."
        self.assertEqual(podcast._chunk_transcript(t), [t])


if __name__ == "__main__":
    unittest.main()
