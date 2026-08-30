"""CONTRATO CONGELADO — Fase 0.1.

Toda mensagem PROATIVA é (ChaveTemplate, variáveis). Nunca uma string pronta.

No Telegram a chave vira texto divertido com figurinha. No WhatsApp vira template aprovado
pela Meta — que não aceita texto livre nem figurinha fora da janela de 24h, leva ~24h para
aprovar, e é pago. Se o emissor gravasse a string pronta, o flip seria impossível.

## Mudar este enum é grátis AGORA e caro depois

Cada chave = um template submetido à Meta na Fase 3. Antes disso, mexer aqui custa um
commit. Depois, custa 24h de aprovação por chave. Acerte agora.
"""

from enum import StrEnum

from creche_bot.dominio.tipos import TipoEtapa


class ChaveTemplate(StrEnum):
    INSCRICAO_CONFIRMADA = "inscricao_confirmada"
    ETAPA_AVANCOU = "etapa_avancou"            # andou, e não precisa fazer nada
    PENDENCIA_NO_CHAT = "pendencia_no_chat"    # falta mandar documento por aqui
    ACAO_PRESENCIAL = "acao_presencial"        # precisa ir até a unidade
    RESULTADO_APROVADO = "resultado_aprovado"
    RESULTADO_RECUSADO = "resultado_recusado"
    LEMBRETE_INCOMPLETO = "lembrete_incompleto"


# Variáveis obrigatórias por chave. O catálogo valida contra isto ANTES de renderizar:
# template do WhatsApp com variável faltando é erro em produção, não no deploy.
VARIAVEIS: dict[ChaveTemplate, tuple[str, ...]] = {
    ChaveTemplate.INSCRICAO_CONFIRMADA: ("nome_crianca", "nome_escola", "protocolo"),
    ChaveTemplate.ETAPA_AVANCOU:        ("nome_crianca", "titulo_etapa", "ordem", "total"),
    ChaveTemplate.PENDENCIA_NO_CHAT:    ("nome_crianca", "pendencias", "prazo"),
    ChaveTemplate.ACAO_PRESENCIAL:      ("nome_crianca", "nome_escola", "endereco", "prazo"),
    ChaveTemplate.RESULTADO_APROVADO:   ("nome_crianca", "nome_escola"),
    ChaveTemplate.RESULTADO_RECUSADO:   ("nome_crianca", "nome_escola"),
    ChaveTemplate.LEMBRETE_INCOMPLETO:  ("nome_responsavel",),
}

# Etapa mudou -> qual template disparar. Uma tabela, não uma cadeia de if.
#
# É aqui que o "vocabulário aberto, comportamento fechado" paga: o backend pode inventar
# a etapa "conferencia_presencial_2a_via" amanhã; se ela chegar como `acao_presencial`,
# o bot já sabe o que fazer. Zero código novo.
POR_TIPO_ETAPA: dict[TipoEtapa, ChaveTemplate] = {
    "aguardando":      ChaveTemplate.ETAPA_AVANCOU,
    "acao_no_chat":    ChaveTemplate.PENDENCIA_NO_CHAT,
    "acao_presencial": ChaveTemplate.ACAO_PRESENCIAL,
    "concluida":       ChaveTemplate.RESULTADO_APROVADO,
    "encerrada":       ChaveTemplate.RESULTADO_RECUSADO,
}
