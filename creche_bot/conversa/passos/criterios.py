"""Bloco 8 — a régua de prioridade do processo vigente.

O CONTEÚDO vem de `backend.criterios_do_processo()`: ordem, pesos e texto mudam todo ano,
e régua escrita à mão no código quebra na virada. A FORMA de cada turno é o que está aqui,
e é estável.

## Por que este bloco existe

48,9% das famílias declaram CadÚnico e só 6,8% conseguem comprovar — por isso 93,8% das
inscrições terminam com pontuação validada zero. Capturar o NIS dentro da conversa é a
razão de existir do projeto.

## Duas decisões de desenho que parecem erro e não são

**Perguntas agrupadas em checklist (8.3 e 8.4).** Individualmente, as cinco situações
sensíveis disparam entre 1,6% e 5,3%; somadas, 13,6% marcam ao menos uma, com média de
0,18 marcação. Cinco turnos invasivos para esse aproveitamento é péssimo desenho — e pior
num canal cujo histórico fica no aparelho da família.

**Nada aqui bloqueia.** Documento que falta vira pendência com lembrete, nunca parede.
Exigir boletim de ocorrência de uma vítima de violência dentro de um chat, como condição
para inscrever a criança, é violento.
"""

from __future__ import annotations

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, ItemLista, MensagemSaida
from creche_bot.conversa.formulario import digitos_de
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import Criterio
from creche_bot.ia.persona import CONSENTIMENTO_SENSIVEL

SIM_NAO_NAOSEI = (Botao("sim", "Sim"), Botao("nao", "Não"), Botao("nao_sei", "Não sei"))
SIM_NAO = (Botao("sim", "Sim"), Botao("nao", "Não"))
BOTOES_GATE = (Botao("pode", "Pode perguntar"), Botao("pular", "Prefiro pular"))


def _do_grupo(p: Passo, grupo: str) -> list[Criterio]:
    return [c for c in p.dados["criterios"] if c["grupo"] == grupo]


def _marcar(p: Passo, codigo: str, comprovado: bool = False) -> None:
    p.dados.setdefault("declarados", [])
    if codigo not in p.dados["declarados"]:
        p.dados["declarados"].append(codigo)
    if comprovado:
        p.dados.setdefault("comprovados", []).append(codigo)


def pendentes(dados: dict) -> list[str]:
    """Declarado e ainda sem comprovação. É o que a família precisa ver, e o que o R1
    cobra depois — nunca a pontuação."""
    comprovados = set(dados.get("comprovados", ()))
    return [c for c in dados.get("declarados", ()) if c not in comprovados]


def comecar(p: Passo) -> MensagemSaida:
    try:
        criterios = p.backend.criterios_do_processo()
    except BackendIndisponivel:
        return p.diz("backend_fora")

    p.dados["criterios"] = [
        {"codigo": c.codigo, "rotulo": c.rotulo, "grupo": c.grupo,
         "sensivel": c.sensivel, "documento": c.documento,
         "opcional": c.documento_opcional}
        for c in criterios
    ]
    p.ir("CRIT_CADUNICO")
    return MensagemSaida(f"{p.txt('abrir_criterios')}\n\n{p.txt('perguntar_cadunico')}",
                         botoes=SIM_NAO_NAOSEI)


# ------------------------------------------------------ 8.1 CadÚnico e o NIS
def cadunico(p: Passo) -> MensagemSaida:
    if p.msg.escolha not in ("sim", "nao", "nao_sei"):
        return MensagemSaida(p.txt("perguntar_cadunico"), botoes=SIM_NAO_NAOSEI)

    if p.msg.escolha == "nao":
        return _abrir_educacao_especial(p)

    # "Não sei" segue o mesmo caminho do "sim": quem não sabe costuma ter.
    p.ir("CRIT_NIS")
    return MensagemSaida(p.txt("pedir_nis"),
                         botoes=(Botao("nao_acho", "Não estou achando"),))


