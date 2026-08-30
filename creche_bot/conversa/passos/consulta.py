"""Bloco C — acompanhar uma inscrição que já existe.

Serve para quem se inscreveu pelo SITE também. É leitura pura, não toca no fluxo de
inscrição, e alcança as ~62 mil famílias que usaram o matricula.rio normalmente —
inclusive os 7,7% que perdem a vaga já convocados.

## A regra que não pode ser quebrada aqui

**Nunca mostre a situação bruta da opção.** O banco grava um status por opção de creche, e
77,8% das linhas "Cancelado pelo sistema" pertencem a inscrições que FORAM ATENDIDAS — é o
cancelamento automático das outras opções quando uma é preenchida. Uma família que
conseguiu a vaga veria "cancelado" em 4 das suas 5 escolhas. O que aparece é o DESFECHO,
calculado no `dominio`, e nada além dele.

**Nunca informe posição na fila nem pontuação.** A classificação é por critério, não por
ordem de chegada, e a posição muda conforme outras famílias comprovam.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import date

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, ItemLista, Local, MensagemSaida
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import Desfecho

BOTOES_COMO = (Botao("com_numero", "Tenho o número"),
               Botao("sem_numero", "Não tenho"))

BOTOES_NAO_ACHOU = (Botao("tentar", "Tentar de novo"),
                    Botao("inscrever", "Fazer inscrição"),
                    Botao("atendente", "Falar com a CRE"))

ACOES = (ItemLista("doc", "Mandar documento que falta"),
         ItemLista("telefone", "Atualizar meu telefone"),
         ItemLista("endereco", "Mudei de endereço"),
         ItemLista("outra", "Inscrever outra criança"))


def comecar(p: Passo) -> MensagemSaida:
    p.ir("CONSULTA_COMO")
    return MensagemSaida(p.txt("consulta_comecar"), botoes=BOTOES_COMO)


def como(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.formulario_passo import perguntar

    if p.msg.escolha == "com_numero":
        p.ir("CONSULTA_NUMERO")
        return MensagemSaida(p.txt("consulta_pedir_numero"))

    if p.msg.escolha == "sem_numero":
        p.ir("CONSULTA_NOME")
        return perguntar(p, "CONSULTA", _buscar_por_nome)

    return p.diz("nao_entendi", botoes=BOTOES_COMO)


# ------------------------------------------------------ C.1 os dois caminhos
def por_numero(p: Passo) -> MensagemSaida:
    """Caminho 1 do portal: número + nascimento, os dois no mesmo balão como o roteiro pede."""
    texto = p.texto or ""
    numero = re.search(r"\d{4}\s*-\s*\d{5,8}", texto)
    nascimento = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", texto)
    if not numero or not nascimento:
        return _errar(p, "consulta_pedir_numero")

    try:
        data = date(int(nascimento[3]), int(nascimento[2]), int(nascimento[1]))
    except ValueError:
        return _errar(p, "consulta_pedir_numero")

    try:
        achados = p.backend.consultar_por_numero(
            re.sub(r"\s", "", numero[0]), data)
    except BackendIndisponivel:
        return p.diz("backend_fora")
    return _apresentar(p, achados)


def _buscar_por_nome(p: Passo) -> MensagemSaida:
    """Caminho 2 do portal: nome + nascimento + filiação. Existe porque nem todo mundo
    guarda o número, e porque há criança sem filiação registrada."""
    try:
        achados = p.backend.consultar_por_nome(
            p.dados["busca_nome"], date.fromisoformat(p.dados["busca_nascimento"]),
            p.dados.get("busca_filiacao", ""))
    except BackendIndisponivel:
        return p.diz("backend_fora")

    for chave in ("busca_nome", "busca_nascimento", "busca_filiacao_consta",
                  "busca_filiacao"):
        p.dados.pop(chave, None)
    return _apresentar(p, achados)


def _errar(p: Passo, chave: str) -> MensagemSaida:
    """Depois de 3 tentativas sem achar, atendente direto — não deixe a família em loop."""
    p.dados["erros_consulta"] = p.dados.get("erros_consulta", 0) + 1
    if p.dados["erros_consulta"] >= 3:
        return _nao_achou(p)
    return MensagemSaida(p.txt(chave))


# ------------------------------------------------------ C.2 mais de uma criança
def _apresentar(p: Passo, achados: list[Desfecho]) -> MensagemSaida:
    if not achados:
        return _nao_achou(p)

    p.dados["erros_consulta"] = 0
    p.dados["achados"] = [_achatar(d) for d in achados]

    if len(achados) == 1:
        return _situacao(p, p.dados["achados"][0])

    p.ir("CONSULTA_ESCOLHER")
    botoes = tuple(Botao(d.numero, f"{d.nome_crianca.split()[0]} "
                                   f"({d.data_nascimento:%m/%Y})")
                   for d in achados[:2])
    return MensagemSaida(p.txt("consulta_qual"),
                         botoes=(*botoes, Botao("todas", "Ver as duas")))


def escolher(p: Passo) -> MensagemSaida:
    achados = p.dados.get("achados", [])
    if p.msg.escolha == "todas":
        return _situacao(p, achados[0], prefixo=_resumo_das_outras(achados[1:]))
    alvo = next((d for d in achados if d["numero"] == p.msg.escolha), None)
    if alvo is None:
        return p.diz("nao_entendi")
    return _situacao(p, alvo)


def _resumo_das_outras(outras: list[dict]) -> str:
    linhas = "\n".join(f"• {d['nome']}: {RESUMO_ESTADO[d['estado']]}" for d in outras)
    return f"As outras:\n{linhas}\n\n"


RESUMO_ESTADO = {
    "vaga_confirmada": "vaga confirmada",
    "lista_de_espera": "na lista de espera",
    "nao_seguiu": "não seguiu no processo",
    "perdeu_prazo": "o prazo de confirmação venceu",
    "cancelada": "cancelada",
    "selecionada": "selecionada, falta confirmar",
    "ativa": "ativa, aguardando a classificação",
}


def _achatar(d: Desfecho) -> dict:
    return {"numero": d.numero, "nome": d.nome_crianca, "estado": d.estado,
            "escolas": list(d.escolas), "escola": d.escola_atendida,
            "endereco": d.endereco_escola, "lat": d.lat, "lng": d.lng,
            "prazo": d.prazo_confirmacao.isoformat() if d.prazo_confirmacao else None,
            "aulas": d.inicio_das_aulas.isoformat() if d.inicio_das_aulas else None,
            "pendencias": list(d.pendencias)}


# ---------------------------------------------------------- C.3 a situação
def _br(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else "a definir"


# Ícone por `TipoEtapa` — a taxonomia FECHADA, nunca o código do backend, que muda por
# município. Tipo novo cai no traço e a tela continua legível.
ICONE_ETAPA = {
    "aguardando": "🕐", "acao_no_chat": "✋", "acao_presencial": "📍",
    "convocacao": "🔔", "concluida": "✅", "encerrada": "⚪",
}


def _linha_do_tempo(p: Passo, numero: str) -> str:
    """O caminho que a inscrição já andou. Vazio até haver mais de uma etapa.

    Com uma etapa só a lista não informa nada que o balão acima não tenha dito, e ocupa
    tela de quem está ansiosa por notícia. É história, não posição na fila: diz o que já
    aconteceu com ESTA inscrição, nunca onde ela está em relação às outras.
    """
    historia = p.repo.eventos(numero)
    if len(historia) < 2:
        return ""
    linhas = "\n".join(f"{ICONE_ETAPA.get(e.tipo, '·')} {e.titulo}" for e in historia)
    return f"\n\nComo foi até aqui:\n{linhas}"


def _situacao(p: Passo, d: dict, prefixo: str = "") -> MensagemSaida:
    """A situação atual, com a história embaixo.

    Menos a convocação: quando há vaga selecionada e prazo correndo, o balão fica só com
    a vaga e o prazo. É o caso dos 7,7% que perderam vaga já convocados em 2025, e
    qualquer coisa a mais na tela compete com a única ação que importa ali.
    """
    msg = _desenhar(p, d, prefixo)
    if d["estado"] == "selecionada" or not (historia := _linha_do_tempo(p, d["numero"])):
        return msg
    return replace(msg, texto=msg.texto + historia)


def _desenhar(p: Passo, d: dict, prefixo: str = "") -> MensagemSaida:
    p.dados["consultada"] = d
    p.ir("CONSULTA_ACOES")
    nome = d["nome"].split()[0]
    estado = d["estado"]

    if estado == "selecionada":
        # Se a inscrição está nesse estado, este é o PRIMEIRO balão da conversa.
        p.ir("CONSULTA_CONFIRMAR")
        return p.diz("c3f_selecionada", prefixo=prefixo, nome=nome,
                     escola=d["escola"], prazo=_br(d["prazo"]),
                     botoes=(Botao("confirmar", "Confirmar a vaga"),
                             Botao("nao_posso", "Não vou poder")))

    if estado == "vaga_confirmada":
        return p.diz("c3a_confirmada", prefixo=prefixo, nome=nome, escola=d["escola"],
                     endereco=d["endereco"] or "", aulas=_br(d["aulas"]),
                     botoes=(Botao("acoes", "Preciso de mais nada"),),
                     local=(Local(d["lat"], d["lng"], d["escola"], d["endereco"])
                            if d["lat"] is not None else None))

    if estado == "lista_de_espera":
        escolas = " e ".join(d["escolas"])
        if d["pendencias"]:
            # É aqui que a consulta deixa de ser passiva: quem está na fila com critério
            # pendente é exatamente quem perdeu pontuação por não comprovar.
            p.ir("CONSULTA_PENDENCIA")
            espera = prefixo + p.txt("c3b_espera", nome=nome, escolas=escolas)
            return p.diz("c3b_pendencia", prefixo=f"{espera}\n\n",
                         botoes=(Botao("mandar_nis", "Mandar o NIS"),
                                 Botao("depois", "Depois")))
        return p.diz("c3b_espera", prefixo=prefixo, nome=nome, escolas=escolas,
                     botoes=(Botao("acoes", "Preciso de mais nada"),))

    if estado == "nao_seguiu":
        # Estado ambíguo no banco. Não invente o motivo — encaminhe.
        return p.diz("c3c_nao_seguiu", prefixo=prefixo, nome=nome,
                     botoes=(Botao("inscrever", "Nova inscrição"),
                             Botao("atendente", "Falar com a CRE")))

    if estado == "perdeu_prazo":
        return p.diz("c3d_perdeu_prazo", prefixo=prefixo, nome=nome,
                     escola=d["escola"] or "creche", prazo=_br(d["prazo"]),
                     botoes=(Botao("avisar", "Quero ser avisada"),
                             Botao("atendente", "Falar com a CRE")))

    if estado == "cancelada":
        return p.diz("c3e_cancelada", prefixo=prefixo, nome=nome,
                     botoes=(Botao("atendente", "Falar com a CRE"),))

    return p.diz("c3g_ativa", prefixo=prefixo, nome=nome,
                 resultado=p.backend.data_do_resultado().strftime("%d/%m/%Y"),
                 botoes=(Botao("acoes", "Preciso de mais nada"),))


def confirmar_vaga(p: Passo) -> MensagemSaida:
    d = p.dados["consultada"]
    if p.msg.escolha == "confirmar":
        return _avisos(p, prefixo=f"{p.txt('vaga_confirmada', escola=d['escola'])}\n\n")
    if p.msg.escolha == "nao_posso":
        return _avisos(p, prefixo=f"{p.txt('vaga_recusada')}\n\n")
    return p.diz("nao_entendi",
                 botoes=(Botao("confirmar", "Confirmar a vaga"),
                         Botao("nao_posso", "Não vou poder")))


def pendencia(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "mandar_nis":
        p.ir("CONSULTA_NIS")
        return MensagemSaida(p.txt("pedir_nis"))
    return _avisos(p)


def nis(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.formulario import digitos_de

    valido, _ = p.backend.validar_nis(digitos_de(p.texto))
    if not valido:
        return p.diz("nis_invalido")
    return _avisos(p, prefixo=f"{p.txt('nis_ok')}\n\n")


# ------------------------------------------------- C.4 e C.5 o que fazer daqui
def _avisos(p: Passo, prefixo: str = "") -> MensagemSaida:
    """C.5 — o turno mais valioso do fluxo de consulta.

    É assim que o bot alcança quem se inscreveu pelo site: a família chega por uma
    consulta e sai com o canal de convocação ativo.
    """
    if p.dados.get("avisos_ligados"):
        return acoes(p, prefixo)
    p.ir("CONSULTA_AVISOS")
    return MensagemSaida(prefixo + p.txt("consulta_avisos"),
                         botoes=(Botao("quero", "Quero ser avisada"),
                                 Botao("nao", "Não, obrigada")))


def avisos(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "quero":
        p.dados["avisos_ligados"] = True
        p.repo.registrar_consentimento(p.contato_id, "comunicacao/consulta",
                                       p.msg.canal, p.msg.id_externo)
        return acoes(p, prefixo=f"{p.txt('aviso_ligado')}\n\n")
    return acoes(p)


def acoes(p: Passo, prefixo: str = "") -> MensagemSaida:
    p.ir("CONSULTA_ACOES")
    return MensagemSaida(prefixo + p.txt("consulta_acoes"), lista=ACOES)


def escolher_acao(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.entrada import inicio

    escolha = p.msg.escolha
    if escolha == "doc":
        p.ir("CONSULTA_DOC")
        return p.diz("consulta_pedir_doc")
    if escolha == "telefone":
        p.ir("CONSULTA_TELEFONE")
        return MensagemSaida(p.txt("consulta_novo_telefone"))
    if escolha == "endereco":
        # Mudança de endereço pode alterar o polo de classificação: não é edição de
        # cadastro, é conversa com a CRE.
        return MensagemSaida(p.txt("consulta_mudou_endereco"),
                             botoes=(Botao("atendente", "Falar com a CRE"),))
    if escolha == "outra":
        return inicio(p)
    if escolha == "acoes":
        return acoes(p)
    return MensagemSaida(p.txt("consulta_acoes"), lista=ACOES)


def novo_telefone(p: Passo) -> MensagemSaida:
    """Parece pequeno e não é: contato desatualizado é uma das causas dos 7,7% que
    perdem a vaga já convocados."""
    from creche_bot.conversa.formulario import campo_de, formatar, validar

    campo = campo_de("telefone")
    ok, valor = validar(campo, p.texto)
    if not ok:
        return MensagemSaida(campo.erro)
    p.dados["telefone"] = valor
    return acoes(p, prefixo=f"{p.txt('telefone_atualizado', telefone=formatar(campo, valor))}\n\n")


def receber_doc(p: Passo) -> MensagemSaida:
    if p.msg.anexo is None:
        return p.diz("pedir_foto")
    d = p.dados.get("consultada", {})
    codigo = (d.get("pendencias") or ["documento"])[0]
    try:
        lido = p.backend.enviar_documento(d.get("numero", ""), codigo,
                                          p.msg.anexo.conteudo, p.msg.anexo.mime)
    except BackendIndisponivel:
        return p.diz("backend_fora")
    if lido.confianca == "baixa":
        return p.diz("documento_ilegivel")
    return acoes(p, prefixo=f"{p.txt('documento_recebido')}\n\n")


# --------------------------------------------------------- C.6 não encontrou
def _nao_achou(p: Passo) -> MensagemSaida:
    p.ir("CONSULTA_NAO_ACHOU")
    return p.diz("consulta_nao_achou", botoes=BOTOES_NAO_ACHOU)


def nao_achou(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.entrada import inicio

    if p.msg.escolha == "tentar":
        p.dados["erros_consulta"] = 0
        return comecar(p)
    if p.msg.escolha == "inscrever":
        return inicio(p)
    return p.diz("atendente")


def acompanhar(p: Passo) -> MensagemSaida:
    """`/status` e o fim da inscrição: com o número na sessão, vai direto ao desfecho."""
    numero = p.dados.get("numero")
    if not numero:
        return comecar(p)
    try:
        achados = p.backend.consultar_por_numero(
            numero, date.fromisoformat(p.dados["nascimento_crianca"]))
    except (BackendIndisponivel, KeyError, ValueError):
        return comecar(p)
    return _apresentar(p, achados) if achados else acoes(p)
