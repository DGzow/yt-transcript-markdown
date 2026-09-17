import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class PlaylistTests(unittest.TestCase):
    def test_identifies_playlist_urls(self):
        self.assertTrue(app.is_playlist_url("https://www.youtube.com/playlist?list=PL123"))
        self.assertTrue(
            app.is_playlist_url(
                "https://www.youtube.com/watch?v=abcdefghijk&list=PL123"
            )
        )
        self.assertFalse(
            app.is_playlist_url("https://www.youtube.com/watch?v=abcdefghijk")
        )

    def test_video_link_passes_through_without_ytdlp(self):
        result = app.expand_target("https://youtu.be/abcdefghijk")

        self.assertTrue(result["ok"])
        self.assertFalse(result["is_playlist"])
        self.assertIsNone(result["folder"])
        self.assertEqual(result["videos"][0]["video_id"], "abcdefghijk")

    @patch("app.subprocess.run")
    def test_playlist_is_expanded_and_deduplicated(self, run):
        payload = {
            "id": "PL_TEST_123",
            "title": "Minha Playlist: Teste?",
            "entries": [
                {"id": "abcdefghijk", "title": "Um"},
                {"id": "lmnopqrstuv", "title": "Dois"},
                {"id": "abcdefghijk", "title": "Repetido"},
                None,
            ],
        }
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(payload), stderr=""
        )

        result = app.expand_target(
            "https://www.youtube.com/playlist?list=PL_TEST_123"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["folder"], "minha-playlist-teste-pl-test-123")
        self.assertEqual(len(result["videos"]), 2)


class OutputTests(unittest.TestCase):
    @patch("app.core.fetch_via_api")
    @patch("app.core.fetch_metadata")
    def test_playlist_folder_cannot_escape_transcripts(self, metadata, fetch):
        metadata.return_value = {
            "title": "Vídeo Teste",
            "channel": "Canal",
            "channel_url": "",
        }
        fetch.return_value = (
            [{"start": 0.0, "duration": 1.0, "text": "Teste de transcrição."}],
            "pt",
            None,
        )

        with tempfile.TemporaryDirectory() as tmp:
            old_dir = app.TRANSCRIPTS_DIR
            app.TRANSCRIPTS_DIR = Path(tmp) / "transcripts"
            try:
                result = app.transcribe(
                    "abcdefghijk", ["pt"], True, folder="../../Minha Playlist?"
                )
            finally:
                app.TRANSCRIPTS_DIR = old_dir

            saved = Path(result["saved_path"]).resolve()
            root = (Path(tmp) / "transcripts").resolve()
            self.assertTrue(result["ok"])
            self.assertIn(root, saved.parents)
            self.assertEqual(result["saved_folder"], "minha-playlist")


if __name__ == "__main__":
    unittest.main()

