"""O roteiro do Zé Matrícula, ponta a ponta. Sem rede, sem Telegram, sem chave de API.

Cada teste roda contra as DUAS implementações de repositório. Se divergirem, acusa aqui.
"""

from __future__ import annotations

import itertools

import pytest

from creche_bot.backend.mock import CPF_CONHECIDO, BackendMock
from creche_bot.canal.tipos import Anexo, MensagemEntrada, MensagemSaida
from creche_bot.conversa.maquina import Maquina

# Os testes que montam a própria Maquina (processo fechado, por ex.) usam este direto
# e não passam pela fixture `repo`, porque precisam inspecionar o repositório depois.
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.ia.redacao import RedatorEstatico

_seq = itertools.count(1)

# CPF válido que o histórico NÃO conhece: cai no caminho de 72,1% das famílias.
CPF_NOVO = "111.444.777-35"


@pytest.fixture
def bot(repo):
    """`repo` vem de tests/conftest.py já parametrizado: memória e Postgres."""
    return Maquina(BackendMock(), RedatorEstatico(), repo)


def msg(texto=None, escolha=None, anexo=None) -> MensagemEntrada:
    return MensagemEntrada(
        canal="telegram", id_externo="777", id_mensagem=str(next(_seq)),
        texto=texto, escolha=escolha,
        anexo=Anexo(anexo, "image/jpeg") if anexo else None)


def responder(bot, *entradas) -> MensagemSaida:
    resposta = None
    for e in entradas:
        resposta = bot.processar(e if isinstance(e, MensagemEntrada) else msg(e))
    return resposta


# Blocos 0 a 3: da porta de entrada até o fim dos dados pessoais.
# O gate do dado sensível aparece assim que a conversa chega na pergunta de saúde do
# bloco 2: aqui a família recusa, que é o caminho mais curto.
ATE_O_CONTATO = [
    msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
    msg(CPF_NOVO), msg("10/01/2024"),                                    # bloco 1
    msg(escolha="nunca"), msg(escolha="pular"),                          # bloco 2
    msg("Ana Beatriz da Silva"), msg(escolha="consta"),                  # bloco 3
    msg("Maria da Silva Santos"),
    msg("Maria da Silva Santos"), msg(CPF_NOVO), msg("07/11/1990"),
]

# Bloco 4.
CONTATO = [msg("21999998888"), msg(escolha="nao"), msg(escolha="nao")]

ATE_O_RESUMO = [*ATE_O_CONTATO, *CONTATO]

# Blocos 5 e 6: confirma o resumo, dá o endereço e o horário. Termina no painel.
ATE_AS_ESCOLAS = [*ATE_O_RESUMO, msg(escolha="certo"),
                  msg("22710-560, 100"), msg(escolha="confirma"), msg(escolha="integral")]

# A régua, no caminho mais curto: sem CadÚnico e com o sensível recusado lá atrás.
SEM_CRITERIOS = [msg(escolha="nao"), msg(escolha="pronto")]


def ate_as_escolas(bot) -> MensagemSaida:
    return responder(bot, *ATE_AS_ESCOLAS)


def escolher_creche(bot, painel) -> MensagemSaida:
    """Toca na primeira creche e fecha a lista. Devolve a confirmação do bloco 7."""
    return responder(bot, msg(escolha=painel.botoes[0].id), msg(escolha="pronto"))


def ate_a_confirmacao(bot) -> MensagemSaida:
    return escolher_creche(bot, ate_as_escolas(bot))


def ate_o_protocolo(bot) -> MensagemSaida:
    ate_a_confirmacao(bot)
    return responder(bot, msg(escolha="confirmar"), *SEM_CRITERIOS)


# Declara educação especial no bloco 2 e não comprova: é assim que se chega ao bloco 8
# com documento pendente.
COM_PENDENCIA = [
    msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
    msg(CPF_NOVO), msg("10/01/2024"),
    msg(escolha="nunca"), msg(escolha="pode"),
    msg(escolha="sim"), msg(escolha="deficiencia_fisica"),
    msg("Ana Beatriz da Silva"), msg(escolha="consta"),
    msg("Maria da Silva Santos"),
    msg("Maria da Silva Santos"), msg(CPF_NOVO), msg("07/11/1990"),
    msg(escolha="nao"),                                     # deficiência dos pais
    *CONTATO, msg(escolha="certo"),
    msg("22710-560, 100"), msg(escolha="confirma"), msg(escolha="integral"),
]

# Régua com o sensível autorizado: CadÚnico não, laudo fica para depois, dois checklists.
CRITERIOS_COM_PENDENCIA = [msg(escolha="nao"), msg(escolha="depois"),
                           msg(escolha="pronto"), msg(escolha="pronto")]


def ate_o_protocolo_com_pendencia(bot) -> MensagemSaida:
    painel = responder(bot, *COM_PENDENCIA)
    escolher_creche(bot, painel)
    return responder(bot, msg(escolha="confirmar"), *CRITERIOS_COM_PENDENCIA)


