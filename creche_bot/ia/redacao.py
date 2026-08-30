"""Como o bot fala. Duas implementações; a escolha é config, não arquitetura.

`RedatorEstatico` roda sem chave da Anthropic e sem rede — é o que permite validar o
fluxo inteiro no Telegram antes de gastar um token.
`RedatorClaude` usa os mesmos textos como base, dá a variação humana em cima, responde
pergunta solta e classifica o que a família manda.

## Os guardrails, e por que existem

O prompt pede tom, limite de linhas e honestidade. Pedir não é garantir: do outro lado
tem um campo de texto aberto, e alguém vai tentar dobrar o prompt. Então nada que o
modelo devolve entra na conversa sem passar por `_limpo` + `_promete`, e mais:

  · em `texto()`, os números do texto base têm que sobreviver intactos — número mexido é
    CPF errado, protocolo errado ou nota de corte errada na tela da família;
  · em `responder_duvida()`, sequência longa de dígito é descartada inteira (CPF, CEP,
    telefone e protocolo inventados), e link também (leva a família para golpe);
  · a pergunta do usuário entra truncada, sem `<` nem `>`, dentro de uma tag que o prompt
    declara ser dado;
  · em `classificar()`, a palavra que volta tem que estar no vocabulário de `Intencao` —
    rótulo inventado viraria intenção que a máquina de estados não sabe tratar.

Qualquer reprovação cai para o texto estático. Um filtro que barra não pode emudecer o bot.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol, get_args, runtime_checkable

from creche_bot.dominio.tipos import Classificacao, Intencao
from creche_bot.ia.persona import SISTEMA, SISTEMA_CLASSIFICA, SISTEMA_DUVIDA, TEXTOS

log = logging.getLogger(__name__)

MODELO = "claude-haiku-4-5"   # nunca Fable/Mythos: são Covered Models, sem ZDR

MAX_PERGUNTA = 500     # o que o usuário manda, cortado antes de virar prompt
MAX_RESPOSTA = 600     # o que o modelo devolve, cortado antes de virar mensagem
MAX_LINHAS = 4

# O sistema cadastra e informa; ele não decide quem entra. Nada disto pode sair daqui.
#
# "probabilidade" e "chance" saíram da lista: o painel do bloco 10 agora mostra a chance
# estimada por creche, calculada em `backend/mapa.py` sobre o que aconteceu em 2025. O que
# a lista continua barrando é o salto de estimativa para promessa — garantia, certeza, e a
# classificação que o bot não faz (pontuação, nota, posição na fila). Um número com ano
# estampado é informação; "você vai conseguir" continua sendo mentira.
PROMESSAS = ("garantid", "com certeza", "certamente", "vai conseguir", "prometo",
             "asseguro", "pode comemorar", "está na frente",
             "sua pontuação", "sua nota", "posição na fila")

REESCRITA = "Reescreva com suas palavras, mantendo o sentido e os números exatos:\n\n{base}"

# Sai do contrato congelado, não de uma segunda lista aqui: vocabulário novo em
# `dominio/tipos.py` passa a ser aceito sem ninguém lembrar de mexer neste arquivo.
#
# A chave é a palavra SEM separador porque `_limpo` tira `_` achando que é markdown:
# "fora_de_contexto" chegava aqui como "foradecontexto" e a intenção mais importante do
# classificador caía fora do vocabulário em silêncio. De quebra aceita "fora de contexto"
# e "Fora-De-Contexto", que é o que um modelo escreve quando quer ser prestativo.
INTENCOES: dict[str, str] = {re.sub(r"[^a-z]", "", i): i for i in get_args(Intencao)}


def _limpo(resposta: str) -> str:
    """Tira markdown. Os dialetos de Telegram e WhatsApp divergem; texto puro serve nos dois."""
    return re.sub(r"[*_`#]", "", resposta).strip()


def _promete(texto: str) -> bool:
    baixo = texto.lower()
    return any(p in baixo for p in PROMESSAS)


def _numeros(texto: str) -> list[str]:
    return re.findall(r"\d+", texto)


@runtime_checkable
class Redator(Protocol):
    def texto(self, chave: str, **vars: Any) -> str: ...
    def classificar(self, mensagem: str, estado: str) -> Classificacao: ...
    def responder_duvida(self, pergunta: str, etapa: str) -> str | None: ...


class RedatorEstatico:
    """Textos escritos à mão. Determinístico, grátis, testável."""

    def texto(self, chave: str, **vars: Any) -> str:
        return TEXTOS[chave].format(**vars) if vars else TEXTOS[chave]

    def classificar(self, mensagem: str, estado: str) -> Classificacao:
        m = mensagem.lower().strip()
        if m in {"/apagar", "apagar", "quero apagar meus dados"}:
            return Classificacao(intencao="desistir")
        if m.endswith("?") or m.startswith(("como", "quando", "por que", "porque", "o que")):
            return Classificacao(intencao="duvida")
        return Classificacao(intencao="responder")

    def responder_duvida(self, pergunta: str, etapa: str) -> str | None:
        """Sem chave não há resposta livre — e `None` faz a máquina seguir o roteiro,
        exatamente como antes de existir IA aqui."""
        return None


class RedatorClaude:
    """Mesma interface, com variação de linguagem. Cai para o estático se a API falhar —
    um erro de rede não pode emudecer o bot."""

    def __init__(self, api_key: str) -> None:
        from anthropic import Anthropic  # import tardio: dependência opcional

        self._cliente = Anthropic(api_key=api_key)
        self._reserva = RedatorEstatico()

    def _pedir(self, sistema: str, pergunta: str) -> str | None:
        """Uma chamada e os filtros que valem para toda resposta. `None` = descarte."""
        try:
            r = self._cliente.messages.create(
                model=MODELO,
                max_tokens=300,
                system=sistema,   # ~180 tokens: abaixo do mínimo cacheável, cache não pega
                messages=[{"role": "user", "content": pergunta}],
            )
        except Exception:
            log.exception("chamada ao modelo falhou")
            return None

        if r.stop_reason == "refusal":       # HTTP 200, não exceção
            log.warning("recusa do modelo")
            return None

        resposta = _limpo("".join(b.text for b in r.content if b.type == "text"))
        if not resposta or _promete(resposta):
            log.warning("resposta do modelo reprovada no filtro de saída")
            return None
        return resposta

    def classificar(self, mensagem: str, etapa: str) -> Classificacao:
        """Uma chamada por mensagem digitada. É cara em latência e barata em dinheiro, e
        paga porque a heurística de string não distingue quem responde de quem se perdeu:
        "meu marido perdeu o emprego" não termina em "?" e não é resposta de CPF nenhum.

        Qualquer tropeço — API fora, palavra fora do vocabulário, filtro reprovando —
        volta para a heurística. Classificador mudo não pode emudecer o cadastro.
        """
        limpa = mensagem[:MAX_PERGUNTA].replace("<", "(").replace(">", ")")
        palavra = self._pedir(
            SISTEMA_CLASSIFICA,
            f"O bot acabou de perguntar: {etapa}\n\n<mensagem>{limpa}</mensagem>",
        )
        chave = re.sub(r"[^a-z]", "", (palavra or "").lower())
        if chave not in INTENCOES:
            if palavra is not None:
                log.warning("classificação fora do vocabulário: %r", palavra[:40])
            return self._reserva.classificar(mensagem, etapa)
        return Classificacao(intencao=INTENCOES[chave])

    def texto(self, chave: str, **vars: Any) -> str:
        base = self._reserva.texto(chave, **vars)
        novo = self._pedir(SISTEMA, REESCRITA.format(base=base))
        if novo is None or _numeros(novo) != _numeros(base):
            return base      # número mexido é dado errado na tela da família
        return novo

    def responder_duvida(self, pergunta: str, etapa: str) -> str | None:
        # `<` e `>` fora: sem eles ninguém fecha a tag e escapa para fora do bloco de dado.
        limpa = pergunta[:MAX_PERGUNTA].replace("<", "(").replace(">", ")")
        resposta = self._pedir(
            SISTEMA_DUVIDA,
            f"CONTEXTO: a pessoa está na etapa {etapa} do cadastro. Nenhum dado pessoal "
            f"dela está disponível aqui.\n\n<pergunta>{limpa}</pergunta>",
        )
        if resposta is None or re.search(r"\d{5,}", resposta):
            return self._reserva.texto("duvida_sem_resposta")
        curta = "\n".join(resposta.splitlines()[:MAX_LINHAS])[:MAX_RESPOSTA]
        return f"{curta}\n\n{self._reserva.texto('retomando')}"


def criar(api_key: str | None) -> Redator:
    return RedatorClaude(api_key) if api_key else RedatorEstatico()
