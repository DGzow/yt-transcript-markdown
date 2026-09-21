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

    def test_already_transcribed_ids_are_found_in_any_subfolder(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "transcripts"
            (raiz / "minha-playlist").mkdir(parents=True)
            (raiz / "minha-playlist" / "um-titulo-abcdefghijk.md").write_text("x", encoding="utf-8")
            (raiz / "avulso-com-hifen--bcdefghijk.md").write_text("x", encoding="utf-8")
            (raiz / "README.md").write_text("x", encoding="utf-8")
            antigo = app.TRANSCRIPTS_DIR
            app.TRANSCRIPTS_DIR = raiz
            try:
                feitos = app.ids_ja_transcritos()
            finally:
                app.TRANSCRIPTS_DIR = antigo
        self.assertEqual(feitos, {"abcdefghijk", "-bcdefghijk"})  # ID que começa com "-" também

    def test_already_transcribed_is_empty_when_folder_missing(self):
        antigo = app.TRANSCRIPTS_DIR
        app.TRANSCRIPTS_DIR = Path(tempfile.gettempdir()) / "pasta-que-nao-existe-xyz"
        try:
            self.assertEqual(app.ids_ja_transcritos(), set())
        finally:
            app.TRANSCRIPTS_DIR = antigo

    def test_ytdlp_uses_node_when_available(self):
        # sem runtime JS o yt-dlp falha com "Requested format is not available"
        with patch("yt_transcript_md.shutil.which", return_value="C:/node.exe"):
            cmd = app.core.ytdlp_base_cmd()
        self.assertIn("--js-runtimes", cmd)
        self.assertEqual(cmd[cmd.index("--js-runtimes") + 1], "node")

    def test_ytdlp_omits_js_runtime_without_node(self):
        with patch("yt_transcript_md.shutil.which", return_value=None):
            cmd = app.core.ytdlp_base_cmd()
        self.assertIsNotNone(cmd)  # o módulo yt_dlp continua sendo achado
        self.assertNotIn("--js-runtimes", cmd)

    def test_watch_later_link_counts_as_playlist(self):
        # o cartão fixo "Assistir mais tarde" da interface usa este link
        self.assertIn("https://www.youtube.com/playlist?list=WL", app.carregar_pagina())
        self.assertTrue(app.is_playlist_url("https://www.youtube.com/playlist?list=WL"))

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

    @patch("app.subprocess.run")
    def test_playlist_ytdlp_error_is_translated(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="ERROR: Could not copy Chrome cookie database; DPAPI failed",
        )

        result = app.expand_target(
            "https://www.youtube.com/playlist?list=PL_TEST_123", cookies="brave"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Não consegui abrir a playlist.")
        self.assertIn("Chrome/Edge/Brave", result["detalhes"][0])

    @patch("app.subprocess.run")
    def test_public_playlist_retries_without_browser_cookies(self, run):
        cookie_failure = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="ERROR: DPAPI failed"
        )
        public_success = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "PL_TEST_123",
                    "title": "Playlist pública",
                    "entries": [{"id": "abcdefghijk", "title": "Um"}],
                }
            ),
            stderr="",
        )
        run.side_effect = [cookie_failure, public_success]

        result = app.expand_target(
            "https://www.youtube.com/playlist?list=PL_TEST_123", cookies="brave"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(run.call_count, 2)
        second_command = run.call_args_list[1].args[0]
        self.assertNotIn("--cookies-from-browser", second_command)


class OutputTests(unittest.TestCase):
    @patch("app.core.fetch_via_api")
    @patch("app.core.fetch_metadata")
    def test_video_without_playlist_goes_to_avulsos_subfolder(self, metadata, fetch):
        metadata.return_value = {"title": "Vídeo Solto", "channel": "Canal", "channel_url": ""}
        fetch.return_value = ([{"start": 0.0, "duration": 1.0, "text": "Texto."}], "pt", None)

        with tempfile.TemporaryDirectory() as tmp:
            antigo = app.TRANSCRIPTS_DIR
            app.TRANSCRIPTS_DIR = Path(tmp) / "transcripts"
            try:
                result = app.transcribe("abcdefghijk", ["pt"], True)  # sem folder
            finally:
                app.TRANSCRIPTS_DIR = antigo

            salvo = Path(result["saved_path"]).resolve()
            esperado = (Path(tmp) / "transcripts" / app.PASTA_AVULSOS).resolve()
            self.assertEqual(salvo.parent, esperado)
            self.assertEqual(result["saved_folder"], app.PASTA_AVULSOS)

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