# ------------------------------------------------------------------ blocos 0 a 2
def test_porta_de_entrada_tem_as_tres_portas(bot):
    bot.processar(msg("/start"))
    r = bot.processar(msg(escolha="sem_ia"))   # o bloco 0.0 pergunta sobre a IA antes
    assert {b.id for b in r.botoes} == {"inscrever", "acompanhar", "duvidas"}


def test_consentimento_e_gate_obrigatorio(bot):
    r = responder(bot, msg("/start"), msg(escolha="inscrever"))
    assert "autoriza" in r.texto.lower()
    assert {b.id for b in r.botoes} == {"autorizo", "ler_termo"}

    r = bot.processar(msg(escolha="ler_termo"))
    assert "matricula.rio" in r.texto, "o termo tem que estar acessível antes de aceitar"
    assert {b.id for b in r.botoes} == {"autorizo", "ler_termo"}


def test_comeca_pela_pesquisa_da_crianca(bot):
    """Bloco 1 do roteiro: CPF e nascimento do candidato, antes de qualquer outra coisa."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"))
    assert "CPF dela" in r.texto

    # Sem o CPF a inscrição segue: nada bloqueia além do consentimento e da faixa etária.
    assert {b.id for b in r.botoes} == {"nao_tenho"}
    r = bot.processar(msg(escolha="nao_tenho"))
    assert "data de nascimento" in r.texto


def test_cpf_invalido_nao_passa_e_desiste_depois_de_tres(bot):
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"))
    for _ in range(2):
        r = bot.processar(msg("111.111.111-11"))     # dígito verificador não fecha
        assert "não confere" in r.texto
    r = bot.processar(msg("111.111.111-11"))
    assert "atendente" in r.texto.lower() or "1746" in r.texto


def test_cadastro_anterior_aproveita_o_endereco(bot):
    """Dispara em 27,9% dos casos, no CPF do responsável, a única busca que o backend tem."""
    r = responder(bot, *ATE_O_CONTATO[:-2], msg(CPF_CONHECIDO))
    assert "Curicica" in r.texto
    assert {b.id for b in r.botoes} == {"tudo_certo", "mudei_endereco"}

    r = bot.processar(msg(escolha="tudo_certo"))
    assert "data de nascimento" in r.texto, "volta para o formulário de onde saiu"

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert dados["endereco"]["bairro"] == "Curicica"


def test_cadastro_anterior_ja_comprova_a_fila_do_ano_anterior(bot):
    """A fonte é o próprio banco: sai validado de graça. Hoje 14,5% declaram e 12,1% comprovam."""
    responder(bot, *ATE_O_CONTATO[:-2], msg(CPF_CONHECIDO), msg(escolha="tudo_certo"))
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "fila_ano_anterior" in dados["comprovados"]


def test_o_telefone_nunca_vem_do_historico(bot):
    """É por ele que a família é convocada: 7,7% perdem a vaga porque o contato falhou."""
    r = responder(bot, *ATE_O_CONTATO[:-2], msg(CPF_CONHECIDO), msg(escolha="tudo_certo"),
                  msg("07/11/1990"))
    assert "celular" in r.texto


# ------------------------------------------------------------------ bloco 2
def test_origem_em_quatro_opcoes_cabe_em_dois_turnos(bot):
    """4 opções não cabem em 3 botões: a terceira abre a segunda pergunta."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_NOVO), msg("10/01/2024"))
    assert {b.id for b in r.botoes} == {"rede_municipal", "nunca", "outra"}

    r = bot.processar(msg(escolha="outra"))
    assert {b.id for b in r.botoes} == {"particular", "outra_rede"}


def test_quem_ja_estuda_na_rede_pode_nao_ter_a_matricula(bot):
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_NOVO), msg("10/01/2024"), msg(escolha="rede_municipal"))
    assert "matrícula" in r.texto
    assert {b.id for b in r.botoes} == {"nao_tenho_matricula"}

    r = bot.processar(msg(escolha="nao_tenho_matricula"))
    assert "obrigada" in r.texto, "segue para o gate do dado sensível, sem travar"


def test_pergunta_de_saude_exige_consentimento_proprio(bot):
    """LGPD art. 11: a pergunta do bloco 2 é dado de saúde."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_NOVO), msg("10/01/2024"), msg(escolha="nunca"))
    assert "não é obrigada" in r.texto
    assert {b.id for b in r.botoes} == {"pode", "pular"}

    r = bot.processar(msg(escolha="pode"))
    assert "deficiência" in r.texto
    assert "nao_responder" in {b.id for b in r.botoes}, "sempre dá pra não responder"


def test_recusar_o_sensivel_pula_a_pergunta_de_saude_sem_travar(bot):
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_NOVO), msg("10/01/2024"), msg(escolha="nunca"),
                  msg(escolha="pular"))
    assert "deficiência" not in r.texto
    assert "nome completo da criança" in r.texto, "o cadastro continua"


# ------------------------------------------------------------------ bloco 3
def test_fora_da_faixa_falha_cedo_e_explica(bot):
    """A família não pode descobrir isso no resultado, e o bloco 1 já pega isso."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_NOVO), msg("05/01/2019"))
    assert "pré-escola" in r.texto
    assert "fora da faixa" in r.texto


