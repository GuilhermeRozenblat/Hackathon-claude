"""O contexto da conversa, projetado nas colunas de `dados/porta.py`.

## Por que existe

`sessao.contexto` é jsonb porque o formato muda toda semana — é o estado VIVO do diálogo,
e não vale uma migração por pergunta. Mas jsonb não responde "quantas famílias de Curicica
pararam antes de escolher a creche", que é a pergunta que alguém vai fazer. Então o mesmo
dado sai daqui numa segunda forma, consultável, e esta é a única tradução entre as duas.

## Onde é chamada

Uma vez por turno, em `maquina.processar()`, logo depois de `salvar_sessao()`. A cada
turno de propósito: família que abandona no meio deixa rastro do que já respondeu, e o
abandono é justamente o que interessa medir. É gravação idempotente — a mesma linha é
reescrita, não acumulada.

## O que NÃO atravessa

O texto livre que a pessoa digitou nas perguntas sensíveis. A régua vira código + booleano
e nada mais: `resposta_criterio` diz que "violencia_domestica" foi declarado, nunca o que
foi contado. Ver a regra de dado sensível no CLAUDE.md da raiz.
"""

from __future__ import annotations

from typing import Any

from creche_bot.dados.porta import Cadastro, PreferenciaEscola, RespostaCriterio


def _sensiveis(dados: dict[str, Any]) -> set[str]:
    return {c["codigo"] for c in dados.get("criterios", ()) if c.get("sensivel")}


def _criterios(dados: dict[str, Any]) -> tuple[RespostaCriterio, ...]:
    """Uma linha por critério DECLARADO. O que não foi declarado não vira linha `False`:
    a régua muda todo ano, e gravar ausência inventaria pergunta que não foi feita."""
    declarados = list(dados.get("declarados", ()))
    comprovados = set(dados.get("comprovados", ()))
    sensiveis = _sensiveis(dados)
    return tuple(
        RespostaCriterio(codigo=c, declarado=True, comprovado=c in comprovados,
                         sensivel=c in sensiveis)
        for c in declarados)


def _preferencias(dados: dict[str, Any]) -> tuple[PreferenciaEscola, ...]:
    """As opções na ordem dos toques — posição 1 é a primeira, como no Sisu.

    Leva junto o fato que estava na tela na hora da escolha. Sem isso ninguém consegue
    reconstruir depois com base em que a família decidiu, e o painel muda de ano para ano.
    """
    por_id = {e["id"]: e for e in dados.get("escolas", ())}
    saida = []
    for posicao, id_escola in enumerate(dados.get("preferencias", ()), 1):
        e = por_id.get(id_escola, {})
        concorrencia = e.get("concorrencia") or (None, None)
        saida.append(PreferenciaEscola(
            posicao=posicao, id_escola=id_escola, nome_escola=e.get("nome", ""),
            distancia_km=e.get("km"), vaga_ociosa=bool(e.get("ociosa")),
            familias_por_vaga=concorrencia[0], ano_referencia=concorrencia[1]))
    return tuple(saida)


def cadastro_de(contato_id: str, dados: dict[str, Any]) -> Cadastro | None:
    """O contexto virado `Cadastro`. `None` quando ainda não há nada que valha uma linha.

    O corte é a primeira resposta de conteúdo: sem ele, todo `/start` que a pessoa manda
    por hábito criaria uma linha vazia no banco.

    Inscrição já efetivada também devolve `None`. O contexto continua cheio depois do
    protocolo, e sem esta guarda o turno seguinte reabriria um cadastro com a criança que
    acabou de ser inscrita. `numero` é o marcador certo porque ele NÃO sobrevive a
    "inscrever outra criança" — `DO_RESPONSAVEL` não o carrega — então a próxima criança
    volta a abrir cadastro sozinha.
    """
    if dados.get("numero"):
        return None

    endereco = dados.get("endereco") or {}
    cadastro = Cadastro(
        contato_id=contato_id,
        nome_crianca=dados.get("nome_crianca"),
        nascimento_crianca=dados.get("nascimento_crianca"),
        sexo=dados.get("sexo"),
        grupamento=dados.get("grupamento"),
        documento_crianca=dados.get("documento_crianca"),
        nome_responsavel=dados.get("nome_responsavel"),
        cpf_responsavel=dados.get("cpf_responsavel"),
        relacao=dados.get("relacao"),
        cep=endereco.get("cep"),
        numero=endereco.get("numero"),
        logradouro=endereco.get("logradouro"),
        bairro=endereco.get("bairro"),
        lat=endereco.get("lat"),
        lng=endereco.get("lng"),
        horario=dados.get("horario"),
        telefone=dados.get("telefone"),
        email=dados.get("email"),
        criterios=_criterios(dados),
        preferencias=_preferencias(dados))

    vazio = (not any((cadastro.cpf_responsavel, cadastro.nome_responsavel,
                      cadastro.nome_crianca, cadastro.cep))
             and not cadastro.criterios and not cadastro.preferencias)
    return None if vazio else cadastro
