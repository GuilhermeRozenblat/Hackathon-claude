"""Bloco 0.0: a IA é de quem conversa, e a tela que pergunta isso.

Por enquanto o Claude roda com a chave da própria pessoa (ver `docs/DECISOES.md` D20):
quem hospeda o bot não paga a conta de ninguém. Então, antes do roteiro, uma pergunta só,
ligar a IA ou seguir sem ela, e um caminho fechado para cada resposta:

    ligar    → instruções em três passos, chave colada, teste na hora, motivo se falhar
    sem IA   → segue o roteiro com as respostas prontas, e `/ia` liga quando ela quiser
    ignorar  → ninguém fica preso numa tela de configuração: segue, avisando que seguiu

Nada aqui passa pelo redator. Texto de configuração carrega comando (`/ia`), endereço
(`console.anthropic.com`) e prefixo de chave (`sk-ant-`); o modelo reescrevendo isso
estragaria justamente a instrução que a pessoa precisa seguir à risca.
"""

from __future__ import annotations

from dataclasses import replace

from creche_bot.canal.tipos import Botao, MensagemSaida
from creche_bot.conversa.passos import entrada
from creche_bot.conversa.sessao import Passo
from creche_bot.ia.redacao import diagnosticar
from creche_bot.segredos import CHAVE_API  # o formato da chave, definido num lugar só

COMANDOS = {"/ia", "/chave"}
# O que a pessoa decidiu sobre a IA. Não é parte do cadastro, então sobrevive a tudo que
# recomeça a conversa: `/start`, sessão expirada, "começar de novo" e "outra criança".
CHAVES_DECISAO = ("chave_ia", "ia_dispensada")
DESLIGAR = {"remover", "apagar", "desligar", "off", "nao", "não", "sair"}

BOTAO_SEM_IA = Botao("sem_ia", "Seguir sem IA")
BOTOES_ESCOLHA = (Botao("ligar_ia", "Ligar a IA"), BOTAO_SEM_IA)

# ------------------------------------------------------------------------ textos

PASSOS_CHAVE = ("1. Abra console.anthropic.com/settings/keys e entre na sua conta\n"
                "2. Toque em Create Key e copie a chave (ela começa com sk-ant-)\n"
                "3. Cole a chave aqui na conversa")

ESCOLHA = ("Oi! Eu sou o Zé Matrícula, da Matrícula Carioca 👋\n\n"
           "Antes de começar: eu posso conversar com IA, e por enquanto ela roda com a "
           "chave da Anthropic de quem usa, assim ninguém paga a conta pelos outros.\n\n"
           "Com IA eu entendo pergunta solta e falo mais solto. Sem ela eu sigo o roteiro "
           "com as respostas prontas, e o cadastro funciona igual.\n\n"
           "Como você prefere?")

COMO_LIGAR = (f"Combinado. São três passos:\n\n{PASSOS_CHAVE}\n\n"
              "Eu testo a chave na hora e te digo se funcionou. Se preferir deixar isso "
              "para depois, toque em Seguir sem IA.")

DESLIGADA = ("A IA está desligada. Eu sigo o roteiro com as respostas prontas, e o "
             f"cadastro funciona igual.\n\nPara ligar com a sua chave da Anthropic:\n\n"
             f"{PASSOS_CHAVE}\n\nEu testo a chave na hora e te digo se funcionou.")

LIGADA = ("Testei sua chave e funcionou 🔑\n\n"
          "Apague aí no chat a mensagem em que você colou a chave. Ela já está guardada "
          "aqui do meu lado. Para desligar depois: /ia remover")

FALHOU = ("Testei sua chave e não deu certo: {motivo}.\n\n"
          "Você pode colar outra chave aqui, ou seguir sem IA, o cadastro funciona igual.")

SEM_IA_OK = "Beleza, seguimos sem IA 👍 Quando quiser ligar, é só mandar /ia."

SEGUINDO_SEM_IA = "Segui sem IA por enquanto. O /ia liga quando você quiser."