def test_nome_abreviado_nao_passa(bot):
    """Nome abreviado é a primeira causa de não achar a inscrição depois, na consulta."""
    responder(bot, *ATE_O_CONTATO[:7])
    r = bot.processar(msg("Maria"))
    assert "sobrenome" in r.texto


# ------------------------------------------------------------------ bloco 6
def test_endereco_so_por_cep_e_numero(bot):
    responder(bot, *ATE_O_RESUMO, msg(escolha="certo"))
    r = bot.processar(msg("Curicica"))
    assert "CEP" in r.texto, "bairro digitado nunca é aceito"

    r = bot.processar(msg("22710-560"))
    assert "número" in r.texto, "sem o número a precisão cai para ~1,4 km"

    r = bot.processar(msg("100"))
    assert "Rua Franz Weissmann, 100, Curicica" in r.texto
    assert r.local is not None


def test_cep_inexistente_nao_inventa_endereco(bot):
    responder(bot, *ATE_O_RESUMO, msg(escolha="certo"))
    r = bot.processar(msg("00000-000, 10"))
    assert "não achei esse cep" in r.texto.lower()


# ------------------------------------------- perguntas de prioridade (a régua)
def test_nis_comprova_as_duas_perguntas_de_uma_vez(bot):
    """Com o NIS o servidor consulta CadÚnico e Bolsa Família pela mesma chave."""
    ate_a_confirmacao(bot)
    responder(bot, msg(escolha="confirmar"))
    r = bot.processar(msg(escolha="sim"))
    assert "NIS" in r.texto
    r = bot.processar(msg("12345678901"))

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert set(dados["comprovados"]) >= {"cadunico", "bolsa_familia"}


def test_sem_o_nis_a_inscricao_segue(bot):
    """Nunca trave a inscrição por falta do NIS: grava, marca pendente, lembra depois."""
    ate_a_confirmacao(bot)
    responder(bot, msg(escolha="confirmar"), msg(escolha="sim"))
    r = bot.processar(msg(escolha="nao_acho"))
    assert "confere depois" in r.texto or "lembrar" in r.texto

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "cadunico" in dados["declarados"]
    assert "cadunico" not in dados.get("comprovados", [])


def test_a_pergunta_de_saude_nao_e_feita_duas_vezes(bot):
    """A régua repete a pergunta do bloco 2. Perguntar de novo seria invasivo à toa."""
    ate_a_confirmacao(bot)
    r = responder(bot, msg(escolha="confirmar"), msg(escolha="nao"))
    assert "deficiência" not in r.texto
    assert r.lista, "vai direto para o checklist de composição familiar"


def test_recusar_o_sensivel_pula_saude_e_situacoes_delicadas(bot):
    ate_a_confirmacao(bot)
    r = responder(bot, msg(escolha="confirmar"), msg(escolha="nao"))
    assert r.lista, "checklist de composição familiar"

    r = bot.processar(msg(escolha="pronto"))
    assert "violência" not in r.texto.lower(), "recusou lá atrás: nem o checklist do 8.4"


def test_checklist_marca_e_desmarca(bot):
    ate_a_confirmacao(bot)
    responder(bot, msg(escolha="confirmar"), msg(escolha="nao"))
    r = bot.processar(msg(escolha="monoparental"))
    assert any(i.titulo.startswith("✅") for i in r.lista)

    r = bot.processar(msg(escolha="monoparental"))
    assert not any(i.titulo.startswith("✅") for i in r.lista), "tocar de novo desmarca"


def test_irmao_matriculado_nao_pede_documento(bot):
    """Verificável no SGA pelo nome. Hoje 35,9% marcam e só 6,0% conseguem validar."""
    ate_a_confirmacao(bot)
    responder(bot, msg(escolha="confirmar"), msg(escolha="nao"),
              msg(escolha="irmao_matriculado"))
    r = bot.processar(msg(escolha="pronto"))
    assert "irmão" in r.texto

    r = bot.processar(msg("Pedro Henrique da Silva"))
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "irmao_matriculado" in dados["comprovados"], "o nome basta, sem papel"


def test_resposta_sensivel_nunca_e_ecoada(bot):
    """Ecoar "Recebido: alguém de casa está preso ✅" num histórico que fica no aparelho
    da família é perigoso."""
    responder(bot, *COM_PENDENCIA)
    responder(bot, msg(escolha="esc:edi-leila-diniz"), msg(escolha="pronto"),
              msg(escolha="confirmar"), msg(escolha="nao"), msg(escolha="depois"),
              msg(escolha="pronto"))
    r = bot.processar(msg(escolha="situacao_prisional"))
    assert "Recebido" not in r.texto
    r = bot.processar(msg(escolha="pronto"))
    assert "Recebido" not in r.texto and "preso" not in r.texto.split("\n")[0]


