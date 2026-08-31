"""Modo demonstração: três famílias prontas, para quem vai avaliar o bot em cinco minutos.

Quem abre o Telegram pela primeira vez cai no cadastro do zero: são quatorze perguntas até a
tela das creches, e ninguém adivinha que existe um CPF que reconhece o cadastro do ano
passado. Cada botão daqui carrega uma família de mentira na sessão de quem clicou e devolve
o bot já dentro da tela que vale a pena ver. Dali a conversa segue normal, pelo mesmo
caminho de sempre.

Persona é só um dicionário: `formulario.proximo_campo` pula todo campo que já está em
`dados`, então preencher o contexto basta e nenhum atalho novo entra na máquina.

Os textos ficam aqui, sem passar pelo redator, como em `passos/ia.py`: é andaime de
demonstração, não é a fala do Zé com a família.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date

from creche_bot.canal.tipos import ItemLista, MensagemSaida
from creche_bot.conversa import projecao
from creche_bot.conversa.passos import escolas, pendencias, responsavel
from creche_bot.conversa.sessao import Passo
from creche_bot.dominio.tipos import grupamento_de

VERSAO = "demo/1"

# O CPF que o histórico do backend conhece (`backend/mock.py`). Literal porque a trilha da
# conversa não importa de `backend/`, e porque isto é dado de demonstração, não regra.
CPF_COM_HISTORICO = "52998224725"
# Válido no dígito verificador e sem dono: é o mesmo que a bateria usa.
CPF_FICTICIO = "11144477735"

MENU = ("Modo demonstração 🧪\n\n"
        "Cada família aqui é de mentira, e entra nesta conversa no ponto em que parou. "
        "Isso substitui o que você tiver preenchido.\n\n"
        "A última opção sai da demonstração e usa o bot normal.")

# Lista, não botões: são quatro opções, e a quarta é justamente a saída. Três botões não
# caberiam as duas coisas, e esconder a saída faria a demo virar porta sem maçaneta.
OPCOES = (ItemLista("escolhendo", "Escolhendo creche",
                    "Cadastro respondido, na tela das creches perto do CEP"),
          ItemLista("inscrita", "Já inscrita",
                    "Inscrição efetivada: dá para usar /status e /avancar"),
          ItemLista("volta", "Volta de 2025",
                    "O CPF que o bot reconhece do processo do ano passado"),
          ItemLista("normal", "Sem demo, do zero",
                    "Sai da demonstração e começa a conversa normal"))


def escolher(p: Passo) -> MensagemSaida:
    """`PASSOS["DEMO"]` e `ENTRADAS["DEMO"]`: esta função consome e desenha.

    O turno do `/demo` chega aqui sem escolha, porque comando não é resposta de botão: aí a
    tela é o menu. O toque seguinte volta ao mesmo handler, já com `escolha`.
    """
    if p.msg.escolha == "normal":
        return _sair(p)

    persona = _PERSONAS.get(p.msg.escolha or "")
    if persona is None:
        p.ir("DEMO")
        return MensagemSaida(MENU, lista=OPCOES)

    # Sem consentimento nada é alcançável (LGPD art. 14), e a persona pula os blocos onde
    # ele seria pedido. Versão própria: no banco fica registrado que foi demonstração.
    p.repo.registrar_consentimento(p.contato_id, VERSAO, p.msg.canal, p.msg.id_externo)
    from creche_bot.conversa.passos.ia import decisao

    guardado = decisao(p.dados)   # trocar de persona não desliga a IA que a pessoa ligou
    p.dados.clear()
    p.dados.update(guardado)
    cabecalho, tela = persona(p)
    return replace(tela, texto=f"{cabecalho}\n\n{tela.texto}")


def _sair(p: Passo) -> MensagemSaida:
    """A saída da demonstração: zera a família de mentira e desenha o bloco 0 de sempre.

    Mesmo gesto do "Começar de novo" da retomada, inclusive em não desligar a IA que a
    pessoa cadastrou: recomeçar o cadastro não é uma decisão sobre a chave dela.
    """
    from creche_bot.conversa.passos.entrada import inicio
    from creche_bot.conversa.passos.ia import decisao

    guardado = decisao(p.dados)
    p.dados.clear()
    p.dados.update(guardado)
    return inicio(p)


# ------------------------------------------------------------------ as três famílias
def _escolhendo(p: Passo) -> tuple[str, MensagemSaida]:
    """Parou na escolha das creches, com o endereço já respondido."""
    p.dados.update(_crianca("Helena Martins Rocha", _nascimento(p, 3),
                            "Juliana Martins Rocha"),
                   **_responsavel("Juliana Martins Rocha", CPF_FICTICIO, "21988887777"))
    _ate_as_escolas(p, "22775003", "500", "integral")
    return ("🧪 Demo: você é a Juliana, mãe da Helena, 2 anos, Barra da Tijuca. "
            "Já respondeu tudo até o endereço.", escolas.sugerir(p))


def _inscrita(p: Passo) -> tuple[str, MensagemSaida]:
    """Inscrição efetivada de verdade, para o /status e o /avancar terem o que mostrar."""
    p.dados.update(_crianca("Davi Nogueira Pinto", _nascimento(p, 4),
                            "Carla Nogueira Pinto"),
                   **_responsavel("Carla Nogueira Pinto", CPF_FICTICIO, "21977776666"))
    _ate_as_escolas(p, "20220030", "100", "integral")
    tela = escolas.sugerir(p)
    if not p.dados.get("escolas"):        # backend fora, ou nenhuma creche no raio
        return "🧪 Demo: não deu para montar a inscrição agora.", tela

    p.dados["preferencias"] = [p.dados["escolas"][0]["id"]]
    # A projeção do turno para de gravar assim que existe `numero` (`projecao.py`), e
    # `enviar` põe o número. Sem esta linha a demo deixaria inscrição sem o cadastro que
    # a gerou, que é justamente o que o painel mostra.
    if (cadastro := projecao.cadastro_de(p.contato_id, p.dados)) is not None:
        p.repo.salvar_cadastro(cadastro)
    return ("🧪 Demo: você é a Carla, mãe do Davi, Catete. A inscrição vai ser feita agora, "
            "de verdade. Depois use /status e /avancar.", pendencias.enviar(p))


def _volta(p: Passo) -> tuple[str, MensagemSaida]:
    """O CPF que o histórico reconhece: 27,9% das crianças de 2025 já constavam em 2024."""
    p.dados.update(_crianca("Ana Beatriz da Silva", _nascimento(p, 4),
                            "Maria da Silva Santos"),
                   nome_responsavel="Maria da Silva Santos",
                   cpf_responsavel=CPF_COM_HISTORICO)
    return ("🧪 Demo: você é a Maria, e se inscreveu em 2025. O bot acabou de reconhecer "
            "o cadastro pelo seu CPF.", responsavel.olhar_historico(p))


_PERSONAS = {"escolhendo": _escolhendo, "inscrita": _inscrita, "volta": _volta}


# ---------------------------------------------------------------------- as peças
def _nascimento(p: Passo, anos: int) -> str:
    """Uma data que cai sempre no mesmo grupamento, seja qual for o processo vigente.

    Data fixa apodrece: a de corte anda um ano a cada processo, e a criança da demo
    acabaria "fora da faixa" sozinha, num dia em que ninguém está olhando.
    """
    return date(p.backend.data_de_corte().year - anos, 6, 10).isoformat()


def _crianca(nome: str, nascimento: str, filiacao: str) -> dict:
    """Blocos 1 a 3, a parte da criança. Sem CPF: nada bloqueia a inscrição além do
    consentimento e da faixa etária, e exigir CPF de criança de 0 a 3 derruba família."""
    return {"cpf_crianca": "nao_tenho", "nascimento_crianca": nascimento,
            "origem": "nunca", "tem_especial": "nao_responder", "nome_crianca": nome,
            "filiacao_consta": "consta", "filiacao": filiacao}


def _responsavel(nome: str, cpf: str, telefone: str) -> dict:
    """O resto do bloco 3 e o bloco 4 inteiro."""
    return {"nome_responsavel": nome, "cpf_responsavel": cpf,
            "nascimento_responsavel": "1992-06-14",
            "deficiencia_responsavel": "nao_responder", "telefone": telefone,
            "tem_outro_contato": "nao", "quer_email": "nao"}


def _ate_as_escolas(p: Passo, cep: str, numero: str, horario: str) -> None:
    """Bloco 6 respondido: endereço resolvido pelo backend, grupamento derivado.

    O endereço vem de `resolver_cep` em vez de escrito à mão para o pino cair no lugar
    certo, e os três CEPs do roteiro resolvem sem internet. Backend fora aqui cai no
    `except` de `maquina.processar`, que é o mesmo tratamento do resto do roteiro.
    """
    p.dados["endereco"] = asdict(p.backend.resolver_cep(cep, numero))
    p.dados["grupamento"] = grupamento_de(
        date.fromisoformat(p.dados["nascimento_crianca"]), p.backend.data_de_corte())
    p.dados["horario"] = horario
