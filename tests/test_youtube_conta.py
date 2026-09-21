import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import youtube_conta as conta


class StatusTests(unittest.TestCase):
    """O estado da conexão decide o que a interface mostra."""

    @patch("youtube_conta.bibliotecas_instaladas", return_value=False)
    def test_sem_bibliotecas(self, _):
        self.assertEqual(conta.status()["estado"], "sem_bibliotecas")

    @patch("youtube_conta.bibliotecas_instaladas", return_value=True)
    def test_sem_client_secret(self, _):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            conta, "CLIENT_SECRET", Path(tmp) / "nao-existe.json"
        ):
            self.assertEqual(conta.status()["estado"], "sem_client_secret")

    @patch("youtube_conta._credenciais", return_value=None)
    @patch("youtube_conta.bibliotecas_instaladas", return_value=True)
    def test_desconectado_quando_nao_ha_login(self, *_):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            with patch.object(conta, "CLIENT_SECRET", secret):
                self.assertEqual(conta.status()["estado"], "desconectado")

    @patch("youtube_conta._credenciais", return_value=object())
    @patch("youtube_conta.bibliotecas_instaladas", return_value=True)
    def test_conectado_quando_ha_credencial(self, *_):
        with tempfile.TemporaryDirectory() as tmp:
            secret = Path(tmp) / "client_secret.json"
            secret.write_text("{}", encoding="utf-8")
            with patch.object(conta, "CLIENT_SECRET", secret):
                self.assertEqual(conta.status()["estado"], "conectado")


class TokenTests(unittest.TestCase):
    def test_sem_token_nao_ha_credencial(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            conta, "TOKEN", Path(tmp) / "token.json"
        ):
            self.assertIsNone(conta._credenciais())

    def test_token_corrompido_vira_desconectado(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text("isso não é json", encoding="utf-8")
            with patch.object(conta, "TOKEN", token):
                self.assertIsNone(conta._credenciais())

    def test_sair_apaga_o_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = Path(tmp) / "token.json"
            token.write_text("{}", encoding="utf-8")
            with patch.object(conta, "TOKEN", token):
                conta.sair()
                self.assertFalse(token.exists())
                conta.sair()  # sair de novo, sem token, não pode dar erro


class ListarPlaylistsTests(unittest.TestCase):
    @patch("youtube_conta._credenciais", return_value=None)
    def test_sem_login_levanta_permissao(self, _):
        with self.assertRaises(PermissionError):
            conta.listar_playlists()

    @patch("googleapiclient.discovery.build")
    @patch("youtube_conta._credenciais", return_value=object())
    def test_junta_todas_as_paginas(self, _cred, build):
        pagina1 = {
            "items": [
                {"id": "PL1", "snippet": {"title": "Primeira"}, "contentDetails": {"itemCount": 3}},
            ],
            "nextPageToken": "PROXIMA",
        }
        pagina2 = {
            "items": [
                {"id": "PL2", "snippet": {"title": "Segunda"}, "contentDetails": {"itemCount": 1}},
            ],
        }
        lista = build.return_value.playlists.return_value.list
        lista.return_value.execute.side_effect = [pagina1, pagina2]

        resultado = conta.listar_playlists()

        self.assertEqual([p["id"] for p in resultado], ["PL1", "PL2"])
        self.assertEqual(resultado[0]["videos"], 3)
        self.assertEqual(resultado[1]["url"], "https://www.youtube.com/playlist?list=PL2")
        # a segunda chamada precisa ter pedido a página seguinte
        self.assertEqual(lista.call_args_list[1].kwargs["pageToken"], "PROXIMA")


if __name__ == "__main__":
    unittest.main()