def test_toda_resposta_volta_confirmada(bot):
    """A família confere no mesmo balão em que responde, e erro de digitação aparece ali,
    não no resumo do bloco 5. Vale para o que ela digita, para o que ela toca e para a
    saída de fuga do campo aberto."""
    responder(bot, msg("/start"), msg(escolha="inscrever"))

    r = bot.processar(msg(escolha="autorizo"))
    assert "Autorização registrada ✅" in r.texto

    r = bot.processar(msg(escolha="nao_tenho"))          # a fuga do CPF da criança
    assert "Anotei: Não tenho o CPF ✅" in r.texto

    r = bot.processar(msg("10/01/2024"))
    assert "Recebido: 10/01/2024 ✅" in r.texto

    r = bot.processar(msg(escolha="nunca"))              # bloco 2, toque em botão
    assert "Anotei: Nunca estudou ✅" in r.texto


def test_resposta_de_saude_do_formulario_nao_volta_ecoada(bot):
    """A exceção do eco, e é regra, não estilo: dado de saúde não volta escrito num
    histórico que fica no aparelho da família (LGPD art. 11)."""
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
              msg(CPF_NOVO), msg("10/01/2024"), msg(escolha="nunca"))

    r = bot.processar(msg(escolha="pode"))               # autoriza o gate do art. 11
    assert "deficiência" in r.texto.lower()

    r = bot.processar(msg(escolha="nao"))
    assert "Anotei" not in r.texto and "Recebido" not in r.texto


def test_documento_ilegivel_nao_vira_comprovacao(bot):
    responder(bot, *COM_PENDENCIA)
    responder(bot, msg(escolha="esc:edi-leila-diniz"), msg(escolha="pronto"),
              msg(escolha="confirmar"), msg(escolha="nao"))
    r = bot.processar(msg(anexo=b"x" * 10))
    assert "não consegui ler" in r.texto.lower()

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "educacao_especial" not in dados.get("comprovados", [])


# ------------------------------------------------------------------ bloco 6
def test_painel_nunca_mostra_nota_de_corte(bot):
    """A classificação só roda depois do fechamento: no momento da conversa ela não
    existe. E o teto foi 465 em 2023 e 100 em 2024, e histórico não é comparável."""
    r = ate_as_escolas(bot)
    assert "nota de corte" not in r.texto.lower()
    assert "ponto" not in r.texto.lower()


def test_painel_mostra_so_fato_verificavel(bot):
    r = ate_as_escolas(bot)
    assert "vaga aberta agora" in r.texto, "vaga ociosa é fato de hoje"
    assert "famílias por vaga" in r.texto, "concorrência é fato do ano passado"
    assert "em 2025" in r.texto, "e tem que vir rotulada como passado"
    assert "RIO 2" in r.texto, "a família reconhece o lugar pelo apelido"
    assert "m (uns" in r.texto or "km" in r.texto


def test_ordem_de_preferencia_sai_da_sequencia_de_toques(bot):
    painel = ate_as_escolas(bot)
    ids = [b.id for b in painel.botoes]
    bot.processar(msg(escolha=ids[-1]))          # escolhe a última primeiro
    r = bot.processar(msg(escolha="pronto"))
    assert "1️⃣ CM Maria" in r.texto


# ------------------------------------------------------------------ bloco 7
def test_confirmacao_final_mostra_a_lista_na_ordem(bot):
    r = ate_a_confirmacao(bot)
    assert "EDI Leila Diniz" in r.texto
    assert {b.id for b in r.botoes} == {"confirmar", "alterar"}


def test_alterar_devolve_o_painel_e_zera_a_ordem(bot):
    ate_a_confirmacao(bot)
    r = bot.processar(msg(escolha="alterar"))
    assert "Achei estas creches" in r.texto

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert dados["preferencias"] == []


def test_uma_opcao_basta(bot):
    """Não force 5: em 2025 a taxa foi 68,8% com 1 opção e 69,7% com 5."""
    painel = ate_as_escolas(bot)
    r = bot.processar(msg(escolha=painel.botoes[0].id))
    assert any(b.id == "pronto" for b in r.botoes)


# ------------------------------------------------------------------ bloco 5
def test_resumo_repete_o_declarado_e_nada_de_pontuacao(bot):
    r = responder(bot, *ATE_O_RESUMO)
    assert "resumo do que já tenho" in r.texto
    assert "Ana Beatriz da Silva" in r.texto and "(21) 99999-8888" in r.texto
    for proibido in ("pontuação", "pontos", "posição", "lugar na fila"):
        assert proibido not in r.texto.lower()


def test_resumo_nunca_repete_resposta_sensivel(bot):
    """Ecoar dado de saúde num histórico que fica no aparelho da família é o que o
    art. 11 manda evitar: guardar, sim; repetir, não."""
    r = responder(bot, *COM_PENDENCIA[:-4])
    assert "deficiência" not in r.texto.lower()

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert dados["tem_especial"] == "sim", "guardado, mesmo sem aparecer"


def test_correcao_volta_ao_bloco_dono_do_campo(bot):
    responder(bot, *ATE_O_RESUMO)
    r = bot.processar(msg(escolha="corrigir"))
    assert {i.id for i in r.lista} == {"crianca", "responsavel", "contato"}

    r = bot.processar(msg(escolha="contato"))
    assert "celular" in r.texto


