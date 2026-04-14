import sys
import types as types_std
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

if "arq" not in sys.modules:
    arq_module = types_std.ModuleType("arq")
    arq_module.ArqRedis = object
    arq_connections = types_std.ModuleType("arq.connections")
    arq_connections.RedisSettings = SimpleNamespace(from_dsn=lambda _dsn: None)
    sys.modules["arq"] = arq_module
    sys.modules["arq.connections"] = arq_connections

from app.routes.generate import GenerateOptions, GenerateRequest, generate
from app import worker
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
        fake_settings = SimpleNamespace(openai_api_key="sk-test", openai_llm_model="oai-llm-test")

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
        self.assertEqual(create_mock.call_args.kwargs["model"], "oai-llm-test")


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
        fake_settings = SimpleNamespace(openai_api_key="sk-test", openai_llm_model="oai-llm-test")

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
        self.assertEqual(create_mock.call_args.kwargs["model"], "oai-llm-test")


class PodcastDialogInstructionsTests(unittest.TestCase):
    def test_openai_dialog_appends_instructions_to_system_prompt(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Host: Hi.\nGuest: Hey."))],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=2,
                total_tokens=3,
            ),
        )
        create_mock = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        fake_settings = SimpleNamespace(openai_api_key="sk-test", openai_llm_model="oai-llm-test")

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("app.services.podcast.get_settings", return_value=fake_settings),
        ):
            transcript, usage = podcast._dialog_openai(
                "Article body",
                "en",
                400,
                "educational",
                instructions="Host is Alex. Guest is Sam.",
            )

        self.assertEqual(transcript, "Host: Hi.\nGuest: Hey.")
        self.assertEqual(usage["total_tokens"], 3)
        system_prompt = create_mock.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Additional instructions:", system_prompt)
        self.assertIn("Host is Alex. Guest is Sam.", system_prompt)

    def test_openai_dialog_omits_additional_block_when_instructions_none(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Host: X."))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        create_mock = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        fake_settings = SimpleNamespace(openai_api_key="sk-test", openai_llm_model="oai-llm-test")

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("app.services.podcast.get_settings", return_value=fake_settings),
        ):
            podcast._dialog_openai("Body", "en", 100, "fast", instructions=None)

        system_prompt = create_mock.call_args.kwargs["messages"][0]["content"]
        self.assertNotIn("Additional instructions:", system_prompt)

    def test_google_dialog_appends_instructions_before_article(self) -> None:
        r = SimpleNamespace(
            text="Host: A.\nGuest: B.",
            usage_metadata=SimpleNamespace(
                prompt_token_count=10,
                candidates_token_count=5,
                total_token_count=15,
            ),
        )
        generate_mock = Mock(return_value=r)
        client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_mock))
        genai_mod = types_std.ModuleType("google.genai")
        genai_mod.Client = Mock(return_value=client)
        genai_types = MagicMock()
        genai_types.GenerateContentConfig = MagicMock(return_value="cfg")
        genai_types.ThinkingConfig = MagicMock(return_value="think")
        genai_mod.types = genai_types
        google_pkg = types_std.ModuleType("google")
        google_pkg.genai = genai_mod
        fake_settings = SimpleNamespace(google_api_key="g-test", google_llm_model="google-llm-test")

        mods = {"google": google_pkg, "google.genai": genai_mod}
        with (
            patch.dict(sys.modules, mods),
            patch("app.services.podcast.get_settings", return_value=fake_settings),
        ):
            transcript, usage = podcast._dialog_google(
                "Art text",
                "en",
                200,
                "calm",
                instructions="Use names from the briefing.",
            )

        self.assertEqual(transcript, "Host: A.\nGuest: B.")
        self.assertEqual(usage["total_tokens"], 15)
        prompt = generate_mock.call_args.kwargs["contents"]
        self.assertIn("Additional instructions:", prompt)
        self.assertIn("Use names from the briefing.", prompt)
        self.assertIn(
            "Use names from the briefing.\n\nArticle:\n\nArt text",
            prompt,
        )
        self.assertEqual(generate_mock.call_args.kwargs["model"], "google-llm-test")

    def test_openai_dialog_uses_expanded_max_tokens_formula(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Host: Hi.\nGuest: Hey."))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
        create_mock = Mock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create_mock))
        )
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value=client))
        fake_settings = SimpleNamespace(openai_api_key="sk-test", openai_llm_model="oai-llm-test")

        with (
            patch.dict(sys.modules, {"openai": fake_openai}),
            patch("app.services.podcast.get_settings", return_value=fake_settings),
        ):
            podcast._dialog_openai("Article body", "en", 600, "educational")

        self.assertEqual(create_mock.call_args.kwargs["max_tokens"], 1800)


