"""A máquina de estados. Despacho por dict; comandos globais antes do passo.

Máquina explícita, não agente autônomo: determinística, testável, barata, e o usuário
nunca fica preso num loop. O roteiro completo está em `docs/ROTEIRO.md`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from creche_bot.backend.porta import BackendCreche
from creche_bot.canal.tipos import MensagemEntrada, MensagemSaida
from creche_bot.conversa.passos import (
    acompanhamento,
    busca,
    entrega,
    escolas,
    formulario_passo,
    resumo,
)
from creche_bot.conversa.sessao import Passo
from creche_bot.dados.porta import Repositorio
from creche_bot.ia.redacao import Redator

log = logging.getLogger(__name__)

PASSOS: dict[str, Callable[[Passo], MensagemSaida]] = {
    # bloco 0 e 1 — boas-vindas, consentimento, data lake
    "INICIO": busca.inicio,
    "CONSENTIMENTO": busca.consentimento,
    "BUSCA_CPF": busca.busca_cpf,
    "BUSCA_NASCIMENTO": busca.busca_nascimento,
    # blocos 2, 3 e 4 — formulário declarativo
    "FORMULARIO": formulario_passo.formulario,
    # bloco 5 — resumo e correção
    "RESUMO": resumo.confirmacao,
    "CORRECAO": resumo.correcao,
    # blocos 6 e 7 — escolas e ordem de preferência
    "LOCALIZACAO": escolas.localizacao,
    "ESCOLHA": escolas.escolha,
    "CONFIRMA_ESCOLAS": escolas.confirma_escolas,
    # bloco 8 — documentação e protocolo
    "ENTREGA": entrega.entrega,
    "RECEBER_DOCUMENTOS": entrega.receber_documentos,
    # pós-inscrição
    "ACOMPANHAMENTO": acompanhamento.acompanhamento,
}

# Estados em que dado de criança é tratado. Nenhum é alcançável sem consentimento
# registrado — LGPD art. 14, guarda no código e não confiança no fluxo.
EXIGEM_CONSENTIMENTO = frozenset(PASSOS) - {"INICIO", "CONSENTIMENTO"}

AJUDA = ("Sou o Zé Matrícula, da Matrícula Rio 💙\n\n"
         "/start para começar de novo\n"
         "/status para ver sua inscrição\n"
         "/apagar para apagar seus dados")


class Maquina:
    def __init__(self, backend: BackendCreche, redator: Redator,
                 repo: Repositorio) -> None:
        self._backend = backend
        self._redator = redator
        self._repo = repo

    def processar(self, msg: MensagemEntrada) -> MensagemSaida:
        contato_id = self._repo.contato_de(msg.canal, msg.id_externo)
        estado, dados = self._repo.carregar_sessao(contato_id)
        comando = (msg.texto or "").strip().lower()

        if comando == "/apagar":
            self._repo.apagar_tudo(contato_id)
            return MensagemSaida(self._redator.texto("apagado"))

        if comando == "/start":
            estado, dados = "INICIO", {}
        elif comando == "/ajuda":
            return MensagemSaida(AJUDA)
        elif comando == "/status":
            estado = "ACOMPANHAMENTO"
        elif comando == "/avancar":
            return self._avancar(dados)

        if estado in EXIGEM_CONSENTIMENTO and not self._repo.tem_consentimento(contato_id):
            estado, dados = "INICIO", {}      # sem autorização, volta ao começo

        passo = Passo(msg=msg, contato_id=contato_id, dados=dados,
                      backend=self._backend, redator=self._redator, repo=self._repo)
        try:
            resposta = PASSOS[estado](passo)
        except Exception:
            log.exception("passo %s falhou para o contato %s", estado, contato_id)
            return MensagemSaida(self._redator.texto("backend_fora"))

        self._repo.salvar_sessao(contato_id, passo.proximo or estado, passo.dados)
        return resposta

    def _avancar(self, dados: dict) -> MensagemSaida:
        """Só existe enquanto o backend é o mock: empurra a inscrição uma etapa e deixa o
        worker de outbox entregar a notificação de verdade.
        ponytail: sai junto com o BackendMock, na Fase 3."""
        protocolo = dados.get("protocolo")
        avancar = getattr(self._backend, "avancar", None)
        if not protocolo or avancar is None:
            return MensagemSaida("Nada para avançar — conclua uma inscrição antes.")
        avancar(protocolo)
        return MensagemSaida("Etapa avançada. A notificação chega em instantes 👀")
