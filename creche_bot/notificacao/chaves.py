"""CONTRATO CONGELADO — v2.

Toda mensagem PROATIVA é (ChaveTemplate, variáveis). Nunca uma string pronta.

No Telegram a chave vira texto com figurinha. No WhatsApp vira template aprovado pela
Meta — que não aceita texto livre nem figurinha fora da janela de 24h, leva ~24h para
aprovar, e é pago. Se o emissor gravasse a string pronta, o flip seria impossível.

## Por que estes fluxos existem

Em 2025, 5.519 famílias (7,7%) foram convocadas e perderam a vaga, concentradas em
Pilares, Santa Teresa, Gávea e Bangu. **A maior parte nunca soube que foi chamada.** Hoje
"não foi avisada" e "foi avisada e desistiu" viram o mesmo registro e as duas são tratadas
como desistência — só a primeira é problema que o bot resolve. `CONVOCACAO` mais
`LEMBRETE_CONVOCACAO` são a correção direta desse vazamento.

## Mudar este enum é grátis AGORA e caro depois

Cada chave = um template submetido à Meta na Fase 3. Antes disso, mexer aqui custa um
commit. Depois, custa 24h de aprovação por chave.
"""

from enum import StrEnum

from creche_bot.dominio.tipos import TipoEtapa


class ChaveTemplate(StrEnum):
    INSCRICAO_CONFIRMADA = "inscricao_confirmada"
    ETAPA_AVANCOU = "etapa_avancou"                  # andou, e não precisa fazer nada
    DOCUMENTO_PENDENTE = "documento_pendente"        # R1 — falta comprovar um critério
    ACAO_PRESENCIAL = "acao_presencial"              # precisa ir até a unidade
    CONVOCACAO = "convocacao"                        # R2 — saiu vaga, e há prazo
    LEMBRETE_CONVOCACAO = "lembrete_convocacao"      # R3 — R2 não foi lida em 24h
    RESULTADO_CLASSIFICADA = "resultado_classificada"  # R4
    RESULTADO_NAO_CLASSIFICADA = "resultado_nao_classificada"
    LEMBRETE_INCOMPLETO = "lembrete_incompleto"      # conversa parou pela metade


# Variáveis obrigatórias por chave. O catálogo valida contra isto ANTES de renderizar:
# template do WhatsApp com variável faltando é erro em produção, não no deploy.
VARIAVEIS: dict[ChaveTemplate, tuple[str, ...]] = {
    ChaveTemplate.INSCRICAO_CONFIRMADA:       ("nome_crianca", "numero"),
    ChaveTemplate.ETAPA_AVANCOU:              ("nome_crianca", "titulo_etapa"),
    ChaveTemplate.DOCUMENTO_PENDENTE:         ("nome_crianca", "pendencias"),
    ChaveTemplate.ACAO_PRESENCIAL:            ("nome_crianca", "nome_escola",
                                               "endereco", "prazo"),
    ChaveTemplate.CONVOCACAO:                 ("nome_crianca", "nome_escola", "prazo"),
    ChaveTemplate.LEMBRETE_CONVOCACAO:        ("nome_crianca", "nome_escola", "prazo"),
    ChaveTemplate.RESULTADO_CLASSIFICADA:     ("nome_crianca", "nome_escola"),
    ChaveTemplate.RESULTADO_NAO_CLASSIFICADA: ("nome_crianca",),
    ChaveTemplate.LEMBRETE_INCOMPLETO:        ("nome_responsavel",),
}

# Etapa mudou -> qual template disparar. Uma tabela, não uma cadeia de if.
#
# É aqui que o "vocabulário aberto, comportamento fechado" paga: o backend pode inventar
# a etapa "conferencia_presencial_2a_via" amanhã; se ela chegar como `acao_presencial`,
# o bot já sabe o que fazer. Zero código novo.
POR_TIPO_ETAPA: dict[TipoEtapa, ChaveTemplate] = {
    "aguardando":      ChaveTemplate.ETAPA_AVANCOU,
    "acao_no_chat":    ChaveTemplate.DOCUMENTO_PENDENTE,
    "acao_presencial": ChaveTemplate.ACAO_PRESENCIAL,
    "convocacao":      ChaveTemplate.CONVOCACAO,
    "concluida":       ChaveTemplate.RESULTADO_CLASSIFICADA,
    "encerrada":       ChaveTemplate.RESULTADO_NAO_CLASSIFICADA,
}
