from dataclasses import replace

from frentes.contratos import Dimensao, ValorDoDocumento
from frentes.taxonomia.chaves import chave_nova
from frentes.taxonomia.diff import comparar
from frentes.taxonomia.valores import derivar


def test_chave_nova_vem_do_nome_sem_acento() -> None:
    assert chave_nova("Integração com o Detran", set()) == "integracao-com-o-detran"


def test_chave_nova_nao_repete_chave_usada() -> None:
    assert chave_nova("Falha", {"falha", "falha-2"}) == "falha-3"


def test_chave_nova_nunca_e_nenhum_destes() -> None:
    assert chave_nova("nenhum_destes", set()) != "nenhum_destes"
    assert chave_nova("   ", set()) == "valor"


def test_renomear_mantem_a_chave(documento, tipos) -> None:
    antes = derivar(1, documento())
    primeiro, *resto = tipos()
    renomeado = replace(primeiro, nome="Falha de sistema")
    depois = derivar(2, documento(tipos=(renomeado, *resto)))

    diff = comparar(antes, depois)

    assert diff.criados == () and diff.removidos == ()
    [mudanca] = diff.renomeados
    assert (mudanca.antes.chave, mudanca.depois.chave) == ("tipo1", "tipo1")
    assert mudanca.depois.nome == "Falha de sistema"


def test_criar_gera_chave_nova(documento, tipos) -> None:
    antes = derivar(1, documento())
    novo = ValorDoDocumento("migracao", "Migração", "mover de plataforma", tipos()[0].filhos)
    depois = derivar(2, documento(tipos=(*tipos(), novo)))

    diff = comparar(antes, depois)

    chaves = {(v.dimensao, v.chave) for v in diff.criados}
    assert (Dimensao.TIPO, "migracao") in chaves
    assert diff.removidos == () and diff.renomeados == ()


def test_juntar_remove_as_chaves_antigas_e_cria_a_nova(documento, tipos) -> None:
    antes = derivar(1, documento())
    a, b, *resto = tipos()
    juntado = replace(a, chave="tipos-12", nome="Tipos 1 e 2")
    depois = derivar(2, documento(tipos=(juntado, *resto)))

    diff = comparar(antes, depois)

    assert {v.chave for v in diff.removidos if v.dimensao is Dimensao.TIPO} >= {"tipo1", "tipo2"}
    assert "tipos-12" in {v.chave for v in diff.criados}


def test_descricao_e_pai_alterados_aparecem_a_parte(documento, tipos) -> None:
    antes = derivar(1, documento())
    a, b, *resto = tipos()
    sub, *outros = a.filhos
    a2 = replace(a, filhos=tuple(outros))
    b2 = replace(b, filhos=(*b.filhos, replace(sub, descricao="outra descrição")))

    diff = comparar(antes, derivar(2, documento(tipos=(a2, b2, *resto))))

    [movido] = diff.movidos
    assert (movido.antes.chave_pai, movido.depois.chave_pai) == ("tipo1", "tipo2")
    assert movido.depois.chave == sub.chave
    assert [m.depois.chave for m in diff.descricao_alterada] == [sub.chave]


def test_versoes_iguais_nao_tem_diferenca(documento) -> None:
    assert comparar(derivar(1, documento()), derivar(2, documento())).vazio


def test_valores_derivados(documento) -> None:
    valores = {(v.dimensao, v.chave): v for v in derivar(1, documento())}

    assert valores[(Dimensao.AREA, "originacao")].chave_pai is None
    assert valores[(Dimensao.AREA, "simulacao")].chave_pai == "originacao"
    assert valores[(Dimensao.AREA, "simulacao")].descricao == "Calcula parcelas"
    assert valores[(Dimensao.TIPO, "tipo1-sub1")].chave_pai == "tipo1"
    assert valores[(Dimensao.TIPO, "tipo2-sub2")].ordem == 1
    assert valores[(Dimensao.SEVERIDADE, "nivel-4")].nome == "nível 4"
    assert (Dimensao.NATUREZA, "reativa") in valores
    assert valores[(Dimensao.URGENCIA, "urgencia")].descricao == "a janela de tempo para agir"
    assert (Dimensao.PROBLEMA, "problema3") in valores