# ------------------------------------------------------------------ bloco 8
def test_fluxo_completo_ate_o_protocolo(bot):
    r = ate_o_protocolo(bot)
    assert "inscrição é a" in r.texto, "sem pendência, vai direto ao protocolo"
    assert r.figurinha == "festa", "inscrição feita é fato: aqui pode comemorar"
    assert "resultado sai em" in r.texto
    assert {b.id for b in r.botoes} == {"outra_crianca", "terminei"}


def test_pendencia_pede_o_documento_condicional_ao_declarado(bot):
    """Lista genérica faz a família levar o papel errado."""
    r = ate_o_protocolo_com_pendencia(bot)
    assert "Laudo" in r.texto and "Certidão" not in r.texto
    assert {b.id for b in r.botoes} == {"whatsapp", "creche", "cras"}


def test_cras_promete_avisar_nos_dois_passos(bot):
    """É o buraco do fluxo atual: hoje o documento sai do CRAS e ninguém avisa."""
    ate_o_protocolo_com_pendencia(bot)

    r = bot.processar(msg(escolha="cras"))
    assert "CRAS" in r.texto
    assert "quando chegar na creche" in r.texto
    assert r.local is not None


def test_segunda_crianca_reaproveita_tudo(bot):
    """1.738 responsáveis inscreveram 2 ou mais crianças em 2025."""
    ate_o_protocolo(bot)
    r = bot.processar(msg(escolha="outra_crianca"))
    assert "CPF dela" in r.texto, "recomeça pelo bloco 1, só que da outra criança"

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert dados.get("endereco"), "endereço do responsável sobrevive"
    assert "nome_crianca" not in dados, "a criança recomeça"


# ------------------------------------------------------ sessão, retomada, guardas
def test_start_no_meio_oferece_retomar(bot):
    """Conversa de WhatsApp cai. Recomeçar do zero sem perguntar é perder a família."""
    responder(bot, *ATE_O_RESUMO, msg(escolha="certo"))
    r = bot.processar(msg("/start"))
    assert "de onde paramos" in r.texto
    assert {b.id for b in r.botoes} == {"continuar", "recomecar"}

    r = bot.processar(msg(escolha="continuar"))
    assert "CEP" in r.texto, "continuou exatamente onde parou"
    # "Não peguei o CEP" também contém "CEP": sem esta linha o teste passa com o bug
    # de retomar pelo PASSOS, que consome o "continuar" como se fosse a resposta.
    assert "não peguei" not in r.texto.lower(), "retomada refez a pergunta, não deu erro"


def test_retomar_desenha_a_tela_e_nao_consome_o_botao(bot):
    """Retomada usa ENTRADAS, não PASSOS: o "continuar" não é resposta de campo.

    Cada estado reentrável precisa redesenhar a própria tela. Retomar pelo consumidor
    fazia o bot responder "não peguei o CEP" a uma mensagem que ninguém mandou.
    """
    parar_em = {
        "ENDERECO_CEP": ([*ATE_O_RESUMO, msg(escolha="certo")], "onde vocês moram"),
        "ENDERECO_CONFIRMA": ([*ATE_O_RESUMO, msg(escolha="certo"),
                               msg("22710-560, 100")], "confere se é aqui"),
    }
    for estado, (caminho, esperado) in parar_em.items():
        b = Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria())
        for e in caminho:
            b.processar(e)
        b.processar(msg("/start"))
        r = b.processar(msg(escolha="continuar"))
        assert esperado in r.texto.lower(), f"{estado} não redesenhou: {r.texto!r}"


def test_retomar_no_bloco_8_nao_consome_o_continuar(bot):
    """Mesma armadilha de `test_retomar_desenha_a_tela_e_nao_consome_o_botao`, um nível
    mais fundo: CRIT_NIS e CRIT_ANEXO também precisam de ENTRADAS própria, senão o
    "continuar" da retomada cai no handler que consome resposta de campo — em CRIT_NIS
    isso mostrava "não parece o NIS" para um botão, e em CRIT_ANEXO descartava o
    documento pendente como se a família tivesse escolhido "não tenho agora"."""
    contato = bot._repo.contato_de("telegram", "777")

    bot._repo.salvar_sessao(contato, "CRIT_NIS", {"criterios": []})
    bot.processar(msg("/start"))
    r = bot.processar(msg(escolha="continuar"))
    assert "NIS" in r.texto
    assert "não parece" not in r.texto.lower()

    bot._repo.salvar_sessao(contato, "CRIT_ANEXO", {
        "criterios": [{"codigo": "educacao_especial", "documento": "laudo médico",
                       "rotulo": "x", "grupo": "8.2", "sensivel": False, "opcional": False}],
        "anexo_de": "educacao_especial", "apos_anexo": "CRIT_FAMILIA",
        "anexo_generico": False,
    })
    bot.processar(msg("/start"))
    r = bot.processar(msg(escolha="continuar"))
    assert "laudo médico" in r.texto
    assert {b.id for b in r.botoes} == {"depois"}, "pedindo o documento, não pulando ele"


