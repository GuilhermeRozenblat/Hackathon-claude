"""Bloco 6: endereço por CEP e número, nunca por bairro digitado.

Na base histórica o campo livre gerou 1.608 grafias para ~925 bairros: "Inhaúma" sozinho
tem 13 variantes. O CEP, ao contrário, é 100% preenchido e 100% válido desde 2024. O
servidor deriva logradouro, bairro e coordenadas; sem o número a precisão cai para ~1,4
km, o suficiente para errar a creche certa dentro do raio de 2 km que as famílias aceitam.

A família vê o bairro uma vez só: para confirmar, nunca para digitar.
"""

from __future__ import annotations

import re
from dataclasses import replace

from creche_bot.backend.porta import BackendIndisponivel
from creche_bot.canal.tipos import Botao, Local, MensagemSaida
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import Endereco

BOTOES_CONFIRMA = (Botao("confirma", "É isso"), Botao("corrige", "Não é esse"))


def pedir_cep(p: Passo) -> MensagemSaida:
    p.ir("ENDERECO_CEP")
    return MensagemSaida(p.txt("pedir_endereco"))


def _partir(texto: str) -> tuple[str, str] | None:
    """"22710-560, 100" -> ("22710560", "100"). Sem CEP de 8 dígitos, não passa."""
    texto = texto or ""
    if (m := re.search(r"(\d{5})\s*-\s*(\d{3})", texto)):     # CEP com hífen
        resto = texto[:m.start()] + texto[m.end():]
        return m[1] + m[2], next(iter(re.findall(r"\d+", resto)), "")

    grupos = re.findall(r"\d+", texto)
    for i, g in enumerate(grupos):                            # CEP como bloco de 8
        if len(g) == 8:
            sobra = grupos[:i] + grupos[i + 1:]
            return g, (sobra[0] if sobra else "")

    junto = "".join(grupos)                                   # tudo grudado
    return (junto[:8], junto[8:]) if len(junto) >= 8 else None


def receber_cep(p: Passo) -> MensagemSaida:
    partes = _partir(p.texto)
    if partes is None:
        return p.diz("cep_invalido")

    cep, numero = partes
    if not numero:
        p.dados["cep_pendente"] = cep
        return MensagemSaida(p.txt("pedir_numero"))

    return _resolver(p, cep, numero)


def receber(p: Passo) -> MensagemSaida:
    """Um estado só: a pessoa manda CEP+número de uma vez, ou o número depois."""
    return receber_numero(p) if "cep_pendente" in p.dados else receber_cep(p)


def receber_numero(p: Passo) -> MensagemSaida:
    """A pessoa mandou o CEP sozinho e agora manda o número."""
    numero = "".join(re.findall(r"\d+", p.texto or ""))
    if not numero:
        return MensagemSaida(p.txt("pedir_numero"))
    return _resolver(p, p.dados.pop("cep_pendente"), numero)


def _resolver(p: Passo, cep: str, numero: str) -> MensagemSaida:
    try:
        endereco = p.backend.resolver_cep(cep, numero)
    except BackendIndisponivel:
        return p.diz("backend_fora")

    if endereco is None:
        return p.diz("cep_nao_achado")

    p.dados["endereco"] = {"cep": endereco.cep, "numero": endereco.numero,
                           "logradouro": endereco.logradouro, "bairro": endereco.bairro,
                           "lat": endereco.lat, "lng": endereco.lng}
    return confere(p)


def confere(p: Passo) -> MensagemSaida:
    """Desenha a confirmação do endereço já resolvido, a entrada do ENDERECO_CONFIRMA.

    Separada de `_resolver` para a retomada poder redesenhar esta tela sem reconsultar
    o CEP. Sem ela, voltar aqui respondia "não entendi" ao botão de continuar.
    """
    endereco = endereco_de(p.dados)
    p.ir("ENDERECO_CONFIRMA")
    return MensagemSaida(p.txt("confere_endereco", endereco=str(endereco)),
                         botoes=BOTOES_CONFIRMA,
                         local=Local(endereco.lat, endereco.lng, "Seu endereço",
                                     str(endereco)))


def confirmar(p: Passo) -> MensagemSaida:
    from creche_bot.conversa.passos.escolas import pedir_horario

    if p.msg.escolha == "confirma":
        tela = pedir_horario(p)
        return replace(tela, texto=f"{p.txt('endereco_confirmado')}\n\n{tela.texto}")

    if p.msg.escolha == "corrige":
        p.dados.pop("endereco", None)
        return pedir_cep(p)

    return p.diz("nao_entendi", botoes=BOTOES_CONFIRMA)


def endereco_de(dados: dict) -> Endereco:
    e = dados["endereco"]
    return Endereco(e["cep"], e["numero"], e["logradouro"], e["bairro"],
                    e["lat"], e["lng"])
