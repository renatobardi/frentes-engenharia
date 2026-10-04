"""O resultado de cada conferência e o relatório que o comando imprime."""

from dataclasses import dataclass
from enum import StrEnum


class Veredito(StrEnum):
    PASSOU = "passou"
    FALHOU = "FALHOU"
    REPORTADO = "só reportado"
    SEM_VALOR = "sem valor"


@dataclass(frozen=True, slots=True)
class Corte:
    """Limites inclusivos; um dos dois pode faltar."""

    minimo: float | None = None
    maximo: float | None = None

    def vale(self, medido: float) -> bool:
        return (self.minimo is None or medido >= self.minimo) and (
            self.maximo is None or medido <= self.maximo
        )

    def texto(self, formato: str = "{:g}") -> str:
        if self.minimo is not None and self.maximo is not None:
            return f"{formato.format(self.minimo)} a {formato.format(self.maximo)}"
        if self.minimo is not None:
            return f"≥ {formato.format(self.minimo)}"
        return f"≤ {formato.format(self.maximo)}"


@dataclass(frozen=True, slots=True)
class Conferencia:
    grupo: str
    nome: str
    veredito: Veredito
    medido: float | None  # o número que o corte compara
    texto: str  # o medido como se lê, com as contagens
    corte: str  # o corte como se lê; vazio quando não há

    @property
    def derruba(self) -> bool:
        return self.veredito is Veredito.FALHOU


def com_corte(
    grupo: str, nome: str, medido: float | None, texto: str, corte: Corte, formato: str = "{:.0%}"
) -> Conferencia:
    """Conferência com corte: sem valor medido não passa nem falha."""
    if medido is None:
        return Conferencia(grupo, nome, Veredito.SEM_VALOR, None, texto, corte.texto(formato))
    veredito = Veredito.PASSOU if corte.vale(medido) else Veredito.FALHOU
    return Conferencia(grupo, nome, veredito, medido, texto, corte.texto(formato))


def so_reportada(
    grupo: str, nome: str, medido: float | None, texto: str, motivo: str = "sem corte"
) -> Conferencia:
    return Conferencia(grupo, nome, Veredito.REPORTADO, medido, texto, motivo)


def fracao(parte: int, todo: int) -> tuple[float | None, str]:
    """A fração e o texto "X% (parte de todo)"; sem denominador, sem valor."""
    if todo == 0:
        return None, "nenhuma frente"
    return parte / todo, f"{parte / todo:.1%} ({parte} de {todo})"


@dataclass(frozen=True, slots=True)
class Relatorio:
    versao: int
    cabecalho: tuple[str, ...]
    conferencias: tuple[Conferencia, ...]

    @property
    def falhas(self) -> list[Conferencia]:
        return [c for c in self.conferencias if c.derruba]

    @property
    def codigo_de_saida(self) -> int:
        return 1 if self.falhas else 0

    def texto(self) -> str:
        linhas = [f"conferência contra o gabarito, versão {self.versao}", *self.cabecalho, ""]
        grupo = None
        for c in self.conferencias:
            if c.grupo != grupo:
                grupo = c.grupo
                linhas += ["", f"## {grupo}"]
            if c.veredito is Veredito.REPORTADO:
                corte = c.corte
            else:
                corte = f"corte {c.corte}" if c.corte else ""
            linhas.append(
                f"[{c.veredito.value}] {c.nome}: {c.texto}" + (f" · {corte}" if corte else "")
            )
        contagem = {v: sum(c.veredito is v for c in self.conferencias) for v in Veredito}
        linhas += [
            "",
            f"{contagem[Veredito.PASSOU]} passaram, {contagem[Veredito.FALHOU]} falharam, "
            f"{contagem[Veredito.REPORTADO]} só reportadas, "
            f"{contagem[Veredito.SEM_VALOR]} sem valor",
        ]
        if self.falhas:
            linhas.append("falharam: " + "; ".join(f"{c.grupo} / {c.nome}" for c in self.falhas))
        return "\n".join(linhas)