def test_retomar_no_cadastro_anterior_repete_a_pergunta(bot):
    """Mesma regra para a tela do histórico, que também não é uma pergunta de campo."""
    responder(bot, *ATE_O_CONTATO[:-2], msg(CPF_CONHECIDO))
    bot.processar(msg("/start"))
    r = bot.processar(msg(escolha="continuar"))
    assert {b.id for b in r.botoes} == {"tudo_certo", "mudei_endereco"}
    assert "não entendi" not in r.texto.lower()


def test_recomecar_limpa_a_sessao(bot):
    responder(bot, *ATE_O_RESUMO, msg(escolha="certo"))
    responder(bot, msg("/start"), msg(escolha="recomecar"))
    r = bot.processar(msg(escolha="inscrever"))
    assert "autoriza" in r.texto.lower()


def test_sessao_expirada_recomeca_limpa(bot):
    from datetime import datetime, timedelta

    responder(bot, *ATE_O_RESUMO)
    contato = bot._repo.contato_de("telegram", "777")
    estado, dados = bot._repo.carregar_sessao(contato)
    dados["visto_em"] = (datetime.now() - timedelta(hours=73)).isoformat()
    bot._repo.salvar_sessao(contato, estado, dados)

    r = bot.processar(msg("oi"))
    assert "Zé Matrícula" in r.texto, "passou de 72h: começa do zero"


def test_sem_creche_perto_nao_prende_a_conversa():
    """Beco sem saída: a tela pergunta "outro endereço, ou mudar o horário?" e o estado
    ficava em ESCOLAS sem `dados["escolas"]`. Qualquer resposta estourava KeyError em
    `_painel`, virava "deu um probleminha" e, como a exceção impede o `salvar_sessao`,
    repetia para sempre — a conversa só saía com /start, que apaga o cadastro.
    """
    class SemCreche(BackendMock):
        def escolas_proximas(self, *a, **kw):
            return ()

    repo = RepositorioMemoria()
    bot = Maquina(SemCreche(), RedatorEstatico(), repo)
    r = responder(bot, *ATE_AS_ESCOLAS)
    assert "não achei creche" in r.texto.lower()

    # A resposta seguinte tem que ser atendida, não virar erro nem repetir o erro.
    r2 = bot.processar(msg("22770-005, 50"))
    assert "probleminha" not in r2.texto.lower(), "continua preso no estado sem painel"
    r3 = bot.processar(msg("22770-005, 50"))
    assert "probleminha" not in r3.texto.lower(), "o erro se repete a cada mensagem"


def test_convocacao_meses_depois_nao_cai_na_saudacao(bot):
    """O botão da push chega com a sessão já expirada, e é o caso NORMAL: a inscrição é
    de março e a convocação sai em junho. Sem roteamento, o toque em "Confirmar vaga"
    caía em INICIO e a família lia "quer inscrever uma criança?" com o prazo correndo.
    """
    from datetime import datetime, timedelta

    ate_o_protocolo(bot)
    contato = bot._repo.contato_de("telegram", "777")
    estado, dados = bot._repo.carregar_sessao(contato)
    dados["visto_em"] = (datetime.now() - timedelta(days=90)).isoformat()
    bot._repo.salvar_sessao(contato, estado, dados)

    r = bot.processar(msg(escolha="confirmar_vaga"))
    assert "quer inscrever" not in r.texto.lower(), "caiu na saudação com o prazo correndo"
    assert "Ana" in r.texto or "inscrição" in r.texto.lower(), (
        "o toque tem que abrir a situação da inscrição, não uma conversa nova")


def test_sem_consentimento_nada_e_alcancavel(bot):
    """LGPD art. 14: guarda no código, não confiança no fluxo."""
    contato = bot._repo.contato_de("telegram", "777")
    bot._repo.salvar_sessao(contato, "CRIT_SENSIVEL", {"criterios": []})
    bot.processar(msg("tentando pular"))
    assert bot._repo.carregar_sessao(contato)[0] in ("INICIO", "PORTA", "IA_CONFIG")


def test_apagar_e_o_direito_de_eliminacao(bot):
    responder(bot, *ATE_O_CONTATO[:5])
    r = bot.processar(msg("/apagar"))
    assert "apaguei" in r.texto.lower()
    assert not bot._repo.tem_consentimento(bot._repo.contato_de("telegram", "777"))


def test_fora_do_periodo_nao_promete_inscricao():
    repo = RepositorioMemoria()
    fechado = Maquina(BackendMock(processo_aberto=False), RedatorEstatico(), repo)
    r = responder(fechado, msg("/start"), msg(escolha="inscrever"))
    assert "já fecharam" in r.texto
    assert any(b.id == "avisar" for b in r.botoes)


# ------------------------------------------------------------- limites e tom
def test_nenhuma_tela_estoura_os_limites_do_whatsapp(bot):
    """MensagemSaida já cobra, mas o teste nomeia a intenção e varre o roteiro."""
    for entrada in ATE_AS_ESCOLAS:
        r = bot.processar(entrada)
        assert len(r.botoes) <= 3 and len(r.lista) <= 10
        assert all(len(b.rotulo) <= 20 for b in r.botoes)


