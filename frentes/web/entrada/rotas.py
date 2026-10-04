"""`POST /frentes`: a porta única de entrada, do webhook e do formulário de relato."""

from contextlib import closing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator

from frentes import contratos, store
from frentes.entrada import recepcao

roteador = APIRouter()


class CorpoDaFrente(BaseModel):
    """O corpo do POST. A origem é `webhook`, salvo o formulário, que manda `relato`."""

    model_config = ConfigDict(extra="ignore")

    texto: str
    emissor: str = recepcao.EMISSOR_PADRAO
    origem: contratos.Origem = contratos.Origem.WEBHOOK
    ocorrido_em: AwareDatetime | None = None
    ref_externa: str | None = None
    metadados: dict[str, Any] = {}

    @field_validator("texto")
    @classmethod
    def _texto_nao_vazio(cls, texto: str) -> str:
        if not texto.strip():
            raise ValueError("texto é obrigatório")
        return texto  # o original nunca é alterado

    @field_validator("origem")
    @classmethod
    def _origem_ao_vivo(cls, origem: contratos.Origem) -> contratos.Origem:
        if origem not in recepcao.ORIGENS_AO_VIVO:
            raise ValueError("origem aceita: relato ou webhook")
        return origem


def _autenticar(
    request: Request,
    x_webhook_token: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Roda antes da validação do corpo: token errado é 401 mesmo com corpo inválido."""
    recebido = x_webhook_token
    if not recebido and authorization and authorization.lower().startswith("bearer "):
        recebido = authorization[7:].strip()
    if not recepcao.token_confere(request.app.state.config.webhook_token, recebido):
        raise HTTPException(status_code=401, detail="token inválido ou ausente")


@roteador.post("/frentes", status_code=202, dependencies=[Depends(_autenticar)])
def receber_frente(request: Request, corpo: CorpoDaFrente) -> dict[str, str]:
    bruta = contratos.FrenteBruta(
        emissor=corpo.emissor,
        texto=corpo.texto,
        ocorrido_em=corpo.ocorrido_em,
        ref_externa=corpo.ref_externa,
        metadados=corpo.metadados,
    )
    with closing(store.abrir(request.app.state.config.banco)) as con:
        gravada = recepcao.receber(con, bruta, corpo.origem)
    return {"id": gravada.id}
