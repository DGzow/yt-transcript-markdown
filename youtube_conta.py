"""Conexão com a conta do YouTube (login Google) para listar as suas playlists.

Tudo que fala com o Google fica aqui, separado do app.py. O fluxo:

1. `entrar()` abre o navegador na tela de consentimento do Google. Você aprova e o
   Google devolve uma permissão (token) para um servidorzinho temporário que este
   módulo levanta só durante o login.
2. O token é salvo em `token.json`, ao lado do app. Nas próximas vezes não precisa
   entrar de novo: `_credenciais()` reaproveita e renova o token sozinho.
3. `listar_playlists()` usa esse token para pedir a lista à YouTube Data API.

A permissão pedida é SOMENTE LEITURA (`youtube.readonly`): o app não consegue
alterar nem apagar nada na sua conta.

As bibliotecas do Google são importadas dentro das funções, e não no topo do arquivo.
Assim o app continua abrindo mesmo sem elas instaladas (só o botão de login avisa).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ESCOPOS = ["https://www.googleapis.com/auth/youtube.readonly"]

PASTA = Path(__file__).parent
CLIENT_SECRET = PASTA / "client_secret.json"  # baixado do Google Cloud (identifica o app)
TOKEN = PASTA / "token.json"  # criado no login (identifica VOCÊ) — nunca versionar

# Quanto tempo esperar você aprovar no navegador antes de desistir.
TEMPO_LIMITE_LOGIN = 180


def bibliotecas_instaladas() -> bool:
    """True se as duas bibliotecas do Google estão disponíveis neste Python."""
    return all(
        importlib.util.find_spec(nome) is not None
        for nome in ("google_auth_oauthlib", "googleapiclient")
    )


def _credenciais():
    """Devolve as credenciais salvas (renovando se venceram) ou None se não há login válido."""
    if not TOKEN.exists():
        return None

    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        cred = Credentials.from_authorized_user_file(str(TOKEN), ESCOPOS)
    except (ValueError, OSError):
        return None  # token.json corrompido: trata como "não conectado"

    if cred.valid:
        return cred

    if cred.expired and cred.refresh_token:
        try:
            cred.refresh(Request())
        except RefreshError:
            # Token revogado, ou vencido pelos 7 dias do modo Teste do Google Cloud.
            TOKEN.unlink(missing_ok=True)
            return None
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
        return cred

    return None


def status() -> dict:
    """Estado da conexão, para a interface decidir o que mostrar."""
    if not bibliotecas_instaladas():
        return {"estado": "sem_bibliotecas"}
    if not CLIENT_SECRET.exists():
        return {"estado": "sem_client_secret"}
    if _credenciais() is None:
        return {"estado": "desconectado"}
    return {"estado": "conectado"}


def entrar() -> None:
    """Abre o login do Google no navegador e guarda o token. Bloqueia até você aprovar."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    fluxo = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), ESCOPOS)
    # port=0: o sistema escolhe uma porta livre para receber a resposta do Google.
    # prompt="consent": força o Google a entregar o "refresh token", o que permite
    # renovar o login sem pedir sua aprovação a cada hora.
    cred = fluxo.run_local_server(
        port=0,
        prompt="consent",
        authorization_prompt_message="",
        success_message="Login concluído. Pode fechar esta aba e voltar ao app.",
        timeout_seconds=TEMPO_LIMITE_LOGIN,
    )
    TOKEN.write_text(cred.to_json(), encoding="utf-8")


def sair() -> None:
    """Esquece o login: apaga o token local. Serve também para trocar de conta."""
    TOKEN.unlink(missing_ok=True)


def listar_playlists() -> list[dict]:
    """Playlists da conta conectada: [{id, titulo, videos, url}, ...].

    Levanta PermissionError se não houver login válido.
    """
    cred = _credenciais()
    if cred is None:
        raise PermissionError("Entre com o Google primeiro.")

    from googleapiclient.discovery import build

    # cache_discovery=False evita um aviso e um arquivo de cache desnecessário.
    servico = build("youtube", "v3", credentials=cred, cache_discovery=False)

    playlists: list[dict] = []
    pagina = None
    while True:
        # A API entrega no máximo 50 itens por chamada; `nextPageToken` aponta a próxima página.
        resposta = servico.playlists().list(
            part="snippet,contentDetails", mine=True, maxResults=50, pageToken=pagina
        ).execute()
        for item in resposta.get("items", []):
            playlists.append(
                {
                    "id": item["id"],
                    "titulo": item["snippet"]["title"],
                    "videos": item["contentDetails"]["itemCount"],
                    "url": f"https://www.youtube.com/playlist?list={item['id']}",
                }
            )
        pagina = resposta.get("nextPageToken")
        if not pagina:
            return playlists
