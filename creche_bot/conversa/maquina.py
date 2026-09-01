"""A máquina de estados. Despacho por dict; comandos globais antes do passo.

Máquina explícita, não agente autônomo: determinística, testável, barata, e a família
nunca fica presa num loop. O roteiro completo está em `docs/ROTEIRO.md`.

Cada estado tem duas portas: `PASSOS[estado]` consome a resposta que chegou, e
`ENTRADAS[estado]` desenha a tela pela primeira vez. Correção e retomada usam a segunda:
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
from creche_bot.conversa import projecao
from creche_bot.conversa.formulario import campo_de
from creche_bot.conversa.passos import (
    consulta,
    criterios,
    demo,
    endereco,
    entrada,
    escolas,
    formulario_passo,
    ia,
    pendencias,
    responsavel,
    resumo,
)
from creche_bot.conversa.sessao import Passo, dizer
from creche_bot.dados.porta import Repositorio
from creche_bot.ia.redacao import Redator, criar

log = logging.getLogger(__name__)


def _etapa(estado: str, dados: dict) -> str:
    """O que o bot acabou de perguntar, para o classificador julgar a resposta.

    Só a pergunta ESTÁTICA do campo entra: `pergunta_alt` interpola nome da criança, e
    dado da família não vai para prompt nenhum. Estado sem formulário viaja só pelo nome,
    que já diz o suficiente ("ENDERECO_CEP", "HORARIO").
    """
    campo = campo_de(dados.get("perguntou", ""))
    return f"{estado}: {campo.pergunta}" if campo else estado


def abrir_contato(p: Passo) -> MensagemSaida:
    """Fim do bloco 3, começo do bloco 4."""
    p.ir("CONTATO")
    return formulario_passo.perguntar(p, "CONTATO", resumo.resumo)


def _cadastro(p: Passo) -> MensagemSaida:
    return formulario_passo.responder(p, "CADASTRO", abrir_contato)


def _contato(p: Passo) -> MensagemSaida:
    return formulario_passo.responder(p, "CONTATO", resumo.resumo)


def _consulta_nome(p: Passo) -> MensagemSaida:
    return formulario_passo.responder(p, "CONSULTA", consulta._buscar_por_nome)


def _fora_da_faixa(p: Passo) -> MensagemSaida:
    """Saída de exceção do bloco 4. Não deixe a família descobrir isso no resultado."""
    if p.msg.escolha == "outra":
        for chave in ("cpf_crianca", "nome_crianca", "nascimento_crianca", "grupamento",
                      "filiacao_consta", "filiacao", "origem", "origem_outra",
                      "matricula", "tem_especial", "tipo_especial", "tipo_especial_outro",
                      "perguntou"):
            p.dados.pop(chave, None)
        p.ir("CADASTRO")
        return formulario_passo.perguntar(p, "CADASTRO", abrir_contato)
    return MensagemSaida(p.txt("pre_escola"))


PASSOS: dict[str, Callable[[Passo], MensagemSaida]] = {
    # bloco 0.0: ligar a IA com a chave da pessoa, ou seguir sem ela
    "IA_CONFIG": ia.escolher,
    # blocos 0, 0.1 e 1: porta de entrada, retomada, consentimento
    "INICIO": entrada.porta,
    "PORTA": entrada.porta,
    "RETOMADA": entrada.retomar,
    "FORA_DO_PERIODO": entrada.fora_do_periodo,
    "CONSENTIMENTO": entrada.consentimento,
    # blocos 1, 2 e 3: pesquisa inicial, sobre a vaga e dados pessoais
    "CADASTRO": _cadastro,
    "CADASTRO_ANTERIOR": responsavel.cadastro_anterior,
    "FORA_DA_FAIXA": _fora_da_faixa,
    # bloco 4: contato
    "CONTATO": _contato,
    # bloco 5: resumo e correção
    "RESUMO": resumo.confirmacao,
    "CORRECAO": resumo.correcao,
    # bloco 6: endereço, horário e o painel de creches
    "ENDERECO_CEP": endereco.receber,
    "ENDERECO_CONFIRMA": endereco.confirmar,
    "HORARIO": escolas.horario,
    "ESCOLAS": escolas.escolher,
    # bloco 7: confirmação da escolha
    "CONFIRMA_ESCOLAS": escolas.escolhas_confirmadas,
    # a régua do processo vigente, antes da documentação que ela mesma pede
    "CRIT_CADUNICO": criterios.cadunico,
    "CRIT_NIS": criterios.nis,
    "CRIT_GATE": criterios.gate_sensivel,
    "CRIT_ESPECIAL": criterios.educacao_especial,
    "CRIT_FAMILIA": criterios.familia,
    "CRIT_IRMAO": criterios.irmao,
    "CRIT_SENSIVEL": criterios.sensivel,
    "CRIT_ANEXO": criterios.anexo,
    # bloco 8: documentação e protocolo
    "PENDENCIAS": pendencias.como_entregar,
    "RECEBER_DOC": pendencias.receber_documento,
    "PROTOCOLO": pendencias.depois_do_protocolo,
    # bloco C: consulta
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
    # Fora do roteiro: as três famílias prontas do `/demo`
    "DEMO": demo.escolher,
}

# Como REENTRAR num bloco: correção (bloco 11) e retomada (bloco 0.1) usam isto.
ENTRADAS: dict[str, Callable[[Passo], MensagemSaida]] = {
    "IA_CONFIG": ia.perguntar,
    "CADASTRO": lambda p: formulario_passo.perguntar(p, "CADASTRO", abrir_contato),
    "CONTATO": lambda p: formulario_passo.perguntar(p, "CONTATO", resumo.resumo),
    "ENDERECO_CEP": endereco.pedir_cep,
    "ENDERECO_CONFIRMA": endereco.confere,
    "CADASTRO_ANTERIOR": responsavel.confere_cadastro,
    "HORARIO": escolas.pedir_horario,
    "CRIT_CADUNICO": criterios.comecar,
    "CRIT_NIS": criterios.reabrir_nis,
    "CRIT_ANEXO": criterios.reabrir_anexo,
    "ESCOLAS": escolas.sugerir,
    "CONFIRMA_ESCOLAS": escolas.confirmar_escolhas,
    "RESUMO": resumo.resumo,
    "INICIO": entrada.inicio,
    # A mesma função dos PASSOS: ela já desenha. A linha existe para `_reorientar` poder
    # redesenhar o menu com o "me perdi" de quem digitou fora, como no resto do roteiro.
    "DEMO": demo.escolher,
}


def entrar(p: Passo, estado: str) -> MensagemSaida:
    """Desenha a tela do estado. Cai no handler normal quando não há entrada própria."""
    return ENTRADAS.get(estado, PASSOS[estado])(p)


# Estados em que dado de criança é TRATADO para inscrever. Nenhum é alcançável sem o
# consentimento do bloco 1: LGPD art. 14, guarda no código e não confiança no fluxo.
#
# Os `CONSULTA_*` ficam de fora de propósito: consultar a própria inscrição é exercício
# do direito de acesso (art. 18), não tratamento novo, e exigir o consentimento de
# inscrição ali barraria justamente quem se inscreveu pelo site. O consentimento de
# comunicação é pedido no C.5, antes de qualquer mensagem proativa.
#
# CONSULTA_DOC é a exceção dentro da exceção: ali a família manda um documento NOVO para
# o backend guardar, o que é tratamento (LGPD art. 14: "nenhum documento é aceito antes do
# consentimento registrado"), não leitura — fica de fora da isenção do bloco C, e cai no
# mesmo gate dos outros blocos. CONSULTA_NIS continua isenta: é número, não documento, e
# resolve uma pendência de uma inscrição já achada por consulta, o mesmo direito de acesso
# que justifica o resto do bloco C.
LIVRES = {"INICIO", "PORTA", "RETOMADA", "CONSENTIMENTO", "FORA_DO_PERIODO", "ACOMPANHAR",
          "IA_CONFIG", "DEMO"}
CONSULTA_TRATAM_DADO_NOVO = {"CONSULTA_DOC"}
EXIGEM_CONSENTIMENTO = frozenset(
    e for e in PASSOS
    if e not in LIVRES and (not e.startswith("CONSULTA_") or e in CONSULTA_TRATAM_DADO_NOVO))

# `/start` recomeça o cadastro, e não é para apagar a inscrição que já existe: sem isto,
# quem manda /start por hábito perde o número e o /status responde "você não tem
# inscrição". Enquanto `dados/porta.py` não souber buscar inscrição por contato, a
# sessão é o único lugar onde o número mora.
#
# `chave_ia` e `ia_dispensada` entram na lista por outro motivo: são a decisão da pessoa
# sobre a IA, não parte do cadastro. Recomeçar a conversa não pode desligar a IA que ela
# acabou de ligar, nem perguntar de novo o que ela já respondeu no bloco 0.0.
PRESERVAR = ("numero", "nome_crianca", "nascimento_crianca", *ia.CHAVES_DECISAO)

# Os ids de botão que `notificacao/catalogo.py` emite, e o estado que cada um abre. Eles
# são o único botão do sistema sem dono numa tela: chegam por push, fora de qualquer
# conversa em curso, e por isso o despacho por estado não os alcança. `retomar` fica de
# fora porque é tratado junto do `/start`, que já sabe desenhar a retomada.
DA_NOTIFICACAO = {
    "confirmar_vaga": "ACOMPANHAR",
    "nao_vou_poder": "ACOMPANHAR",
    "avisar_proximo": "ACOMPANHAR",
}

# Teto de perguntas livres por contato. Cada uma é uma chamada paga ao modelo, e um chat
# aberto na internet é um botão de gastar dinheiro dos outros. Estourou a cota, a mensagem
# volta a ser tratada como resposta do roteiro. O cadastro continua, só a IA descansa.
LIMITE_DUVIDAS = 8
JANELA_DUVIDAS = 3600.0

AJUDA = ("Sou o Zé Matrícula, da Matrícula Carioca\n\n"
         "/start para começar\n"
         "/status para ver sua inscrição\n"
         "/ia para ligar a conversa com IA\n"
         "/apagar para apagar seus dados\n"
         "/demo para ver o bot com dados de exemplo\n\n"
         "Prefere falar com uma pessoa? Ligue 1746.")


def _preservar(dados: dict) -> dict:
    return {c: dados[c] for c in PRESERVAR if c in dados}


class Maquina:
    def __init__(self, backend: BackendCreche, redator: Redator, repo: Repositorio,
                 transcritor: Callable[[bytes], str | None] | None = None) -> None:
        self._backend = backend
        self._redator = redator
        self._repo = repo
        self._transcritor = transcritor
        self._duvidas: dict[str, list[float]] = {}
        self._por_chave: dict[str, Redator] = {}   # um cliente por chave, não por turno
        self._ia_avisados: set[str] = set()        # quem já soube que a IA dele caiu
        self._perdidos: set[str] = set()   # quem já foi reorientado na última mensagem

    def processar(self, msg: MensagemEntrada) -> MensagemSaida:
        # Voz vira texto antes de qualquer decisão: quem falou segue o mesmo caminho de
        # quem digitou, e nenhum passo precisa saber que existe áudio.
        if msg.anexo is not None and msg.anexo.mime.startswith("audio/"):
            ouvido = self._transcritor(msg.anexo.conteudo) if self._transcritor else None
            if not ouvido:
                return dizer(self._redator, "audio_sem_texto")
            msg = replace(msg, texto=ouvido, anexo=None)

        contato_id = self._repo.contato_de(msg.canal, msg.id_externo)
        estado, dados = self._repo.carregar_sessao(contato_id)
        # `.lower()` só na cópia que vira comando: a chave da Anthropic tem maiúsculas.
        digitado = (msg.texto or "").strip()
        comando = digitado.lower()
        redator = self._redator_de(dados)

        if comando == "/apagar":
            self._repo.apagar_tudo(contato_id)
            return dizer(redator, "apagado")

        # Sessão de 72h. Passou disso, a conversa recomeça limpa, mas a inscrição que
        # já existe sobrevive, senão o /status responde que ela não existe.
        if entrada.sessao_expirada(dados):
            estado, dados = "INICIO", _preservar(dados)

        # Configuração da IA, em qualquer ponto do roteiro. A chave colada SOZINHA entra
        # pelo mesmo caminho de propósito: sem isto ela seguiria como resposta do campo
        # que estava no ar, gravada como se fosse um nome, e ecoada de volta na tela.
        if (pedido := ia.pedido_de_configuracao(digitado)) is not None:
            try:
                return ia.comando(self._montar(msg, contato_id, dados, redator),
                                  estado, pedido)
            except Exception:
                # Banco fora no meio de um `/ia` deixaria a pessoa sem resposta nenhuma,
                # e ela não tem como saber se a chave entrou ou não.
                log.exception("configuração da IA falhou para o contato %s", contato_id)
                return dizer(redator, "backend_fora")

        # `/start` no meio da conversa DESENHA a retomada; não consome "/start" como se
        # fosse resposta de botão. Era o bug que fazia o bot responder "não entendi".
        retomar_de = None
        if comando == "/start" or msg.escolha == "retomar":
            if estado in entrada.ONDE_PAROU:
                retomar_de, estado = estado, "RETOMADA"
            else:
                estado, dados = "INICIO", _preservar(dados)
        elif comando == "/ajuda":
            return MensagemSaida(AJUDA, figurinha="coracao")
        elif comando == "/status":
            estado = "ACOMPANHAR"
        elif comando == "/avancar":
            return self._avancar(dados)
        elif comando == "/demo":
            estado = "DEMO"

        # Botão que veio numa NOTIFICAÇÃO, não da tela que está no ar. Ele chega dias ou
        # meses depois — a convocação de junho responde a uma inscrição de março — e aí a
        # sessão de 72h já expirou e o estado voltou para `INICIO` logo acima. Sem este
        # roteamento, quem apertava "Confirmar vaga" recebia a saudação ("quer inscrever
        # uma criança?") com o prazo da convocação correndo: o vazamento dos 7,7% que a
        # notificação existe justamente para fechar.
        #
        # Vai para `ACOMPANHAR` e não direto para a confirmação porque a tela de situação
        # é quem carrega a inscrição do backend e redesenha os botões com os ids que
        # `passos/consulta.py` trata. Um toque a mais, e nenhum estado inventado aqui.
        if msg.escolha in DA_NOTIFICACAO:
            estado = DA_NOTIFICACAO[msg.escolha]

        if estado in EXIGEM_CONSENTIMENTO and not self._repo.tem_consentimento(contato_id):
            estado, dados = "INICIO", {}      # sem autorização, volta ao começo

        # Bloco 0.0, antes do roteiro: quem nunca decidiu sobre a IA decide agora. É uma
        # tela só, e ninguém fica preso nela, porque `ia.escolher` segue com qualquer resposta.
        # ponytail: sai junto com a chave por contato, quando o bot voltar a ter chave de
        # plataforma. Ver docs/DECISOES.md D20.
        desenhar_ia = estado == "INICIO" and ia.precisa_escolher(dados)
        if desenhar_ia:
            estado = "IA_CONFIG"

        dados["visto_em"] = datetime.now().isoformat(timespec="seconds")
        passo = self._montar(msg, contato_id, dados, redator)
        try:
            # Sai do roteiro sem SALVAR nada: quem perguntou ou se perdeu não perde o
            # lugar na fila, e a próxima mensagem cai no mesmo estado.
            if (fora := self._fora_do_roteiro(passo, estado)) is not None:
                return self._com_aviso(contato_id, redator, fora)
            self._perdidos.discard(contato_id)
            if retomar_de:
                resposta = entrada.retomada(passo, retomar_de)
            elif desenhar_ia:
                resposta = entrar(passo, estado)   # DESENHA a tela; não consome a mensagem
            else:
                resposta = self._executar(passo, estado)
        except Exception:
            log.exception("passo %s falhou para o contato %s", estado, contato_id)
            return dizer(redator, "backend_fora")

        self._repo.salvar_sessao(contato_id, passo.proximo or estado, passo.dados)
        self._projetar(contato_id, passo.dados)
        return self._com_aviso(contato_id, redator, resposta)

    def _montar(self, msg: MensagemEntrada, contato_id: str, dados: dict,
                redator: Redator) -> Passo:
        return Passo(msg=msg, contato_id=contato_id, dados=dados,
                     backend=self._backend, redator=redator, repo=self._repo)

    def _com_aviso(self, contato_id: str, redator: Redator,
                   resposta: MensagemSaida) -> MensagemSaida:
        """A chave da pessoa falhou no meio do turno? Ela fica sabendo, uma vez por queda.

        O cadastro não para: o `RedatorClaude` cai para o texto pronto sozinho. O que não
        pode é a pessoa achar que a IA dela está funcionando enquanto o bot responde seco.
        Repetir o aviso a cada mensagem seria a falha oposta, então ele só volta depois
        que a IA voltar a responder.
        """
        aviso = ia.aviso_de_falha(redator)
        if aviso is None:
            self._ia_avisados.discard(contato_id)
            return resposta
        if contato_id in self._ia_avisados:
            return resposta
        if len(self._ia_avisados) > 5_000:     # mesmo motivo do clear das cotas
            self._ia_avisados.clear()
        self._ia_avisados.add(contato_id)
        # Em cima, não embaixo: toda tela do bot termina na pergunta, e um aviso depois
        # dela empurraria a pergunta para o meio da mensagem.
        return replace(resposta, texto=f"{aviso}\n\n{resposta.texto}")

    def _redator_de(self, dados: dict) -> Redator:
        """A IA é do contato, não do processo: cada um liga a sua chave com `/ia`.

        O cliente fica cacheado por chave, porque montar um a cada turno abriria conexão nova
        por mensagem. `clear` pelo mesmo motivo das cotas: dicionário que só cresce.
        """
        chave = dados.get("chave_ia")
        if not chave:
            return self._redator
        if chave not in self._por_chave:
            if len(self._por_chave) > 500:
                self._por_chave.clear()
            try:
                self._por_chave[chave] = criar(chave)
            except Exception:      # anthropic não instalado, por exemplo
                log.exception("não consegui montar o redator da chave do contato")
                return self._redator
        return self._por_chave[chave]

    def _projetar(self, contato_id: str, dados: dict) -> None:
        """Espelha o contexto nas colunas consultáveis. Nunca derruba a conversa.

        A sessão já foi salva quando isto roda: se a projeção falhar, o diálogo continua
        de onde estava e só o espelho fica para trás. O contrário, perder o turno da
        família porque uma coluna nova não existia ainda, seria trocar o produto pelo
        relatório.
        """
        try:
            if (cadastro := projecao.cadastro_de(contato_id, dados)) is not None:
                self._repo.salvar_cadastro(cadastro)
        except Exception:
            log.exception("projeção do cadastro falhou para o contato %s", contato_id)

    def _executar(self, passo: Passo, estado: str) -> MensagemSaida:
        if estado in ("INICIO", "ACOMPANHAR"):
            return entrar(passo, estado) if estado == "INICIO" else PASSOS[estado](passo)
        return PASSOS[estado](passo)

    def _fora_do_roteiro(self, passo: Passo, estado: str) -> MensagemSaida | None:
        """Toda mensagem digitada passa por aqui antes de virar resposta de campo.

        A pessoa está respondendo, perguntando, ou se perdeu? `None` = segue o roteiro.
        Só a etapa e a pergunta estática vão para o modelo, e nada do que a família já
        contou precisa estar lá para decidir isso.
        """
        texto = passo.texto
        if passo.msg.escolha or not texto or texto.startswith("/"):
            return None      # botão e comando já têm dono; classificar seria gastar à toa
        if estado == "IA_CONFIG":
            return None      # quem está configurando a IA não está respondendo o roteiro

        etapa = _etapa(estado, passo.dados)
        intencao = passo.redator.classificar(texto, etapa).intencao

        if intencao == "duvida":
            if not self._cota(passo.contato_id):
                return None
            resposta = passo.redator.responder_duvida(texto, etapa)
            if resposta:
                return MensagemSaida(resposta)
            # Sem chave não há resposta livre. Dizer como ligar é melhor que devolver a
            # pergunta ao roteiro, onde ela vira "não entendi" no campo seguinte. A cota
            # vale aqui também: passadas as 8, o aviso para de repetir.
            return None if passo.dados.get("chave_ia") else MensagemSaida(ia.SEM_IA)
        if intencao == "fora_de_contexto":
            return self._reorientar(passo, estado)
        return None

    def _reorientar(self, passo: Passo, estado: str) -> MensagemSaida | None:
        """Veio coisa que não responde a pergunta: repete a pergunta, sem contar erro.

        Duas vezes seguidas seria loop: classificador que erra prenderia a família fora
        do cadastro. Na segunda, deixa passar: `_errar` sabe reclamar sozinho, conta as
        três tentativas e oferece a CRE. Estado sem tela de reentrada também passa, porque
        redesenhar ali significaria chamar o handler, que CONSOME a mensagem.
        """
        if estado not in ENTRADAS or passo.contato_id in self._perdidos:
            return None
        if len(self._perdidos) > 5_000:      # quem some no meio nunca sai daqui sozinho
            self._perdidos.clear()
        self._perdidos.add(passo.contato_id)
        tela = entrar(passo, estado)
        return replace(tela, texto=f"{passo.txt('me_perdi')}\n\n{tela.texto}")

    def _cota(self, contato_id: str) -> bool:
        """Janela deslizante de uma hora, por contato.

        ponytail: dicionário em memória, um processo só. Some junto com o processo, e é
        exatamente por isso que existe o `clear`, para não virar vazamento no dia do pico.
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
        from creche_bot.backend.mock import BackendMock

        # `type(...) is`, não `isinstance`: `BackendMapa` HERDA de `BackendMock` e por isso
        # herda o `avancar`. A guarda antiga (`avancar is None`) nunca disparava em
        # produção, e qualquer família que digitasse /avancar depois de se inscrever
        # receberia R1 a R4 até "Vaga confirmada" — mentira sobre vaga em creche pública.
        if type(self._backend) is not BackendMock:
            return MensagemSaida("Esse comando não existe por aqui.")

        numero = dados.get("numero")
        avancar = getattr(self._backend, "avancar", None)
        if not numero or avancar is None:
            return MensagemSaida("Nada para avançar. Conclua uma inscrição antes.")
        try:
            avancar(numero)
        except KeyError:
            # O serviço reiniciou e o mock recomeçou vazio. Sem esta guarda a exceção sobe
            # até o canal e o bot fica MUDO, que é o pior jeito de falhar numa demonstração.
            return MensagemSaida("Essa inscrição saiu da memória do serviço. "
                                 "Faça outra com /demo ou /start.")
        return MensagemSaida("Etapa avançada. A notificação chega em instantes 👀")