def test_bot_nunca_promete_vaga_nem_pontuacao(bot):
    """A chance estimada por creche PODE aparecer; a promessa e a classificação, não.

    O painel do bloco 10 mostra um percentual calculado sobre 2025 (ver
    `backend/mapa.py`). Esta lista é a fronteira que continua de pé: garantia, certeza, e
    a régua que só roda depois do fechamento das inscrições.
    """
    proibidas = ("garantido", "com certeza", "vai conseguir", "sua pontuação",
                 "nota de corte", "posição na fila")
    for entrada in ATE_AS_ESCOLAS:
        texto = bot.processar(entrada).texto.lower()
        assert not any(x in texto for x in proibidas), texto


def test_chance_na_tela_nunca_aparece_sem_o_ano_de_onde_veio():
    """Sem o ano, "33%" vira previsão sobre o processo de agora, que não existe ainda.

    Roda contra o `BackendMapa` de propósito: é ele que produz a chance, e o mock das três
    escolas do roteiro não produziria número nenhum para verificar.
    """
    from creche_bot.backend.mapa import BackendMapa
    from creche_bot.conversa.passos.escolas import _chance

    backend = BackendMapa()
    endereco = backend.resolver_cep("22710560", "100")
    for vaga in backend.escolas_proximas(endereco, "maternal_2", "integral"):
        linha = _chance({"chance": vaga.chance,
                         "concorrencia": (None if vaga.concorrencia is None else
                                          [vaga.concorrencia.familias_por_vaga,
                                           vaga.concorrencia.ano])})
        if linha:
            assert "estimada" in linha, linha
            assert str(vaga.concorrencia.ano) in linha, linha


def test_nenhum_texto_usa_markdown():
    """Os dialetos de Telegram e WhatsApp divergem: texto puro, sempre."""
    from creche_bot.ia.persona import TEXTOS

    for chave, texto in TEXTOS.items():
        for marca in ("**", "__", "`", "# "):
            assert marca not in texto, f"{chave} tem markdown: {marca}"


# --------------------------------------------------- bordas e caminhos de erro
def test_tres_erros_no_mesmo_campo_oferece_atendente(bot):
    """Insistir uma quarta vez com quem já errou três é como o fluxo perde a família."""
    responder(bot, *ATE_O_CONTATO[:7])
    for _ in range(2):
        r = bot.processar(msg("x"))
        assert "sobrenome" in r.texto
    r = bot.processar(msg("x"))
    assert "1746" in r.texto or "atendente" in r.texto.lower()

    # "Tentar de novo" reabre a pergunta zerada, em vez de validar o toque do botão como
    # resposta (o que falhava de novo e devolvia a mesma tela de atendente, sem saída).
    r = bot.processar(msg(escolha="tentar"))
    assert "atendente" not in r.texto.lower() and "1746" not in r.texto
    r = bot.processar(msg("Ana Beatriz da Silva"))
    assert "atendente" not in r.texto.lower()


def test_fora_da_faixa_permite_tentar_outra_crianca(bot):
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
              msg(CPF_NOVO), msg("05/01/2019"))
    r = bot.processar(msg(escolha="outra"))
    assert "CPF dela" in r.texto

    r = bot.processar(msg(escolha="pre_escola")) if r.botoes else r
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "nascimento_crianca" not in dados, "a criança fora da faixa não fica no cadastro"


def test_documento_chega_pelo_whatsapp_e_fecha_a_pendencia(bot):
    """Capturar a evidência dentro da conversa é o produto: hoje a comprovação
    presencial valida 8,0% dos casos."""
    ate_o_protocolo_com_pendencia(bot)
    r = bot.processar(msg(escolha="whatsapp"))
    assert "foto" in r.texto.lower()

    r = bot.processar(msg(anexo=b"x" * 5000))
    assert "inscrição é a" in r.texto, "comprovou tudo: vai direto ao protocolo"

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "educacao_especial" in dados["comprovados"]


def test_documento_pode_ficar_para_depois_sem_travar(bot):
    """Nada bloqueia a inscrição além do consentimento e da faixa etária."""
    ate_o_protocolo_com_pendencia(bot)
    bot.processar(msg(escolha="whatsapp"))
    r = bot.processar(msg(escolha="depois"))
    assert "inscrição é a" in r.texto


def test_fora_do_periodo_liga_o_aviso():
    repo = RepositorioMemoria()
    fechado = Maquina(BackendMock(processo_aberto=False), RedatorEstatico(), repo)
    responder(fechado, msg("/start"), msg(escolha="inscrever"))
    r = fechado.processar(msg(escolha="avisar"))
    assert "avisar" in r.texto.lower()
    assert repo.tem_consentimento(repo.contato_de("telegram", "777"))