AINDA_SEM_CHAVE = ("Ainda não vi a chave por aqui. Ela é uma linha só, começa com sk-ant- "
                   "e sai de console.anthropic.com/settings/keys.\n\n"
                   "Cole ela aqui, ou toque em Seguir sem IA.")

STATUS_LIGADA = ("A IA está ligada com a sua chave 🔑\n\n"
                 "Para trocar, cole outra chave aqui. Para desligar: /ia remover")

STATUS_FALHANDO = ("A IA está ligada com a sua chave, mas a última chamada não foi: "
                   "{motivo}.\n\n"
                   "Para trocar, cole outra chave aqui. Para desligar: /ia remover")

REMOVIDA = ("Apaguei sua chave. A IA está desligada, e o cadastro continua funcionando "
            "com as respostas prontas.")

# Pergunta solta sem IA ligada. Cair calado no roteiro fazia a pergunta virar "não
# entendi" no campo seguinte, que é a pior resposta possível para quem pediu ajuda.
SEM_IA = ("Pergunta solta eu só respondo com a IA ligada, e por enquanto ela roda com a "
          "chave da própria pessoa, e /ia explica como ligar.\n\n"
          "Para falar com gente, ligue 1746. Podemos continuar de onde paramos?")

# Anexado pela máquina quando a chave da pessoa falha NO MEIO da conversa. O cadastro não
# para, porque o `RedatorClaude` cai para o texto pronto sozinho, mas ficar seco sem explicar
# faria a pessoa achar que a chave dela está funcionando.
AVISO_FORA = ("Aviso: a IA não respondeu agora: {motivo}. Segui com as respostas "
              "prontas, e nada do seu cadastro se perdeu. Para trocar a chave: /ia")


# ------------------------------------------------------------- o que chega pelo chat

def pedido_de_configuracao(texto: str) -> str | None:
    """A mensagem mexe na IA? Devolve o argumento: `""` para o `/ia` pelado, `None` se a
    mensagem não é sobre isso e segue para o roteiro.

    A chave é procurada em QUALQUER lugar do texto, não só colada sozinha: "prontinho, a
    chave é sk-ant-..." tem que entrar por aqui também. Se seguisse para o roteiro, ela
    viraria resposta do campo que está no ar, gravada como se fosse um nome e ecoada de
    volta na tela, que é o pior lugar possível para um segredo.
    """
    if (achada := CHAVE_API.search(texto)) is not None:
        return achada.group()
    comando, _, resto = texto.partition(" ")
    return resto.strip() if comando.lower() in COMANDOS else None


def decisao(dados: dict) -> dict:
    """O pedaço da sessão que um recomeço não pode levar junto.

    Quem zera o contexto está recomeçando o CADASTRO. Desligar no mesmo gesto a IA que a
    pessoa cadastrou seria apagar uma decisão que ela tomou noutro assunto, e sem avisar.
    """
    return {c: dados[c] for c in CHAVES_DECISAO if c in dados}


# ------------------------------------------------------------- a tela do bloco 0.0

def precisa_escolher(dados: dict) -> bool:
    """A tela 0.0 é para quem ainda não decidiu nada: aparece uma vez, não a cada /start."""
    return not dados.get("chave_ia") and not dados.get("ia_dispensada")


def perguntar(p: Passo) -> MensagemSaida:
    p.ir("IA_CONFIG")
    return MensagemSaida(ESCOLHA, botoes=BOTOES_ESCOLHA)


