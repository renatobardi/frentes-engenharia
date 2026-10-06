"""Os cortes da conferência, como estão na spec (04, 05 e 08). São iniciais: a recalibrar
com a seed inteira classificada. Os limiares do pipeline (confiança, encaixe fraco) não
estão aqui: vêm do `config/limiares.toml`."""

from eventos.conferencia.relatorio import Corte

# 04: por história
FRENTE_COMUM = Corte(minimo=0.60)
AREA_ACEITA = Corte(minimo=0.90)
TEMA_NOVO_NA_FRENTE_NOVA = Corte(minimo=0.80)
TOP_1 = Corte(minimo=6, maximo=10)  # intensidade: múltiplos da mediana das células
DEMAIS = Corte(minimo=2.5, maximo=6)

# 08: área do fundo e relato cruzado
FUNDO_LISTADO = Corte(minimo=0.85)
FUNDO_PLATAFORMA = Corte(maximo=1.5)
CRUZADO_LISTADO = Corte(minimo=0.90)
CRUZADO_NA_AREA_DO_RELATOR = Corte(maximo=0.10)

# 05: problema, de H1 a H5
HISTORIAS_COM_PROBLEMA = Corte(minimo=4)
PROBLEMAS_POR_HISTORIA = Corte(maximo=3)
PROBLEMA_DO_FUNDO = Corte(maximo=0)
COBERTURA = Corte(minimo=0.70)
FALSO_POSITIVO_OUTRO_TIME = Corte(maximo=0.05)

# As histórias da spec 08: o time fixo (conferido por área aceita), a visão de cada uma e
# quais têm corte de intensidade. H3 esfria depois do mês 6 (a janela de 90 dias do dia D
# não pega o pico) e H7 desenha uma coluna, não uma célula: as duas só são reportadas.
HISTORIAS = ("H1", "H2", "H3", "H4", "H5", "H6", "H7")
HISTORIAS_DE_TIME_FIXO = ("H2", "H3", "H4", "H6")
TEMA_NOVO = "H5"
HISTORIAS_DO_PROBLEMA = ("H1", "H2", "H3", "H4", "H5")
AREA_PLATAFORMA = "plataforma-e-sustentacao"