def nis(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "nao_acho":
        # Nunca trave a inscrição por falta do NIS: grava, marca pendente, agenda o R1.
        for c in _do_grupo(p, "8.1"):
            _marcar(p, c["codigo"])
        prazo = p.backend.periodo_de_inscricao()[1].strftime("%d/%m")
        return _abrir_educacao_especial(p, prefixo=f"{p.txt('nis_depois', prazo=prazo)}\n\n")

    try:
        valido, comprova = p.backend.validar_nis(digitos_de(p.texto))
    except BackendIndisponivel:
        return p.diz("backend_fora")

    if not valido:
        return p.diz("nis_invalido",
                     botoes=(Botao("nao_acho", "Não estou achando"),))

    p.dados["nis"] = digitos_de(p.texto)
    for c in _do_grupo(p, "8.1"):
        _marcar(p, c["codigo"], comprovado=c["codigo"] in comprova)
    return _abrir_educacao_especial(p, prefixo=f"{p.txt('nis_ok')}\n\n")


# --------------------------------------------------- 8.2 educação especial
def _abrir_educacao_especial(p: Passo, prefixo: str = "") -> MensagemSaida:
    """Primeira pergunta sensível: o consentimento específico da LGPD art. 11 vem antes.

    Recusar aqui pula TODAS as perguntas sensíveis, as do 8.2 e as do 8.4.
    """
    if not p.dados.get("consentimento_sensivel"):
        p.ir("CRIT_GATE")
        return MensagemSaida(prefixo + CONSENTIMENTO_SENSIVEL, botoes=BOTOES_GATE)

    p.ir("CRIT_ESPECIAL")
    return MensagemSaida(prefixo + p.txt("perguntar_especial"), botoes=SIM_NAO)


def gate_sensivel(p: Passo) -> MensagemSaida:
    if p.msg.escolha == "pular":
        p.dados["consentimento_sensivel"] = False
        return _abrir_familia(p, prefixo=f"{p.txt('sensivel_pulado')}\n\n")

    if p.msg.escolha != "pode":
        return MensagemSaida(CONSENTIMENTO_SENSIVEL, botoes=BOTOES_GATE)

    p.dados["consentimento_sensivel"] = True
    p.repo.registrar_consentimento(p.contato_id, "dado_sensivel/8.4",
                                   p.msg.canal, p.msg.id_externo)
    return _abrir_educacao_especial(p)


def educacao_especial(p: Passo) -> MensagemSaida:
    if p.msg.escolha not in ("sim", "nao"):
        return MensagemSaida(p.txt("perguntar_especial"), botoes=SIM_NAO)

    if p.msg.escolha == "nao":
        return _abrir_familia(p)

    criterio = _do_grupo(p, "8.2")[0]
    _marcar(p, criterio["codigo"])
    return _pedir_anexo(p, criterio, seguinte="CRIT_FAMILIA")


# ------------------------------------------------ 8.3 composição familiar
def _abrir_familia(p: Passo, prefixo: str = "") -> MensagemSaida:
    p.ir("CRIT_FAMILIA")
    return _checklist(p, "8.3", prefixo)


def _checklist(p: Passo, grupo: str, prefixo: str = "") -> MensagemSaida:
    """Seleção múltipla que o WhatsApp não tem: a lista alterna a cada toque.

    Cabe folgado nos 10 itens — 3 no 8.3 e 5 no 8.4, mais o "pronto".
    """
    marcados = set(p.dados.get("declarados", ()))
    itens = tuple(
        ItemLista(c["codigo"], ("✅ " if c["codigo"] in marcados else "▫️ ") + c["rotulo"])
        for c in _do_grupo(p, grupo)
    )
    texto = p.txt("checklist_familia" if grupo == "8.3" else "checklist_sensivel")
    return MensagemSaida(prefixo + texto,
                         lista=(*itens, ItemLista("pronto", "Pronto, terminei")))


def familia(p: Passo) -> MensagemSaida:
    codigos = {c["codigo"] for c in _do_grupo(p, "8.3")}

    if p.msg.escolha in codigos:
        _alternar(p, p.msg.escolha)
        return _checklist(p, "8.3")

    if p.msg.escolha != "pronto":
        return _checklist(p, "8.3")

    # Verificável no SGA pelo nome, sem documento. Hoje 35,9% marcam e só 6,0% validam.
    if "irmao_matriculado" in p.dados.get("declarados", ()):
        p.ir("CRIT_IRMAO")
        return MensagemSaida(p.txt("pedir_irmao"))
    return _apos_familia(p)


def irmao(p: Passo) -> MensagemSaida:
    nome = " ".join((p.texto or "").split())
    if len(nome.split()) < 2:
        return MensagemSaida(p.txt("pedir_irmao"))
    p.dados["nome_irmao"] = nome
    p.dados.setdefault("comprovados", []).append("irmao_matriculado")
    return _apos_familia(p)


def _apos_familia(p: Passo) -> MensagemSaida:
    """Os documentos do 8.3 entram na fila; depois vem o 8.4, se houve consentimento."""
    for codigo in ("monoparental", "refugiada"):
        if codigo in p.dados.get("declarados", ()):
            criterio = next(c for c in p.dados["criterios"] if c["codigo"] == codigo)
            if codigo not in p.dados.get("comprovados", ()):
                return _pedir_anexo(p, criterio, seguinte="CRIT_SENSIVEL")
    return _abrir_sensivel(p)


# --------------------------------------------------- 8.4 situações sensíveis
def _abrir_sensivel(p: Passo, prefixo: str = "") -> MensagemSaida:
    if not p.dados.get("consentimento_sensivel"):
        return _fechar(p, prefixo)          # já recusou lá atrás: não pergunta de novo
    p.ir("CRIT_SENSIVEL")
    return _checklist(p, "8.4", prefixo)


def sensivel(p: Passo) -> MensagemSaida:
    codigos = {c["codigo"] for c in _do_grupo(p, "8.4")}

    if p.msg.escolha in codigos:
        _alternar(p, p.msg.escolha)
        return _checklist(p, "8.4")

    if p.msg.escolha != "pronto":
        return _checklist(p, "8.4")

    marcou = [c for c in _do_grupo(p, "8.4")
              if c["codigo"] in p.dados.get("declarados", ())]
    if marcou:
        # Um pedido só para todas: e a resposta "não tenho" tem que ser confortável.
        return _pedir_anexo(p, marcou[0], seguinte="FIM", generico=True)
    return _fechar(p)


# ------------------------------------------------------------ comprovações
def _alternar(p: Passo, codigo: str) -> None:
    declarados = p.dados.setdefault("declarados", [])
    if codigo in declarados:
        declarados.remove(codigo)
    else:
        declarados.append(codigo)


def _pedir_anexo(p: Passo, criterio: dict, seguinte: str,
                 generico: bool = False) -> MensagemSaida:
    p.dados["anexo_de"] = criterio["codigo"]
    p.dados["apos_anexo"] = seguinte
    p.dados["anexo_generico"] = generico
    p.ir("CRIT_ANEXO")
    chave = "pedir_documento_sensivel" if generico else "pedir_documento"
    return p.diz(chave, documento=criterio["documento"] or "o documento",
                 botoes=(Botao("depois", "Não tenho agora"),))


def anexo(p: Passo) -> MensagemSaida:
    seguinte = p.dados.get("apos_anexo", "FIM")

    if p.msg.escolha == "depois" or (p.msg.anexo is None and not p.texto):
        return _seguir(p, seguinte, prefixo=f"{p.txt('documento_depois')}\n\n")

    if p.msg.anexo is None:
        return p.diz("pedir_foto",
                     botoes=(Botao("depois", "Não tenho agora"),))

    codigo = p.dados["anexo_de"]
    try:
        lido = p.backend.enviar_documento(p.dados.get("numero", "rascunho"), codigo,
                                          p.msg.anexo.conteudo, p.msg.anexo.mime)
    except BackendIndisponivel:
        return p.diz("backend_fora")

    if lido.confianca == "baixa":
        # Documento ilegível não vira comprovação falsa.
        return p.diz("documento_ilegivel",
                     botoes=(Botao("depois", "Não tenho agora"),))

    p.dados.setdefault("comprovados", []).append(codigo)
    if lido.nis:
        p.dados.setdefault("nis", lido.nis)
    return _seguir(p, seguinte, prefixo=f"{p.txt('documento_recebido')}\n\n")


def _seguir(p: Passo, seguinte: str, prefixo: str) -> MensagemSaida:
    for chave in ("anexo_de", "apos_anexo", "anexo_generico"):
        p.dados.pop(chave, None)
    if seguinte == "CRIT_FAMILIA":
        return _abrir_familia(p, prefixo)
    if seguinte == "CRIT_SENSIVEL":
        return _apos_familia(p) if _falta_doc_familia(p) else _abrir_sensivel(p, prefixo)
    return _fechar(p, prefixo)


def _falta_doc_familia(p: Passo) -> bool:
    comprovados = set(p.dados.get("comprovados", ()))
    return any(c in p.dados.get("declarados", ()) and c not in comprovados
               for c in ("monoparental", "refugiada"))


def _fechar(p: Passo, prefixo: str = "") -> MensagemSaida:
    """Bloco 8 terminado — segue para o contato."""
    from creche_bot.conversa.passos.escolas import sugerir
    from creche_bot.conversa.passos.formulario_passo import perguntar

    p.ir("CONTATO")
    return perguntar(p, "CONTATO", sugerir, prefixo=prefixo)