def test_fora_do_periodo_nao_liga_aviso_sem_o_botao():
    """Texto livre (ou qualquer toque que não seja "avisar") não é consentimento: só o
    botão "Quero ser avisada" liga o aviso — ver a armadilha documentada no CLAUDE.md."""
    repo = RepositorioMemoria()
    fechado = Maquina(BackendMock(processo_aberto=False), RedatorEstatico(), repo)
    responder(fechado, msg("/start"), msg(escolha="inscrever"))
    r = fechado.processar(msg("não quero, obrigada"))
    assert "não entendi" in r.texto.lower()
    assert not repo.tem_consentimento(repo.contato_de("telegram", "777"))


def test_ajuda_nao_perde_o_lugar(bot):
    responder(bot, *ATE_O_RESUMO)
    estado_antes = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))[0]

    r = bot.processar(msg("/ajuda"))
    assert "1746" in r.texto
    assert bot._repo.carregar_sessao(
        bot._repo.contato_de("telegram", "777"))[0] == estado_antes


def test_status_leva_a_inscricao_ja_feita(bot):
    ate_o_protocolo(bot)
    r = bot.processar(msg("/status"))
    assert "inscrição" in r.texto.lower() or "Ana" in r.texto


def test_backend_fora_nao_mata_a_conversa(bot):
    """A conversa não morre porque um serviço externo tossiu."""
    from creche_bot.backend.porta import BackendIndisponivel

    responder(bot, *ATE_O_RESUMO, msg(escolha="certo"))

    def cai(*_a, **_k):
        raise BackendIndisponivel("timeout")

    bot._backend.resolver_cep = cai
    r = bot.processar(msg("22710-560, 100"))
    assert "probleminha" in r.texto.lower()
    assert "guardei" in r.texto.lower(), "tem que dizer que o preenchimento não se perdeu"


def test_conversa_que_cai_e_recomeca_nao_duplica_inscricao(bot):
    """Sem chave de idempotência, a família que retoma entra duas vezes, e as duas
    inscrições se anulam."""
    primeiro = ate_o_protocolo(bot).texto

    contato = bot._repo.contato_de("telegram", "777")
    _, dados = bot._repo.carregar_sessao(contato)
    bot._repo.salvar_sessao(contato, "CRIT_FAMILIA", dados)
    r = bot.processar(msg(escolha="pronto"))
    assert dados["numero"] in r.texto or dados["numero"] in primeiro


def test_chance_sem_ano_nao_vira_numero_na_tela():
    """Chance sem procedência não sai. É a segunda condição do CLAUDE.md.

    A conta de `backend/mapa.py` tem teto de 95%, e 26% das unidades não têm
    concorrência comparável. Sem esta guarda, essas creches mostravam "chance estimada
    95%" seco: número no teto, sem ano, lido como previsão sobre o processo de agora.
    """
    from creche_bot.conversa.passos.escolas import _chance

    assert _chance({"chance": 0.95, "concorrencia": None}) == ""
    assert _chance({"chance": None, "concorrencia": [5.0, 2025]}) == ""
    linha = _chance({"chance": 0.4, "concorrencia": [5.0, 2025]})
    assert "40%" in linha and "2025" in linha


def test_rodape_so_explica_a_chance_quando_ha_chance_na_tela():
    """Creche sem concorrência comparável não mostra número. Explicar o que não está ali
    deixa o bot falando de "chance" sem exibir nenhuma — 5 das 9 creches de um painel real
    caem nesse caso."""
    from creche_bot.conversa.passos.escolas import _regiao
    from creche_bot.ia.persona import TEXTOS

    class PassoFalso:
        def __init__(self, escolas):
            self.dados = {"regiao": {"bairro": "Curicica", "ano": 2025,
                                     "demanda": 390, "atendidos": 342},
                          "escolas": escolas}

        def txt(self, chave, **v):
            return TEXTOS[chave].format(**v)

    com = _regiao(PassoFalso([{"chance": 0.4, "concorrencia": [5.0, 2025]}]))
    sem = _regiao(PassoFalso([{"chance": 0.95, "concorrencia": None}]))
    assert "estimativa" in com, "com número na tela, a explicação tem que aparecer"
    assert "chance" not in sem.lower(), f"sem número, não pode falar de chance: {sem!r}"
    assert "390 famílias" in sem, "a estatística da região continua nos dois casos"


def test_avancar_nao_existe_com_o_backend_de_producao():
    """`/avancar` empurra etapas e dispara R1 a R4. Em produção seria o bot dizendo
    "Vaga confirmada" para uma família que não tem vaga nenhuma.

    A guarda antiga era `avancar is None`, e nunca disparava: `BackendMapa` herda de
    `BackendMock` e herda o método junto.
    """
    from creche_bot.backend.mapa import BackendMapa

    producao = Maquina(BackendMapa(), RedatorEstatico(), RepositorioMemoria())
    r = producao.processar(msg("/avancar"))
    assert "não existe" in r.texto.lower(), r.texto

    demo = Maquina(BackendMock(), RedatorEstatico(), RepositorioMemoria())
    r = demo.processar(msg("/avancar"))
    assert "não existe" not in r.texto.lower(), "com o mock o comando continua valendo"
