from dataclasses import replace

from eventos.contratos import Dimensao, ValorDoDocumento
from eventos.taxonomia.chaves import chave_nova
from eventos.taxonomia.diff import comparar
from eventos.taxonomia.valores import derivar


def test_chave_nova_vem_do_nome_sem_acento() -> None:
    assert chave_nova("Integração com o Detran", set()) == "integracao-com-o-detran"


def test_chave_nova_nao_repete_chave_usada() -> None:
    assert chave_nova("Falha", {"falha", "falha-2"}) == "falha-3"


def test_chave_nova_nunca_e_nenhum_destes() -> None:
    assert chave_nova("Nenhum destes", set()) == "nenhum-destes-2"
    assert chave_nova("nenhum_destes", set()) == "nenhum-destes-2"
    assert chave_nova("   ", set()) == "valor"


def test_renomear_mantem_a_chave(documento, frentes) -> None:
    antes = derivar(1, documento())
    primeiro, *resto = frentes()
    renomeado = replace(primeiro, nome="Falha de sistema")
    depois = derivar(2, documento(frentes=(renomeado, *resto)))

    diff = comparar(antes, depois)

    assert diff.criados == () and diff.removidos == ()
    [mudanca] = diff.renomeados
    assert (mudanca.antes.chave, mudanca.depois.chave) == ("frente1", "frente1")
    assert mudanca.depois.nome == "Falha de sistema"


def test_criar_gera_chave_nova(documento, frentes) -> None:
    antes = derivar(1, documento())
    novo = ValorDoDocumento("migracao", "Migração", "mover de plataforma", frentes()[0].filhos)
    depois = derivar(2, documento(frentes=(*frentes(), novo)))

    diff = comparar(antes, depois)

    chaves = {(v.dimensao, v.chave) for v in diff.criados}
    assert (Dimensao.FRENTE, "migracao") in chaves
    assert diff.removidos == () and diff.renomeados == ()


def test_juntar_remove_as_chaves_antigas_e_cria_a_nova(documento, frentes) -> None:
    antes = derivar(1, documento())
    a, b, *resto = frentes()
    juntado = replace(a, chave="frentes-12", nome="Frentes 1 e 2")
    depois = derivar(2, documento(frentes=(juntado, *resto)))

    diff = comparar(antes, depois)

    assert {v.chave for v in diff.removidos if v.dimensao is Dimensao.FRENTE} >= {
        "frente1",
        "frente2",
    }
    assert "frentes-12" in {v.chave for v in diff.criados}


def test_descricao_e_pai_alterados_aparecem_a_parte(documento, frentes) -> None:
    antes = derivar(1, documento())
    a, b, *resto = frentes()
    sub, *outros = a.filhos
    a2 = replace(a, filhos=tuple(outros))
    b2 = replace(b, filhos=(*b.filhos, replace(sub, descricao="outra descrição")))

    diff = comparar(antes, derivar(2, documento(frentes=(a2, b2, *resto))))

    [movido] = diff.movidos
    assert (movido.antes.chave_pai, movido.depois.chave_pai) == ("frente1", "frente2")
    assert movido.depois.chave == sub.chave
    assert [m.depois.chave for m in diff.descricao_alterada] == [sub.chave]


def test_versoes_iguais_nao_tem_diferenca(documento) -> None:
    assert comparar(derivar(1, documento()), derivar(2, documento())).vazio


def test_valores_derivados(documento) -> None:
    valores = {(v.dimensao, v.chave): v for v in derivar(1, documento())}

    assert valores[(Dimensao.AREA, "originacao")].chave_pai is None
    assert valores[(Dimensao.AREA, "simulacao")].chave_pai == "originacao"
    assert valores[(Dimensao.AREA, "simulacao")].descricao == "Calcula parcelas"
    assert valores[(Dimensao.FRENTE, "frente1-sub1")].chave_pai == "frente1"
    assert valores[(Dimensao.FRENTE, "frente2-sub2")].ordem == 1
    assert valores[(Dimensao.SEVERIDADE, "nivel-4")].nome == "nível 4"
    assert (Dimensao.NATUREZA, "reativo") in valores
    assert valores[(Dimensao.URGENCIA, "urgencia")].descricao == "a janela de tempo para agir"
    assert (Dimensao.PROBLEMA, "problema3") in valores
