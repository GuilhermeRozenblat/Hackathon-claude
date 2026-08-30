"""A máquina de estados. Despacho por dict; comandos globais antes do passo.

Máquina explícita, não agente autônomo: determinística, testável, barata, e a família
nunca fica presa num loop. O roteiro completo está em `docs/ROTEIRO.md`.

Cada estado tem duas portas: `PASSOS[estado]` consome a resposta que chegou, e
`ENTRADAS[estado]` desenha a tela pela primeira vez. Correção e retomada usam a segunda —
sem ela, voltar a um bloco engole a próxima mensagem da família.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from creche_bot.backend.porta import BackendCreche
from creche_bot.canal.tipos import MensagemEntrada, MensagemSaida
from creche_bot.conversa.passos import (
    consulta,
    criterios,
    endereco,
    entrada,
    escolas,
    formulario_passo,
    pendencias,
    responsavel,
    resumo,
)
from creche_bot.conversa.sessao import Passo
from creche_bot.dados.porta import Repositorio
from creche_bot.ia.redacao import Redator

log = logging.getLogger(__name__)


def _cadastro(p: Passo) -> MensagemSaida:
    return formulario_passo.responder(p, "CADASTRO", endereco.pedir_cep)


def _contato(p: Passo) -> MensagemSaida:
    return formulario_passo.responder(p, "CONTATO", escolas.sugerir)


def _consulta_nome(p: Passo) -> MensagemSaida:
    return formulario_passo.responder(p, "CONSULTA", consulta._buscar_por_nome)


def _fora_da_faixa(p: Passo) -> MensagemSaida:
    """Saída de exceção do bloco 4. Não deixe a família descobrir isso no resultado."""
    if p.msg.escolha == "outra":
        for chave in ("nome_crianca", "nascimento_crianca", "grupamento", "sexo",
                      "filiacao_consta", "filiacao", "documento_crianca", "perguntou"):
            p.dados.pop(chave, None)
        p.ir("CADASTRO")
        return formulario_passo.perguntar(p, "CADASTRO", endereco.pedir_cep)
    return MensagemSaida(p.txt("pre_escola"))


PASSOS: dict[str, Callable[[Passo], MensagemSaida]] = {
    # blocos 0, 0.1 e 1 — porta de entrada, retomada, consentimento
    "INICIO": entrada.porta,
    "PORTA": entrada.porta,
    "RETOMADA": entrada.retomar,
    "FORA_DO_PERIODO": entrada.fora_do_periodo,
    "CONSENTIMENTO": entrada.consentimento,
    # blocos 2 e 2a — o responsável é a âncora
    "CPF_RESPONSAVEL": responsavel.cpf_responsavel,
    "CADASTRO_ANTERIOR": responsavel.cadastro_anterior,
    # blocos 3, 4 e 5 — cadastro declarativo
    "CADASTRO": _cadastro,
    "FORA_DA_FAIXA": _fora_da_faixa,
    # bloco 6 — endereço por CEP e número
    "ENDERECO_CEP": endereco.receber,
    "ENDERECO_CONFIRMA": endereco.confirmar,
    # bloco 7 — horário
    "HORARIO": escolas.horario,
    # bloco 8 — a régua do processo vigente
    "CRIT_CADUNICO": criterios.cadunico,
    "CRIT_NIS": criterios.nis,
    "CRIT_GATE": criterios.gate_sensivel,
    "CRIT_ESPECIAL": criterios.educacao_especial,
    "CRIT_FAMILIA": criterios.familia,
    "CRIT_IRMAO": criterios.irmao,
    "CRIT_SENSIVEL": criterios.sensivel,
    "CRIT_ANEXO": criterios.anexo,
    # bloco 9 — contato
    "CONTATO": _contato,
    # bloco 10 — escolha das creches
    "ESCOLAS": escolas.escolher,
    # bloco 11 — resumo e correção
    "RESUMO": resumo.confirmacao,
    "CORRECAO": resumo.correcao,
    # blocos 12 e 13 — comprovação e protocolo
    "PENDENCIAS": pendencias.como_entregar,
    "RECEBER_DOC": pendencias.receber_documento,
    "PROTOCOLO": pendencias.depois_do_protocolo,
    # bloco C — consulta
    "ACOMPANHAR": consulta.acompanhar,
    "CONSULTA_COMO": consulta.como,
    "CONSULTA_NUMERO": consulta.por_numero,
    "CONSULTA_NOME": _consulta_nome,
    "CONSULTA_ESCOLHER": consulta.escolher,
    "CONSULTA_CONFIRMAR": consulta.confirmar_vaga,
    "CONSULTA_PENDENCIA": consulta.pendencia,
    "CONSULTA_NIS": consulta.nis,
    "CONSULTA_AVISOS": consulta.avisos,
    "CONSULTA_ACOES": consulta.escolher_acao,
    "CONSULTA_TELEFONE": consulta.novo_telefone,
    "CONSULTA_DOC": consulta.receber_doc,
    "CONSULTA_NAO_ACHOU": consulta.nao_achou,
}

# Como REENTRAR num bloco: correção (bloco 11) e retomada (bloco 0.1) usam isto.
ENTRADAS: dict[str, Callable[[Passo], MensagemSaida]] = {
    "CADASTRO": lambda p: formulario_passo.perguntar(p, "CADASTRO", endereco.pedir_cep),
    "CONTATO": lambda p: formulario_passo.perguntar(p, "CONTATO", escolas.sugerir),
    "ENDERECO_CEP": endereco.pedir_cep,
    "HORARIO": escolas.pedir_horario,
    "CRIT_CADUNICO": criterios.comecar,
    "ESCOLAS": escolas.sugerir,
    "RESUMO": resumo.resumo,
    "CPF_RESPONSAVEL": responsavel.pedir_cpf,
    "INICIO": entrada.inicio,
}


def entrar(p: Passo, estado: str) -> MensagemSaida:
    """Desenha a tela do estado. Cai no handler normal quando não há entrada própria."""
    return ENTRADAS.get(estado, PASSOS[estado])(p)


# Estados em que dado de criança é TRATADO para inscrever. Nenhum é alcançável sem o
# consentimento do bloco 1 — LGPD art. 14, guarda no código e não confiança no fluxo.
#
# Os `CONSULTA_*` ficam de fora de propósito: consultar a própria inscrição é exercício
# do direito de acesso (art. 18), não tratamento novo, e exigir o consentimento de
# inscrição ali barraria justamente quem se inscreveu pelo site. O consentimento de
# comunicação é pedido no C.5, antes de qualquer mensagem proativa.
LIVRES = {"INICIO", "PORTA", "RETOMADA", "CONSENTIMENTO", "FORA_DO_PERIODO", "ACOMPANHAR"}
EXIGEM_CONSENTIMENTO = frozenset(
    e for e in PASSOS if e not in LIVRES and not e.startswith("CONSULTA_"))

# `/start` recomeça o cadastro, e não é para apagar a inscrição que já existe: sem isto,
# quem manda /start por hábito perde o número e o /status responde "você não tem
# inscrição". Enquanto `dados/porta.py` não souber buscar inscrição por contato, a
# sessão é o único lugar onde o número mora.
INSCRICAO_EM_ANDAMENTO = ("numero", "nome_crianca", "nascimento_crianca")

# Teto de perguntas livres por contato. Cada uma é uma chamada paga ao modelo, e um chat
# aberto na internet é um botão de gastar dinheiro dos outros. Estourou a cota, a mensagem
# volta a ser tratada como resposta do roteiro — o cadastro continua, só a IA descansa.
LIMITE_DUVIDAS = 8
JANELA_DUVIDAS = 3600.0

AJUDA = ("Sou o Zé Matrícula, da Matrícula Carioca 💙\n\n"
         "/start para começar\n"
         "/status para ver sua inscrição\n"
         "/apagar para apagar seus dados\n\n"
         "Prefere falar com uma pessoa? Ligue 1746.")


def _guardar_inscricao(dados: dict) -> dict:
    return {c: dados[c] for c in INSCRICAO_EM_ANDAMENTO if c in dados}


class Maquina:
    def __init__(self, backend: BackendCreche, redator: Redator, repo: Repositorio,
                 transcritor: Callable[[bytes], str | None] | None = None) -> None:
        self._backend = backend
        self._redator = redator
        self._repo = repo
        self._transcritor = transcritor
        self._duvidas: dict[str, list[float]] = {}

    def processar(self, msg: MensagemEntrada) -> MensagemSaida:
        # Voz vira texto antes de qualquer decisão: quem falou segue o mesmo caminho de
        # quem digitou, e nenhum passo precisa saber que existe áudio.
        if msg.anexo is not None and msg.anexo.mime.startswith("audio/"):
            ouvido = self._transcritor(msg.anexo.conteudo) if self._transcritor else None
            if not ouvido:
                return MensagemSaida(self._redator.texto("audio_sem_texto"))
            msg = replace(msg, texto=ouvido, anexo=None)

        contato_id = self._repo.contato_de(msg.canal, msg.id_externo)
        estado, dados = self._repo.carregar_sessao(contato_id)
        comando = (msg.texto or "").strip().lower()

        if comando == "/apagar":
            self._repo.apagar_tudo(contato_id)
            return MensagemSaida(self._redator.texto("apagado"))

        # Sessão de 72h. Passou disso, a conversa recomeça limpa — mas a inscrição que
        # já existe sobrevive, senão o /status responde que ela não existe.
        if entrada.sessao_expirada(dados):
            estado, dados = "INICIO", _guardar_inscricao(dados)

        # `/start` no meio da conversa DESENHA a retomada; não consome "/start" como se
        # fosse resposta de botão. Era o bug que fazia o bot responder "não entendi".
        retomar_de = None
        if comando == "/start":
            if estado in entrada.ONDE_PAROU:
                retomar_de, estado = estado, "RETOMADA"
            else:
                estado, dados = "INICIO", _guardar_inscricao(dados)
        elif comando == "/ajuda":
            return MensagemSaida(AJUDA)
        elif comando == "/status":
            estado = "ACOMPANHAR"
        elif comando == "/avancar":
            return self._avancar(dados)

        if estado in EXIGEM_CONSENTIMENTO and not self._repo.tem_consentimento(contato_id):
            estado, dados = "INICIO", {}      # sem autorização, volta ao começo

        if (duvida := self._duvida(msg, estado, contato_id)) is not None:
            return duvida     # estado intacto: perguntar não faz perder o lugar na fila

        dados["visto_em"] = datetime.now().isoformat(timespec="seconds")
        passo = Passo(msg=msg, contato_id=contato_id, dados=dados,
                      backend=self._backend, redator=self._redator, repo=self._repo)
        try:
            resposta = (entrada.retomada(passo, retomar_de) if retomar_de
                        else self._executar(passo, estado))
        except Exception:
            log.exception("passo %s falhou para o contato %s", estado, contato_id)
            return MensagemSaida(self._redator.texto("backend_fora"))

        self._repo.salvar_sessao(contato_id, passo.proximo or estado, passo.dados)
        return resposta

    def _executar(self, passo: Passo, estado: str) -> MensagemSaida:
        if estado in ("INICIO", "ACOMPANHAR"):
            return entrar(passo, estado) if estado == "INICIO" else PASSOS[estado](passo)
        return PASSOS[estado](passo)

    def _duvida(self, msg: MensagemEntrada, estado: str,
                contato_id: str) -> MensagemSaida | None:
        """Pergunta solta no meio do cadastro. `None` = não é dúvida, segue o roteiro.

        Só o nome da etapa vai para o modelo. Nada do que a família já contou — CPF, nome
        da criança, endereço — precisa estar lá para responder "como funciona a fila".
        """
        if msg.escolha or not msg.texto:
            return None
        if self._redator.classificar(msg.texto, estado).intencao != "duvida":
            return None
        if not self._cota(contato_id):
            return None
        resposta = self._redator.responder_duvida(msg.texto, estado)
        return MensagemSaida(resposta) if resposta else None

    def _cota(self, contato_id: str) -> bool:
        """Janela deslizante de uma hora, por contato.

        ponytail: dicionário em memória, um processo só. Some junto com o processo, e é
        exatamente por isso que existe o `clear` — não vira vazamento no dia do pico.
        """
        agora = time.monotonic()
        if len(self._duvidas) > 5_000:
            self._duvidas.clear()
        janela = [t for t in self._duvidas.get(contato_id, ()) if agora - t < JANELA_DUVIDAS]
        if len(janela) >= LIMITE_DUVIDAS:
            log.warning("contato %s estourou a cota de dúvidas", contato_id)
            self._duvidas[contato_id] = janela
            return False
        self._duvidas[contato_id] = [*janela, agora]
        return True

    def _avancar(self, dados: dict) -> MensagemSaida:
        """Só existe enquanto o backend é o mock: empurra a inscrição uma etapa e deixa o
        worker de outbox entregar a notificação de verdade.
        ponytail: sai junto com o BackendMock, na Fase 3."""
        numero = dados.get("numero")
        avancar = getattr(self._backend, "avancar", None)
        if not numero or avancar is None:
            return MensagemSaida("Nada para avançar — conclua uma inscrição antes.")
        avancar(numero)
        return MensagemSaida("Etapa avançada. A notificação chega em instantes 👀")