def escolher(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "ligar_ia":
        p.dados["ia_aguardando"] = True
        p.ir("IA_CONFIG")
        return MensagemSaida(COMO_LIGAR, botoes=(BOTAO_SEM_IA,))
    if p.msg.escolha == "sem_ia":
        return _seguir(p, SEM_IA_OK, entrada.inicio)

    # Quem pediu para ligar está tentando colar a chave, e a mensagem que chega aqui é
    # "não achei", "já criei" ou a chave pela metade (a chave inteira nem chega neste
    # passo: `pedido_de_configuracao` a intercepta antes). Desistir por ela seria fazer
    # o contrário do que ela acabou de pedir. Repete a instrução, com a saída à vista.
    if p.dados.get("ia_aguardando") and not p.msg.escolha:
        p.ir("IA_CONFIG")
        return MensagemSaida(AINDA_SEM_CHAVE, botoes=(BOTAO_SEM_IA,))

    # Qualquer outra coisa, seja texto solto, botão de outra tela, assunto que não é este: a
    # pessoa não quer decidir isto agora. Prender alguém numa tela de configuração de
    # chave de API seria o pior desfecho possível de um bot de matrícula.
    return _seguir(p, SEGUINDO_SEM_IA, entrada.porta if p.msg.escolha else entrada.inicio)


def _seguir(p: Passo, nota: str, tela) -> MensagemSaida:
    """Marca a decisão e entrega a próxima tela do roteiro com a nota em cima."""
    p.dados["ia_dispensada"] = True
    p.dados.pop("ia_aguardando", None)
    p.ir("PORTA")
    desenhada = tela(p)
    return replace(desenhada, texto=f"{nota}\n\n{desenhada.texto}")


# ------------------------------------------------- `/ia` e a chave colada, em qualquer ponto

def comando(p: Passo, estado: str, argumento: str) -> MensagemSaida:
    """`/ia`, `/ia remover`, `/ia sk-ant-...` e a chave colada sozinha.

    Salva a sessão aqui: comando global devolve resposta antes do fim do turno, e sem
    isto a chave que a pessoa acabou de cadastrar não sobreviveria à próxima mensagem.
    """
    resposta = _responder(p, estado, argumento)
    p.repo.salvar_sessao(p.contato_id, p.proximo or estado, p.dados)
    return resposta


def _responder(p: Passo, estado: str, argumento: str) -> MensagemSaida:
    if not argumento:
        return MensagemSaida(_status(p))
    if argumento.lower() in DESLIGAR:
        p.dados.pop("chave_ia", None)
        if estado == "IA_CONFIG":           # desligou já na tela 0.0: segue para o roteiro
            return _seguir(p, REMOVIDA, entrada.inicio)
        p.dados["ia_dispensada"] = True     # decidiu; não pergunte de novo no /start
        return MensagemSaida(REMOVIDA)
    return _ligar(p, argumento, estado)


def _ligar(p: Passo, chave: str, estado: str) -> MensagemSaida:
    """Testa antes de salvar. Chave que não funciona não entra.

    Guardar sem testar faria o pior tipo de falha silenciosa: `RedatorClaude` cai para o
    texto pronto a cada chamada, o bot fica igual ao de antes, e quem colou a chave
    nunca descobre que ela está errada.
    """
    if (motivo := diagnosticar(chave)) is not None:
        botoes = (BOTAO_SEM_IA,) if estado == "IA_CONFIG" else ()
        return MensagemSaida(FALHOU.format(motivo=motivo), botoes=botoes)

    p.dados["chave_ia"] = chave
    p.dados.pop("ia_aguardando", None)
    if estado != "IA_CONFIG":
        return MensagemSaida(LIGADA)        # no meio da conversa, não redesenha nada
    tela = entrada.inicio(p)
    return replace(tela, texto=f"{LIGADA}\n\n{tela.texto}")


def _status(p: Passo) -> str:
    if not p.dados.get("chave_ia"):
        return DESLIGADA
    motivo = aviso_de_falha(p.redator, cru=True)
    return STATUS_FALHANDO.format(motivo=motivo) if motivo else STATUS_LIGADA


def aviso_de_falha(redator, *, cru: bool = False) -> str | None:
    """O que a última chamada ao modelo deixou para trás. `None` = a IA está de pé.

    `getattr` porque só o `RedatorClaude` tem esse atributo: o estático nunca falha, e
    dublê de teste não precisa saber que ele existe.
    """
    motivo = getattr(redator, "ultima_falha", None)
    if motivo is None:
        return None
    return motivo if cru else AVISO_FORA.format(motivo=motivo)
