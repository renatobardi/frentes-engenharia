"""scripts/deploy.sh com um `lxc` falso no PATH: nada entra em LXC de verdade nem usa credencial."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "deploy.sh"
SHA = "a" * 40
CURTO = "aaaaaaa"

# O lxc falso grava cada chamada em $FAKE_LOG (uma linha, o que vem depois do "--") e responde
# conforme FAKE_* : FAKE_COMMIT_EXISTE, FAKE_NA_MAIN, FAKE_FALHA ("fetch", "checkout" ou "compose")
# e FAKE_HEALTH (o que o /healthz devolve; vários valores separados por espaço, um por leitura).
LXC_FALSO = """#!/usr/bin/env bash
args=("$@")
for i in "${!args[@]}"; do
  if [ "${args[$i]}" = "--" ]; then cmd=("${args[@]:$((i + 1))}"); fi
done
echo "lxc ${args[*]}" >> "$FAKE_LOG"
cat > /dev/null  # como o lxc de verdade: consome o stdin que receber
case "${cmd[*]}" in
  "git fetch"*) [ "${FAKE_FALHA:-}" = fetch ] && exit 1; exit 0 ;;
  "git rev-parse"*)
    [ "${FAKE_COMMIT_EXISTE:-1}" = 1 ] || exit 1
    echo "$FAKE_SHA"; exit 0 ;;
  "git merge-base"*) [ "${FAKE_NA_MAIN:-1}" = 1 ]; exit $? ;;
  "git checkout"*) [ "${FAKE_FALHA:-}" = checkout ] && exit 1; exit 0 ;;
  "docker compose up"*) [ "${FAKE_FALHA:-}" = compose ] && exit 1; exit 0 ;;
  "docker compose exec"*)
    leituras=$(grep -c "docker compose exec" "$FAKE_LOG")
    [ -z "${FAKE_STDERR:-}" ] || echo "$FAKE_STDERR" >&2
    read -ra valores <<< "$FAKE_HEALTH"
    idx=$((leituras - 1)); [ "$idx" -lt "${#valores[@]}" ] || idx=$((${#valores[@]} - 1))
    echo "${valores[$idx]}"; exit 0 ;;
esac
echo "comando inesperado no lxc falso: ${cmd[*]}" >&2
exit 99
"""


@pytest.fixture
def ambiente(tmp_path: Path) -> dict[str, str]:
    bin_falso = tmp_path / "bin"
    bin_falso.mkdir()
    lxc = bin_falso / "lxc"
    lxc.write_text(LXC_FALSO)
    lxc.chmod(lxc.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "chamadas.log"
    log.write_text("")
    # Só o necessário: nada de credencial real do host passa para o script.
    return {
        "PATH": f"{bin_falso}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "LANG": "C.UTF-8",
        "FAKE_LOG": str(log),
        "FAKE_SHA": SHA,
        "FAKE_HEALTH": SHA,
        "DEPLOY_ESPERA": "0",
        "DEPLOY_TENTATIVAS": "3",
    }


def rodar(ambiente: dict[str, str], *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env={**ambiente, **extra},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def chamadas(ambiente: dict[str, str]) -> list[str]:
    return Path(ambiente["FAKE_LOG"]).read_text().splitlines()


def test_caminho_feliz_faz_os_passos_na_ordem_e_termina_com_o_healthz_no_commit(
    ambiente: dict[str, str],
) -> None:
    r = rodar(ambiente, CURTO)
    assert r.returncode == 0, r.stderr
    assert f"OK: /healthz devolveu {SHA}" in r.stdout
    cmds = chamadas(ambiente)
    ordem = [
        "git fetch origin main",
        "git rev-parse --verify aaaaaaa^{commit}",
        f"git merge-base --is-ancestor {SHA} origin/main",
        f"git checkout --detach {SHA}",
        "docker compose up -d --build",
        "docker compose exec -T app python -c",
    ]
    posicoes = [next(i for i, c in enumerate(cmds) if p in c) for p in ordem]
    assert posicoes == sorted(posicoes)
    assert all("lxc exec frentes-engenharia-prd --cwd /opt/app" in c for c in cmds)


def test_o_commit_completo_vai_para_o_build_pelo_ambiente_do_compose(
    ambiente: dict[str, str],
) -> None:
    rodar(ambiente, CURTO)
    subida = next(c for c in chamadas(ambiente) if "docker compose up" in c)
    assert f"--env FRENTES_COMMIT={SHA}" in subida


def test_repetir_o_mesmo_sha_tambem_termina_bem(ambiente: dict[str, str]) -> None:
    assert rodar(ambiente, SHA).returncode == 0
    assert rodar(ambiente, SHA).returncode == 0


def test_commit_fora_da_main_e_recusado_sem_checkout_nem_compose(ambiente: dict[str, str]) -> None:
    r = rodar(ambiente, SHA, FAKE_NA_MAIN="0")
    assert r.returncode != 0
    assert "não está na main" in r.stderr
    cmds = " ".join(chamadas(ambiente))
    assert "git checkout" not in cmds
    assert "docker compose" not in cmds


def test_commit_que_nao_existe_no_clone_e_recusado(ambiente: dict[str, str]) -> None:
    r = rodar(ambiente, SHA, FAKE_COMMIT_EXISTE="0")
    assert r.returncode != 0
    assert "não existe" in r.stderr
    assert "git checkout" not in " ".join(chamadas(ambiente))


def test_healthz_com_outro_commit_falha_depois_das_tentativas(ambiente: dict[str, str]) -> None:
    outro = "b" * 40
    r = rodar(ambiente, SHA, FAKE_HEALTH=outro)
    assert r.returncode != 0
    assert "FALHOU" in r.stderr
    assert outro in r.stdout
    leituras = [c for c in chamadas(ambiente) if "docker compose exec" in c]
    assert len(leituras) == 3


def test_healthz_que_demora_a_mudar_espera_e_passa(ambiente: dict[str, str]) -> None:
    antigo = "c" * 40
    r = rodar(ambiente, SHA, FAKE_HEALTH=f"{antigo} {SHA}")
    assert r.returncode == 0, r.stderr
    leituras = [c for c in chamadas(ambiente) if "docker compose exec" in c]
    assert len(leituras) == 2


@pytest.mark.parametrize("etapa", ["fetch", "checkout", "compose"])
def test_falha_de_um_passo_aborta_o_deploy(ambiente: dict[str, str], etapa: str) -> None:
    r = rodar(ambiente, SHA, FAKE_FALHA=etapa)
    assert r.returncode != 0
    assert "docker compose exec" not in " ".join(chamadas(ambiente))


def test_dry_run_mostra_os_passos_e_nao_executa_nada(ambiente: dict[str, str]) -> None:
    r = rodar(ambiente, "--dry-run", SHA)
    assert r.returncode == 0, r.stderr
    assert chamadas(ambiente) == []
    trechos = ("git fetch origin main", "git checkout --detach", "docker compose up -d --build")
    for trecho in trechos:
        assert trecho in r.stdout
    assert "dry-run: nada foi executado" in r.stdout


def test_dry_run_vale_em_qualquer_posicao_e_nao_olha_o_estado_do_lxc(
    ambiente: dict[str, str],
) -> None:
    r = rodar(ambiente, SHA, "--dry-run", FAKE_NA_MAIN="0", FAKE_HEALTH="b" * 40)
    assert r.returncode == 0
    assert chamadas(ambiente) == []


@pytest.mark.parametrize(
    "args",
    [(), ("não-é-sha",), ("abc",), ("a" * 41,), (SHA, SHA), ("--outra", SHA)],
)
def test_argumento_invalido_sai_com_2_sem_chamar_o_lxc(
    ambiente: dict[str, str], args: tuple[str, ...]
) -> None:
    r = rodar(ambiente, *args)
    assert r.returncode == 2
    assert chamadas(ambiente) == []


def test_o_texto_do_script_nao_leva_segredo_nem_le_credencial() -> None:
    texto = SCRIPT.read_text()
    for nome in ("TYPESAFE", "OPENROUTER", "WEBHOOK_TOKEN", "GH_TOKEN", "OCI_S3"):
        assert nome not in texto


def test_script_que_chega_por_stdin_nao_para_depois_do_primeiro_passo(
    ambiente: dict[str, str],
) -> None:
    """O canal de aprovação manda o texto por stdin: o lxc não pode comer o resto dele."""
    r = subprocess.run(
        ["bash", "-s"],
        input=f"set -- {SHA}\n" + SCRIPT.read_text(),
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert f"OK: /healthz devolveu {SHA}" in r.stdout
    assert any("docker compose up" in c for c in chamadas(ambiente))


def test_sha_pode_vir_pela_variavel_deploy_sha(ambiente: dict[str, str]) -> None:
    r = rodar(ambiente, DEPLOY_SHA=SHA)
    assert r.returncode == 0, r.stderr
    assert any(f"git checkout --detach {SHA}" in c for c in chamadas(ambiente))


@pytest.mark.parametrize("nome", ["DEPLOY_TENTATIVAS", "DEPLOY_ESPERA"])
@pytest.mark.parametrize("valor", ["abc", "-1", "1.5"])
def test_tentativas_e_espera_so_aceitam_digitos(
    ambiente: dict[str, str], nome: str, valor: str
) -> None:
    r = rodar(ambiente, SHA, **{nome: valor})
    assert r.returncode == 2
    assert chamadas(ambiente) == []


def test_falhou_mostra_o_stderr_da_ultima_tentativa(ambiente: dict[str, str]) -> None:
    r = rodar(ambiente, SHA, FAKE_HEALTH="b" * 40, FAKE_STDERR="container reiniciando")
    assert r.returncode != 0
    assert "stderr da última tentativa" in r.stderr
    assert "container reiniciando" in r.stderr
