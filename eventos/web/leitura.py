"""O app atrás do nginx do oute-server: o que vem da internet só lê, e o HEAD vale como GET.

O nginx manda `X-Frentes-Publico: 1` quando a conexão chega fora da tailnet e `0` na tailnet,
sempre sobrescrevendo o que o cliente mandou. Com `1`, o app recusa (405) todo método que não
seja GET ou HEAD e as telas escondem o que escreve (relatar, endereçar, desfazer, revisar).
O nginx já corta o mesmo na borda; esta é a segunda trava, e quem vê o menu certo não esbarra
num 405. O cabeçalho só diz "público": ninguém ganha acesso por ele, só perde.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CABECALHO = b"x-frentes-publico"
LEITURA = frozenset({"GET", "HEAD"})
CORPO_405 = b'{"detail":"Somente leitura fora da tailnet."}'


def somente_leitura(scope: Scope) -> bool:
    """Se o nginx marcou a requisição como vinda da internet."""
    return any(nome == CABECALHO and valor.strip() == b"1" for nome, valor in scope["headers"])


class Leitura:
    """Middleware ASGI: marca `request.state.somente_leitura`, recusa escrita e atende HEAD."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        metodo = scope["method"]
        publico = somente_leitura(scope)
        if publico and metodo not in LEITURA:
            await send(
                {
                    "type": "http.response.start",
                    "status": 405,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(CORPO_405)).encode()),
                        (b"allow", b"GET, HEAD"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": CORPO_405})
            return
        escopo = {**scope, "state": {**scope.get("state", {}), "somente_leitura": publico}}
        if metodo != "HEAD":
            await self.app(escopo, receive, send)
            return
        # As rotas só declaram GET: atende como GET e tira o corpo da resposta.
        escopo["method"] = "GET"

        async def sem_corpo(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.body":
                mensagem = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(mensagem)

        await self.app(escopo, receive, sem_corpo)