class GenerateOptionsSchemaRegressionTests(unittest.TestCase):
    def test_word_count_default_is_600(self) -> None:
        self.assertEqual(GenerateOptions().word_count, 600)

    def test_word_count_accepts_4000_and_rejects_4001(self) -> None:
        self.assertEqual(GenerateOptions(word_count=4000).word_count, 4000)
        with self.assertRaises(Exception):
            GenerateOptions(word_count=4001)


class WorkerDefaultsRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_podcast_worker_default_word_count_is_600(self) -> None:
        podcast_job = {
            "job_id": "job-podcast",
            "status": "queued",
            "type": "podcast",
            "content": "<p>Hello</p>",
            "options": {},
            "webhook_url": None,
        }
        podcast_mock = AsyncMock(return_value=("/tmp/podcast.mp3", {}))

        with (
            patch("app.worker.get_job", AsyncMock(return_value=podcast_job)),
            patch("app.worker.update_job", AsyncMock()),
            patch("app.worker.podcast.generate_podcast_audio", podcast_mock),
            patch("app.worker.upload_audio", Mock(return_value="https://example.com/podcast.mp3")),
            patch("app.worker._duration", Mock(return_value=12.3)),
        ):
            await worker.run_job({}, "job-podcast")

        self.assertEqual(podcast_mock.await_args.kwargs["word_count"], 600)
        self.assertIsNone(podcast_mock.await_args.kwargs["google_tts_model"])

    async def test_narration_worker_default_word_count_remains_400(self) -> None:
        narration_job = {
            "job_id": "job-narration",
            "status": "queued",
            "type": "narration",
            "content": "<p>Hello</p>",
            "options": {},
            "webhook_url": None,
        }
        narration_mock = AsyncMock(return_value=("/tmp/narration.mp3", {}))

        with (
            patch("app.worker.get_job", AsyncMock(return_value=narration_job)),
            patch("app.worker.update_job", AsyncMock()),
            patch("app.worker.narration.generate_narration_audio", narration_mock),
            patch("app.worker.upload_audio", Mock(return_value="https://example.com/narration.mp3")),
            patch("app.worker._duration", Mock(return_value=12.3)),
        ):
            await worker.run_job({}, "job-narration")

        self.assertEqual(narration_mock.await_args.kwargs["word_count"], 400)
        self.assertIsNone(narration_mock.await_args.kwargs["google_tts_model"])

    async def test_worker_passes_google_tts_model_override_when_provided(self) -> None:
        instagram_job = {
            "job_id": "job-instagram",
            "status": "queued",
            "type": "instagram",
            "content": "<p>Hello</p>",
            "options": {"google_tts_model": "google-tts-override"},
            "webhook_url": None,
        }
        instagram_mock = AsyncMock(return_value=("/tmp/instagram.mp3", {}))

        with (
            patch("app.worker.get_job", AsyncMock(return_value=instagram_job)),
            patch("app.worker.update_job", AsyncMock()),
            patch("app.worker.instagram.generate_instagram_audio", instagram_mock),
            patch("app.worker.upload_audio", Mock(return_value="https://example.com/instagram.mp3")),
            patch("app.worker._duration", Mock(return_value=12.3)),
        ):
            await worker.run_job({}, "job-instagram")

        self.assertEqual(
            instagram_mock.await_args.kwargs["google_tts_model"],
            "google-tts-override",
        )


class PodcastTtsPauseRegressionTests(unittest.TestCase):
    def test_openai_tts_source_includes_200ms_pause(self) -> None:
        import inspect

        source = inspect.getsource(podcast._tts_openai_turns)
        self.assertIn("AudioSegment.silent(duration=200)", source)
        self.assertIn("combined = combined + pause + seg", source)


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
