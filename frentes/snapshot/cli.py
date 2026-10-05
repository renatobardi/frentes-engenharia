"""`python -m frentes snapshot gravar | carregar`."""

import sys
from pathlib import Path

from frentes import config, store
from frentes.snapshot import arquivo

USO = "uso: python -m frentes snapshot gravar [--saida CAMINHO] | carregar [--de CAMINHO]"


def _caminho(argumentos: list[str], opcao: str) -> Path:
    """O caminho dado em `opcao`, ou o padrão. Levanta ValueError se o argumento é inválido."""
    if not argumentos:
        return arquivo.CAMINHO_PADRAO  # lido agora, para o teste poder trocá-lo
    if len(argumentos) == 2 and argumentos[0] == opcao:
        return Path(argumentos[1])
    raise ValueError(f"argumento não esperado: {' '.join(argumentos)}")


def snapshot(argumentos: list[str]) -> int:
    if not argumentos or argumentos[0] not in ("gravar", "carregar"):
        print(USO, file=sys.stderr)
        return 2
    acao, resto = argumentos[0], argumentos[1:]
    try:
        caminho = _caminho(resto, "--saida" if acao == "gravar" else "--de")
    except ValueError as erro:
        print(f"snapshot {acao}: {erro}\n{USO}", file=sys.stderr)
        return 2
    cfg = config.carregar()
    try:
        if acao == "gravar":
            gravado = arquivo.gravar(cfg, caminho)
            print(
                f"snapshot gravado em {caminho}: dia D {gravado.dia_d}, "
                f"{gravado.tamanho_bytes / 1024 / 1024:.1f} MB"
            )
            if gravado.commit == config.COMMIT_DESCONHECIDO:
                print(
                    "aviso: FRENTES_COMMIT não está definido: o snapshot leva o commit "
                    f"{gravado.commit!r} no snapshot_meta",
                    file=sys.stderr,
                )
            if gravado.tamanho_bytes > arquivo.LIMITE_DO_REPO_BYTES:
                print(
                    "aviso: passou de 50 MB compactado: pela spec (09-snapshot) o snapshot "
                    "passa a anexo de release",
                    file=sys.stderr,
                )
        else:
            carregado = arquivo.carregar(cfg.banco, caminho)
            print(
                f"snapshot carregado em {cfg.banco}: dia D {carregado.dia_d} "
                f"deslocado {carregado.deslocamento_dias} dias (vira ontem)"
            )
    except store.BancoAusente as erro:
        print(f"snapshot {acao}: {erro}", file=sys.stderr)
        return 1
    except (
        arquivo.SnapshotRecusado,
        arquivo.SnapshotAusente,
        arquivo.SnapshotInvalido,
        arquivo.BancoNaoTrocavel,
        OSError,
    ) as erro:
        print(f"snapshot {acao}: {erro}", file=sys.stderr)
        return 1
    return 0


COMANDOS = {"snapshot": ("snapshot gravar | snapshot carregar", snapshot)}
