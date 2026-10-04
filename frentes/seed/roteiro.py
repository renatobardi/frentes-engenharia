"""O roteiro com seed fixa: sorteia o esqueleto de cada frente da seed.

O gabarito sai daqui, nunca do texto. Os dados vêm do organograma e dos emissores (`seed/`);
o resto são as curvas e as distribuições da spec 08. A mesma seed dá os mesmos esqueletos.
"""

import random
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from frentes.contratos import (
    AreaDoOrganograma,
    Cruzado,
    EspecieDeItem,
    Natureza,
    Origem,
    TimeDoOrganograma,
)
from frentes.seed import curvas
from frentes.seed.curvas import HISTORIAS, Historia
from frentes.seed.temas import HISTORIAS as SINTOMAS_HISTORIAS
from frentes.seed.temas import TEMAS
from frentes.seed.templates import EMISSOR_GENERICO
from frentes.seed.validador import sem_acento

SEED = 20260930
TOTAL = 6000
ESTILOS = ("curto", "detalhado", "informal", "formal", "tecnico")
ORIGENS_COM_TEMPLATE = (Origem.LOG, Origem.WEBHOOK, Origem.BANCO)
ORIGENS_DE_TEXTO = (Origem.RELATO, Origem.MCP)


class ErroDeRoteiro(Exception):
    """O roteiro não fecha: totais impossíveis ou todos os times estouraram o teto."""


@dataclass(slots=True)
class Esqueleto:
    id: str
    historia_id: str
    cenario: str
    origem: Origem
    emissor: str
    time_emissor: str | None
    area: str | None
    time: str | None
    areas_aceitas: tuple[str, ...]
    natureza: Natureza | None
    gravidade_alvo: str | None
    estilo: str
    ocorrido_em: datetime
    recebido_em: datetime
    ref_externa: str | None = None
    tema_fundo: str | None = None
    ambigua: str | None = None
    fora_de_escopo: bool = False
    episodio_id: str | None = None
    objeto: str | None = None
    servico: str | None = None
    listado: bool | None = None
    time_relator: str | None = None
    cruzado: Cruzado | None = None
    objeto_relator: str | None = None
    time_secundario: str | None = None
    objeto_secundario: str | None = None
    sintoma: int = 0


@dataclass(slots=True)
class Roteiro:
    esqueletos: list[Esqueleto]
    dia_d: date
    seed: int
    teto: int
    estouros: int
    meses: list[tuple[int, int]]
    historias_por_mes: dict[str, list[int]] = field(default_factory=dict)

    def mes_de(self, esq: Esqueleto) -> int:
        """O mês 1–12 da frente, contado do dia D."""
        ano, mes = esq.ocorrido_em.year, esq.ocorrido_em.month
        return self.meses.index((ano, mes - 1)) + 1


class Itens:
    """O uso de cada item da ficha por semestre, para o teto."""

    def __init__(self, teto: int) -> None:
        self.teto = teto
        self.usos: Counter[tuple[int, str, str]] = Counter()
        self.estouros = 0

    def livre(self, semestre: int, time: str, item: str) -> bool:
        return self.usos[(semestre, time, item)] < self.teto

    def usar(self, semestre: int, time: str, item: str) -> None:
        self.usos[(semestre, time, item)] += 1


def sortear_time_e_item(
    rng: random.Random,
    times: Sequence[TimeDoOrganograma],
    pesos: Sequence[float],
    candidatos: Callable[[TimeDoOrganograma], Sequence[str]],
    itens: Itens,
    semestre: int,
    excluir: Sequence[str] = (),
) -> tuple[TimeDoOrganograma, str]:
    """Sorteia um time e um item dele; se o item já está no teto no semestre, sorteia outro time.

    Cada troca conta em `itens.estouros`. Sem time que caiba, levanta `ErroDeRoteiro`.
    """
    tentados = set(excluir)
    while True:
        restantes = [(t, p) for t, p in zip(times, pesos, strict=True) if t.chave not in tentados]
        if not restantes:
            raise ErroDeRoteiro("todos os times estouraram o teto por item neste semestre")
        time = rng.choices([t for t, _ in restantes], [p for _, p in restantes])[0]
        item = rng.choice(list(candidatos(time)))
        if itens.livre(semestre, time.chave, item):
            itens.usar(semestre, time.chave, item)
            return time, item
        itens.estouros += 1
        tentados.add(time.chave)


def teto_por_item(contagens_historias: dict[str, list[int]]) -> int:
    """Metade da menor história com frentes nos meses 1–6 (o teto, por semestre)."""
    primeiros = [sum(c[:6]) for c in contagens_historias.values() if sum(c[:6]) > 0]
    if not primeiros:
        raise ErroDeRoteiro("nenhuma história tem frentes nos meses 1–6: o volume é pequeno demais")
    return min(primeiros) // 2


@dataclass(frozen=True, slots=True)
class Pessoas:
    por_time: dict[str, list[str]]
    sistemas: dict[str, list[str]]
    todas: list[tuple[str, str]]  # (nome, time)


def ler_pessoas(emissores: dict) -> Pessoas:
    por_time: dict[str, list[str]] = {}
    sistemas: dict[str, list[str]] = {}
    todas: list[tuple[str, str]] = []
    for e in emissores["emissores"]:
        if e["tipo"] == "pessoa":
            por_time.setdefault(e["time"], []).append(e["nome"])
            todas.append((e["nome"], e["time"]))
        else:
            sistemas.setdefault(e["time"], []).append(e["nome"])
    return Pessoas(por_time, sistemas, todas)


def _itens(time: TimeDoOrganograma, especie: EspecieDeItem) -> list[str]:
    return [i.nome for i in time.itens if i.especie is especie]


def cita_termo(nome: str, termos: Sequence[str]) -> bool:
    """O nome (sem acento nem maiúscula) cita algum dos termos como palavra inteira."""
    norma = sem_acento(nome).replace("-", " ")
    return any(re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", norma) for t in termos)


def _listado(time: TimeDoOrganograma, nome: str) -> bool:
    return next(i.listado for i in time.itens if i.nome == nome)


class Gerador:
    def __init__(
        self,
        areas: Sequence[AreaDoOrganograma],
        emissores: dict,
        dia_d: date,
        seed: int = SEED,
        total: int = TOTAL,
        termos_de_historia: Sequence[str] = (),
    ) -> None:
        self.termos = termos_de_historia
        self.rng = random.Random(f"roteiro:{seed}")
        self.seed, self.total, self.dia_d = seed, total, dia_d
        self.meses = curvas.meses_ate(dia_d)
        self.times = [t for a in areas for t in a.times]
        self.area_de = {t.chave: a.chave for a in areas for t in a.times}
        self.time_por_chave = {t.chave: t for t in self.times}
        self.pessoas = ler_pessoas(emissores)
        self.pesos_time = [self.rng.uniform(0.7, 1.5) for _ in self.times]
        self.esqueletos: list[Esqueleto] = []
        self.meses_do: dict[int, int] = {}

    # ------------------------------------------------------------------ totais

    def calcular_totais(self) -> None:
        total_mes = curvas.repartir(
            self.total, [curvas.CRESCIMENTO_MENSAL**k for k in range(curvas.MESES)]
        )
        self.historia_por_mes: dict[str, list[int]] = {}
        for h in HISTORIAS.values():
            n = round(self.total * h.peso)
            self.historia_por_mes[h.id] = curvas.repartir(
                n, [h.curva(m) for m in range(1, curvas.MESES + 1)]
            )
        n_fora = round(self.total * curvas.FORA_DE_ESCOPO)
        self.fora_por_mes = curvas.repartir(n_fora, total_mes)
        self.fundo_por_mes = [
            total_mes[i] - sum(c[i] for c in self.historia_por_mes.values()) - self.fora_por_mes[i]
            for i in range(curvas.MESES)
        ]
        if min(self.fundo_por_mes) < 0:
            raise ErroDeRoteiro("as histórias passam do volume de um mês")
        self.teto = teto_por_item(self.historia_por_mes)
        self.itens = Itens(self.teto)

    # ------------------------------------------------------------------ peças

    def instante(self, origem: Origem, mes: int, pico: bool = False) -> tuple[datetime, datetime]:
        ano, mes0 = self.meses[mes - 1]
        dias = curvas.dias_do_mes(ano, mes0)
        dia = self.rng.choices(dias, [curvas.peso_do_dia(d, pico) for d in dias])[0]
        hora = self.rng.randint(8, 18) if origem in ORIGENS_DE_TEXTO else self.rng.randint(0, 23)
        ocorrido = datetime(
            dia.year,
            dia.month,
            dia.day,
            hora,
            self.rng.randint(0, 59),
            self.rng.randint(0, 59),
            tzinfo=UTC,
        )
        atraso = {
            Origem.RELATO: timedelta(minutes=self.rng.randint(1, 180)),
            Origem.MCP: timedelta(minutes=self.rng.randint(1, 10)),
        }.get(origem, timedelta(seconds=self.rng.randint(1, 30)))
        fim = datetime(self.dia_d.year, self.dia_d.month, self.dia_d.day, 23, 59, 59, tzinfo=UTC)
        return ocorrido, min(ocorrido + atraso, fim)

    def emissor(self, origem: Origem, time: str, fundo: bool = False) -> tuple[str, str | None]:
        """Pessoa do time (relato e mcp) ou sistema do time; sem sistema, um genérico da origem.

        No fundo, o sistema cujo nome cita o objeto de uma história (como o "Vigia da
        Esteira") não emite: o texto do fundo não pode nomear esse objeto.
        """
        if origem in ORIGENS_DE_TEXTO:
            return self.rng.choice(self.pessoas.por_time[time]), time
        todos = self.pessoas.sistemas.get(time, [])
        if fundo:
            todos = [s for s in todos if not cita_termo(s, self.termos)]
        certos = [s for s in todos if s.startswith("Banco") == (origem is Origem.BANCO)]
        if certos:
            return self.rng.choice(certos), time
        return EMISSOR_GENERICO[origem], None

    def gravidade(self, natureza: Natureza, pesos: dict[str, float]) -> str | None:
        if natureza is not Natureza.REATIVA:
            return None
        pesos = pesos or curvas.FUNDO_GRAVIDADE
        return self.rng.choices(list(pesos), list(pesos.values()))[0]

    def novo(self, mes: int, **campos) -> Esqueleto:
        origem: Origem = campos["origem"]
        ocorrido, recebido = self.instante(origem, mes, campos.pop("pico", False))
        esq = Esqueleto(
            id="",
            ocorrido_em=ocorrido,
            recebido_em=recebido,
            estilo="terceira_pessoa"
            if origem is Origem.MCP
            else (self.rng.choice(ESTILOS) if origem is Origem.RELATO else "padrao"),
            **campos,
        )
        self.esqueletos.append(esq)
        self.meses_do[id(esq)] = mes
        return esq

    @staticmethod
    def escolher_item(especie: EspecieDeItem) -> Callable[[TimeDoOrganograma], list[str]]:
        return lambda t: _itens(t, especie)

    # ------------------------------------------------------------------ histórias

    def historias(self) -> None:
        for h in HISTORIAS.values():
            for mes, quantas in enumerate(self.historia_por_mes[h.id], start=1):
                for _ in range(quantas):
                    self.frente_de_historia(h, mes)
            if h.episodios:
                self.episodios(h)

    def cenario(self, h: Historia):
        return self.rng.choices(h.cenarios, [c.peso for c in h.cenarios])[0]

    def frente_de_historia(self, h: Historia, mes: int) -> None:
        c = self.cenario(h)
        origem = self.rng.choices(list(c.origens), list(c.origens.values()))[0]
        sem = curvas.semestre(mes)
        especie = EspecieDeItem.SERVICO if origem in ORIGENS_COM_TEMPLATE else EspecieDeItem.OBJETO
        servico = objeto = None
        listado = None
        if c.times:
            area, tchave = self.rng.choices(list(c.times), list(c.times.values()))[0]
            time = self.time_por_chave[tchave]
            if origem in ORIGENS_COM_TEMPLATE:
                servico = self.rng.choice(_itens(time, EspecieDeItem.SERVICO))
            objeto = h.objeto
        else:
            # time vindo da ficha, com o teto por item (H5 pedidos espalhados e H7)
            if h.id == "H5":
                times = [t for t in self.times if t.chave != "app"]
                pesos = [self.pesos_time[self.times.index(t)] for t in times]
            else:
                times = self.times
                pesos = [
                    self.pesos_time[i]
                    * (3.0 if self.area_de[t.chave] in curvas.COM_PESO_EXTRA else 1)
                    for i, t in enumerate(self.times)
                ]
            time, item = sortear_time_e_item(
                self.rng, times, pesos, self.escolher_item(especie), self.itens, sem
            )
            area = self.area_de[time.chave]
            if especie is EspecieDeItem.SERVICO:
                servico = item
            else:
                objeto = item
            listado = _listado(time, item)
            if h.id == "H5":
                objeto = item
        emissor, time_emissor = self.emissor(origem, time.chave)
        areas = h.areas_aceitas if c.times else (area,)
        n_sint = len(SINTOMAS_HISTORIAS.get(h.id, ()))
        self.novo(
            mes,
            historia_id=h.id,
            cenario=c.nome,
            origem=origem,
            emissor=emissor,
            time_emissor=time_emissor,
            area=area,
            time=time.chave,
            areas_aceitas=tuple(areas),
            natureza=c.natureza,
            gravidade_alvo=self.gravidade(c.natureza, c.gravidade),
            objeto=objeto,
            servico=servico,
            listado=listado,
            sintoma=self.rng.randrange(n_sint) if n_sint else 0,
            pico=h.pico_de_fim_de_mes,
        )

    def episodios(self, h: Historia) -> None:
        """Frentes reativas da mesma história no mesmo dia viram um episódio."""
        por_dia: dict[date, list[Esqueleto]] = {}
        for e in self.esqueletos:
            if e.historia_id == h.id and e.natureza is Natureza.REATIVA:
                por_dia.setdefault(e.ocorrido_em.date(), []).append(e)
        for dia, lista in por_dia.items():
            if len(lista) >= 2:
                for e in lista:
                    e.episodio_id = f"ep-{h.id.lower()}-{dia:%Y%m%d}"

    # ------------------------------------------------------------------ fora e fundo

    def fora_de_escopo(self) -> None:
        for mes, quantas in enumerate(self.fora_por_mes, start=1):
            for _ in range(quantas):
                origem = self.rng.choices(
                    list(curvas.FORA_ORIGENS), list(curvas.FORA_ORIGENS.values())
                )[0]
                nome, time = self.rng.choice(self.pessoas.todas)
                self.novo(
                    mes,
                    historia_id="fora",
                    cenario="fora",
                    origem=origem,
                    emissor=nome,
                    time_emissor=time,
                    area=None,
                    time=None,
                    areas_aceitas=(),
                    natureza=None,
                    gravidade_alvo=None,
                    fora_de_escopo=True,
                )

    def origens_do_fundo(self, slots: list[int]) -> list[Origem]:
        alvo = {o: round(p * self.total) for o, p in curvas.ORIGENS.items()}
        feitas = Counter(e.origem for e in self.esqueletos)
        resto = {o: alvo[o] - feitas[o] for o in alvo}
        if min(resto.values()) < 0 or sum(resto.values()) != len(slots):
            raise ErroDeRoteiro(f"origens do fundo não fecham: {resto} para {len(slots)} frentes")
        lista = [o for o, n in resto.items() for _ in range(n)]
        self.rng.shuffle(lista)
        return lista

    def naturezas_do_fundo(self, origens: list[Origem]) -> list[Natureza]:
        """Log, banco e webhook são reativos; o resto das reativas vem de relato e mcp."""
        feitas = [e.natureza for e in self.esqueletos if e.natureza is not None]
        alvo = round(
            curvas.REATIVA * (self.total - sum(1 for e in self.esqueletos if e.fora_de_escopo))
        )
        fixas = sum(1 for o in origens if o not in ORIGENS_DE_TEXTO)
        faltam = alvo - sum(1 for n in feitas if n is Natureza.REATIVA) - fixas
        texto = [i for i, o in enumerate(origens) if o in ORIGENS_DE_TEXTO]
        if not 0 <= faltam <= len(texto):
            raise ErroDeRoteiro(f"naturezas não fecham: faltam {faltam} reativas em {len(texto)}")
        reativas = set(self.rng.sample(texto, faltam))
        return [
            Natureza.REATIVA if (o not in ORIGENS_DE_TEXTO or i in reativas) else Natureza.PROATIVA
            for i, o in enumerate(origens)
        ]

    def fundo(self) -> None:
        slots = [m for m, q in enumerate(self.fundo_por_mes, start=1) for _ in range(q)]
        origens = self.origens_do_fundo(slots)
        naturezas = self.naturezas_do_fundo(origens)
        # relato cruzado e ambíguas, só em relato e mcp
        relatos = [i for i, o in enumerate(origens) if o is Origem.RELATO]
        cruzados = set(self.rng.sample(relatos, round(curvas.CRUZADO * len(relatos))))
        sabores = [Cruzado.SO_O_DONO, Cruzado.DOIS_OBJETOS]
        sabor_de = {i: sabores[k % 2] for k, i in enumerate(sorted(cruzados))}
        candidatas = [
            i for i, o in enumerate(origens) if o in ORIGENS_DE_TEXTO and i not in cruzados
        ]
        n_amb = round(curvas.AMBIGUAS * self.total)
        ambiguas = self.rng.sample(candidatas, n_amb)
        sabor_amb = {i: curvas.SABORES_AMBIGUOS[k % 4] for k, i in enumerate(sorted(ambiguas))}
        tecnicos = [t for t in TEMAS if t.grupo == "tecnico"]
        funcionais = [t for t in TEMAS if t.grupo == "funcional"]
        grupos = [True] * (len(slots) // 2) + [False] * (len(slots) - len(slots) // 2)
        self.rng.shuffle(grupos)
        for i, mes in enumerate(slots):
            self.frente_de_fundo(
                i,
                mes,
                origens[i],
                naturezas[i],
                tecnicos if grupos[i] else funcionais,
                sabor_de.get(i),
                sabor_amb.get(i),
            )

    def frente_de_fundo(self, i, mes, origem, natureza, temas, cruzado, ambigua) -> None:
        sem = curvas.semestre(mes)
        tema = self.rng.choices(temas, [t.peso for t in temas])[0]
        if tema.chave == "fornecedor":
            especie = EspecieDeItem.FORNECEDOR
        elif origem in ORIGENS_COM_TEMPLATE:
            especie = EspecieDeItem.SERVICO
        else:
            especie = EspecieDeItem.OBJETO
        time, item = sortear_time_e_item(
            self.rng, self.times, self.pesos_time, self.escolher_item(especie), self.itens, sem
        )
        extra: dict = {}
        emissor_time = time.chave
        if cruzado is not None:
            mesma = self.rng.random() < curvas.CRUZADO_MESMA_AREA
            area_dono = self.area_de[time.chave]
            outros = [
                t
                for t in self.times
                if t.chave != time.chave and (self.area_de[t.chave] == area_dono) == mesma
            ]
            relator = self.rng.choice(outros)
            emissor_time = relator.chave
            extra.update(time_relator=relator.chave, cruzado=cruzado)
            if cruzado is Cruzado.DOIS_OBJETOS:
                _, objeto_relator = sortear_time_e_item(
                    self.rng,
                    [relator],
                    [1.0],
                    self.escolher_item(EspecieDeItem.OBJETO),
                    self.itens,
                    sem,
                )
                extra["objeto_relator"] = objeto_relator
        if ambigua == "duas_areas":
            area_dono = self.area_de[time.chave]
            outros = [t for t in self.times if self.area_de[t.chave] != area_dono]
            pesos = [self.pesos_time[self.times.index(t)] for t in outros]
            segundo, objeto2 = sortear_time_e_item(
                self.rng,
                outros,
                pesos,
                self.escolher_item(EspecieDeItem.OBJETO),
                self.itens,
                sem,
            )
            extra.update(time_secundario=segundo.chave, objeto_secundario=objeto2)
        aceitas = [self.area_de[time.chave]]
        if "time_secundario" in extra:
            aceitas.append(self.area_de[extra["time_secundario"]])
        emissor, time_emissor = (
            (self.rng.choice(self.pessoas.por_time[emissor_time]), emissor_time)
            if origem in ORIGENS_DE_TEXTO
            else self.emissor(origem, emissor_time, fundo=True)
        )
        usa_servico = especie is EspecieDeItem.SERVICO or (
            tema.chave == "fornecedor" and origem in ORIGENS_COM_TEMPLATE
        )
        self.novo(
            mes,
            historia_id="fundo",
            cenario="fundo",
            origem=origem,
            emissor=emissor,
            time_emissor=time_emissor,
            area=self.area_de[time.chave],
            time=time.chave,
            areas_aceitas=tuple(aceitas),
            natureza=natureza,
            gravidade_alvo=self.gravidade(natureza, {}),
            tema_fundo=tema.chave,
            ambigua=ambigua,
            objeto=None if usa_servico else item,
            servico=item if usa_servico else None,
            listado=_listado(time, item),
            sintoma=self.rng.randrange(len(tema.sintomas)),
            **extra,
        )

    # ------------------------------------------------------------------ fecho

    def fechar(self) -> Roteiro:
        ordem = sorted(self.esqueletos, key=lambda e: (e.ocorrido_em, e.origem.value, e.time or ""))
        # `sorted` é estável e o desempate acima não depende de sorteio: a ordem é reproduzível.
        largura = len(str(self.total))
        for n, esq in enumerate(ordem, start=1):
            esq.id = f"fr-{n:0{largura}d}"
            if esq.origem is not Origem.RELATO:
                esq.ref_externa = f"seed-{esq.origem.value}-{n:0{largura}d}"
        return Roteiro(
            esqueletos=ordem,
            dia_d=self.dia_d,
            seed=self.seed,
            teto=self.teto,
            estouros=self.itens.estouros,
            meses=self.meses,
            historias_por_mes=self.historia_por_mes,
        )


def gerar_roteiro(
    areas: Sequence[AreaDoOrganograma],
    emissores: dict,
    dia_d: date,
    seed: int = SEED,
    total: int = TOTAL,
    termos_de_historia: Sequence[str] = (),
) -> Roteiro:
    g = Gerador(areas, emissores, dia_d, seed, total, termos_de_historia)
    g.calcular_totais()
    g.historias()
    g.fora_de_escopo()
    g.fundo()
    return g.fechar()
