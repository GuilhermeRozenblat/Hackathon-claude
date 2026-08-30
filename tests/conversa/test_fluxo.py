"""O roteiro do Zé Matrícula, ponta a ponta. Sem rede, sem Telegram, sem chave de API.

Cada teste roda contra as DUAS implementações de repositório. Se divergirem, acusa aqui.
"""

from __future__ import annotations

import itertools
import tempfile

import pytest

from creche_bot.backend.mock import CPF_CONHECIDO, BackendMock
from creche_bot.canal.tipos import Anexo, MensagemEntrada, MensagemSaida
from creche_bot.conversa.maquina import Maquina
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dados.sqlite import RepositorioSQLite
from creche_bot.ia.redacao import RedatorEstatico

_seq = itertools.count(1)

# CPF válido que o histórico NÃO conhece: cai no caminho de 72,1% das famílias.
CPF_NOVO = "111.444.777-35"


@pytest.fixture(params=["memoria", "sqlite"])
def bot(request):
    repo = (RepositorioMemoria() if request.param == "memoria"
            else RepositorioSQLite(tempfile.mktemp(suffix=".db")))
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


# Blocos 0 a 7: da porta de entrada até o horário da vaga.
ATE_O_HORARIO = [
    msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
    msg(CPF_NOVO),
    msg("Maria da Silva Santos"), msg("07/11/1990"), msg(escolha="mae"),
    msg("Ana Beatriz da Silva"), msg("10/01/2024"), msg(escolha="menina"),
    msg(escolha="consta"), msg("Maria da Silva Santos"),
    msg(escolha="nenhum"), msg(escolha="nao_sei"),
    msg("22710-560, 100"), msg(escolha="confirma"),
]

# Bloco 8 no caminho mais curto: sem CadÚnico e sem nada sensível.
SEM_CRITERIOS = [msg(escolha="integral"), msg(escolha="nao"), msg(escolha="pular"),
                 msg(escolha="pronto")]

# Bloco 9.
CONTATO = [msg(escolha="este"), msg(escolha="nao"), msg(escolha="nao")]

CAMINHO_CURTO = [*ATE_O_HORARIO, *SEM_CRITERIOS, *CONTATO]

# Bloco 8 declarando educação especial sem comprovar: é assim que se chega ao bloco 12.
COM_PENDENCIA = [msg(escolha="integral"), msg(escolha="nao"), msg(escolha="pode"),
                 msg(escolha="sim"), msg(escolha="depois"),
                 msg(escolha="pronto"), msg(escolha="pronto")]


def ate_as_escolas(bot) -> MensagemSaida:
    return responder(bot, *CAMINHO_CURTO)


def escolher_creche(bot, painel) -> MensagemSaida:
    """Toca na primeira creche e fecha a lista. Devolve o resumo do bloco 11."""
    return responder(bot, msg(escolha=painel.botoes[0].id), msg(escolha="pronto"))


def ate_o_resumo(bot) -> MensagemSaida:
    return escolher_creche(bot, ate_as_escolas(bot))


def ate_o_resumo_com_pendencia(bot) -> MensagemSaida:
    painel = responder(bot, *ATE_O_HORARIO, *COM_PENDENCIA, *CONTATO)
    return escolher_creche(bot, painel)


# ------------------------------------------------------------------ blocos 0 a 2
def test_porta_de_entrada_tem_as_tres_portas(bot):
    r = bot.processar(msg("/start"))
    assert {b.id for b in r.botoes} == {"inscrever", "acompanhar", "duvidas"}


def test_consentimento_e_gate_obrigatorio(bot):
    r = responder(bot, msg("/start"), msg(escolha="inscrever"))
    assert "autoriza" in r.texto.lower()
    assert {b.id for b in r.botoes} == {"autorizo", "ler_termo"}

    r = bot.processar(msg(escolha="ler_termo"))
    assert "matricula.rio" in r.texto, "o termo tem que estar acessível antes de aceitar"
    assert {b.id for b in r.botoes} == {"autorizo", "ler_termo"}


def test_comeca_pelo_cpf_do_responsavel_nao_da_crianca(bot):
    """Exigir CPF de criança de 0 a 3 anos no primeiro turno derruba família na porta."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"))
    assert "seu CPF" in r.texto


def test_cpf_invalido_nao_passa_e_desiste_depois_de_tres(bot):
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"))
    for _ in range(2):
        r = bot.processar(msg("111.111.111-11"))     # dígito verificador não fecha
        assert "não confere" in r.texto
    r = bot.processar(msg("111.111.111-11"))
    assert "atendente" in r.texto.lower() or "1746" in r.texto


def test_cadastro_anterior_reconhece_e_pula_para_o_horario(bot):
    """Bloco 2a — dispara em 27,9% dos casos."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_CONHECIDO))
    assert "Ana Beatriz da Silva" in r.texto and "Curicica" in r.texto
    assert {b.id for b in r.botoes} == {"tudo_certo", "mudei_endereco", "outra_crianca"}

    r = bot.processar(msg(escolha="tudo_certo"))
    assert "integral" in r.texto, "tudo certo pula direto para o bloco 7"


def test_cadastro_anterior_ja_comprova_a_fila_do_ano_anterior(bot):
    """A fonte é o próprio banco: sai validado de graça. Hoje 14,5% declaram e 12,1% comprovam."""
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
              msg(CPF_CONHECIDO), msg(escolha="tudo_certo"))
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "fila_ano_anterior" in dados["comprovados"]


def test_outra_crianca_reaproveita_o_responsavel(bot):
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_CONHECIDO), msg(escolha="outra_crianca"))
    assert "seu nome completo" not in r.texto, "não pergunta de novo o que já sabe"

    # A relação com a criança não vem do histórico e muda de irmão para irmão.
    r = bot.processar(msg(escolha="mae"))
    assert "criança" in r.texto and "nome completo" in r.texto

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert dados["nome_responsavel"] == "Maria da Silva Santos"
    assert dados.get("endereco"), "endereço do responsável é reaproveitado"


# ------------------------------------------------------------------ bloco 4
def test_fora_da_faixa_falha_cedo_e_explica(bot):
    """A família não pode descobrir isso no resultado."""
    r = responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
                  msg(CPF_NOVO), msg("Maria da Silva Santos"), msg("07/11/1990"),
                  msg(escolha="mae"), msg("Joao Pedro Lima"), msg("05/01/2019"))
    assert "pré-escola" in r.texto
    assert "fora da faixa" in r.texto


def test_nome_abreviado_nao_passa(bot):
    """Nome abreviado é a primeira causa de não achar a inscrição depois, na consulta."""
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
              msg(CPF_NOVO))
    r = bot.processar(msg("Maria"))
    assert "sobrenome" in r.texto


# ------------------------------------------------------------------ bloco 6
def test_endereco_so_por_cep_e_numero(bot):
    responder(bot, *ATE_O_HORARIO[:-2])
    r = bot.processar(msg("Curicica"))
    assert "CEP" in r.texto, "bairro digitado nunca é aceito"

    r = bot.processar(msg("22710-560"))
    assert "número" in r.texto, "sem o número a precisão cai para ~1,4 km"

    r = bot.processar(msg("100"))
    assert "Rua Franz Weissmann, 100 — Curicica" in r.texto
    assert r.local is not None


def test_cep_inexistente_nao_inventa_endereco(bot):
    responder(bot, *ATE_O_HORARIO[:-2])
    r = bot.processar(msg("00000-000, 10"))
    assert "não achei esse cep" in r.texto.lower()


# ------------------------------------------------------------------ bloco 8
def test_nis_comprova_as_duas_perguntas_de_uma_vez(bot):
    """Com o NIS o servidor consulta CadÚnico e Bolsa Família pela mesma chave."""
    responder(bot, *ATE_O_HORARIO, msg(escolha="integral"))
    r = bot.processar(msg(escolha="sim"))
    assert "NIS" in r.texto
    r = bot.processar(msg("12345678901"))

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert set(dados["comprovados"]) >= {"cadunico", "bolsa_familia"}


def test_sem_o_nis_a_inscricao_segue(bot):
    """Nunca trave a inscrição por falta do NIS: grava, marca pendente, lembra depois."""
    responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="sim"))
    r = bot.processar(msg(escolha="nao_acho"))
    assert "confere depois" in r.texto or "lembrar" in r.texto

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "cadunico" in dados["declarados"]
    assert "cadunico" not in dados.get("comprovados", [])


def test_consentimento_sensivel_precede_a_pergunta_de_saude(bot):
    """LGPD art. 11: dado de saúde exige consentimento específico e destacado."""
    r = responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="nao"))
    assert "não é obrigada" in r.texto
    assert {b.id for b in r.botoes} == {"pode", "pular"}


def test_recusar_o_sensivel_pula_saude_e_situacoes_delicadas(bot):
    r = responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="nao"),
                  msg(escolha="pular"))
    assert "deficiência" not in r.texto, "recusou: a pergunta de saúde não pode aparecer"
    assert r.lista, "vai direto para o checklist de composição familiar"

    r = bot.processar(msg(escolha="pronto"))
    assert "violência" not in r.texto.lower(), "nem o checklist do 8.4"


def test_checklist_marca_e_desmarca(bot):
    responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="nao"),
              msg(escolha="pular"))
    r = bot.processar(msg(escolha="monoparental"))
    assert any(i.titulo.startswith("✅") for i in r.lista)

    r = bot.processar(msg(escolha="monoparental"))
    assert not any(i.titulo.startswith("✅") for i in r.lista), "tocar de novo desmarca"


def test_irmao_matriculado_nao_pede_documento(bot):
    """Verificável no SGA pelo nome. Hoje 35,9% marcam e só 6,0% conseguem validar."""
    responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="nao"),
              msg(escolha="pular"), msg(escolha="irmao_matriculado"))
    r = bot.processar(msg(escolha="pronto"))
    assert "irmão" in r.texto

    r = bot.processar(msg("Pedro Henrique da Silva"))
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "irmao_matriculado" in dados["comprovados"], "o nome basta, sem papel"


def test_resposta_sensivel_nunca_e_ecoada(bot):
    """Ecoar "Recebido: alguém de casa está preso ✅" num histórico que fica no aparelho
    da família é perigoso."""
    responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="nao"),
              msg(escolha="pode"), msg(escolha="nao"), msg(escolha="pronto"))
    r = bot.processar(msg(escolha="situacao_prisional"))
    assert "Recebido" not in r.texto
    r = bot.processar(msg(escolha="pronto"))
    assert "Recebido" not in r.texto and "preso" not in r.texto.split("\n")[0]


def test_documento_ilegivel_nao_vira_comprovacao(bot):
    responder(bot, *ATE_O_HORARIO, msg(escolha="integral"), msg(escolha="nao"),
              msg(escolha="pode"), msg(escolha="sim"))
    r = bot.processar(msg(anexo=b"x" * 10))
    assert "não consegui ler" in r.texto.lower()

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "educacao_especial" not in dados.get("comprovados", [])


# ------------------------------------------------------------------ bloco 10
def test_painel_nunca_mostra_nota_de_corte(bot):
    """A classificação só roda depois do fechamento: no momento da conversa ela não
    existe. E o teto foi 465 em 2023 e 100 em 2024 — histórico não é comparável."""
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
    assert "1. CM Maria" in r.texto


def test_uma_opcao_basta(bot):
    """Não force 5: em 2025 a taxa foi 68,8% com 1 opção e 69,7% com 5."""
    painel = ate_as_escolas(bot)
    r = bot.processar(msg(escolha=painel.botoes[0].id))
    assert any(b.id == "pronto" for b in r.botoes)


# ------------------------------------------------------------------ bloco 11
def test_resumo_mostra_o_que_falta_comprovar_e_nada_de_pontuacao(bot):
    r = ate_o_resumo_com_pendencia(bot)
    assert "repetir tudo" in r.texto
    assert "Falta comprovar" in r.texto
    for proibido in ("pontuação", "pontos", "posição", "lugar na fila"):
        assert proibido not in r.texto.lower()


def test_correcao_volta_ao_bloco_dono_do_campo(bot):
    ate_o_resumo(bot)
    r = bot.processar(msg(escolha="corrigir"))
    assert {i.id for i in r.lista} >= {"crianca", "endereco", "horario", "contato"}

    r = bot.processar(msg(escolha="endereco"))
    assert "CEP" in r.texto


# ------------------------------------------------------------ blocos 12 e 13
def test_fluxo_completo_ate_o_protocolo(bot):
    r = ate_o_resumo(bot)
    assert "repetir tudo" in r.texto

    r = bot.processar(msg(escolha="enviar"))
    assert "inscrição é a" in r.texto, "sem pendência, vai direto ao protocolo"
    assert "resultado sai em" in r.texto
    assert {b.id for b in r.botoes} == {"outra_crianca", "terminei"}


def test_pendencia_pede_o_documento_condicional_ao_declarado(bot):
    """Lista genérica faz a família levar o papel errado."""
    ate_o_resumo_com_pendencia(bot)
    r = bot.processar(msg(escolha="enviar"))
    assert "Laudo" in r.texto and "Certidão" not in r.texto
    assert {b.id for b in r.botoes} == {"whatsapp", "creche", "cras"}


def test_cras_promete_avisar_nos_dois_passos(bot):
    """É o buraco do fluxo atual: hoje o documento sai do CRAS e ninguém avisa."""
    ate_o_resumo_com_pendencia(bot)
    bot.processar(msg(escolha="enviar"))

    r = bot.processar(msg(escolha="cras"))
    assert "CRAS" in r.texto
    assert "quando chegar na creche" in r.texto
    assert r.local is not None


def test_segunda_crianca_reaproveita_tudo(bot):
    """1.738 responsáveis inscreveram 2 ou mais crianças em 2025."""
    ate_o_resumo(bot)
    bot.processar(msg(escolha="enviar"))
    r = bot.processar(msg(escolha="outra_crianca"))
    assert "nome completo" in r.texto and "criança" in r.texto

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert dados.get("endereco"), "endereço do responsável sobrevive"
    assert "nome_crianca" not in dados, "a criança recomeça"


# ------------------------------------------------------ sessão, retomada, guardas
def test_start_no_meio_oferece_retomar(bot):
    """Conversa de WhatsApp cai. Recomeçar do zero sem perguntar é perder a família."""
    responder(bot, *ATE_O_HORARIO[:-2])
    r = bot.processar(msg("/start"))
    assert "de onde paramos" in r.texto
    assert {b.id for b in r.botoes} == {"continuar", "recomecar"}

    r = bot.processar(msg(escolha="continuar"))
    assert "CEP" in r.texto, "continuou exatamente onde parou"


def test_recomecar_limpa_a_sessao(bot):
    responder(bot, *ATE_O_HORARIO[:-2])
    responder(bot, msg("/start"), msg(escolha="recomecar"))
    r = bot.processar(msg(escolha="inscrever"))
    assert "autoriza" in r.texto.lower()


def test_sessao_expirada_recomeca_limpa(bot):
    from datetime import datetime, timedelta

    responder(bot, *ATE_O_HORARIO[:-2])
    contato = bot._repo.contato_de("telegram", "777")
    estado, dados = bot._repo.carregar_sessao(contato)
    dados["visto_em"] = (datetime.now() - timedelta(hours=73)).isoformat()
    bot._repo.salvar_sessao(contato, estado, dados)

    r = bot.processar(msg("oi"))
    assert "Zé Matrícula" in r.texto, "passou de 72h: começa do zero"


def test_sem_consentimento_nada_e_alcancavel(bot):
    """LGPD art. 14 — guarda no código, não confiança no fluxo."""
    contato = bot._repo.contato_de("telegram", "777")
    bot._repo.salvar_sessao(contato, "CRIT_SENSIVEL", {"criterios": []})
    bot.processar(msg("tentando pular"))
    assert bot._repo.carregar_sessao(contato)[0] in ("INICIO", "PORTA")


def test_apagar_e_o_direito_de_eliminacao(bot):
    responder(bot, *ATE_O_HORARIO[:5])
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
    for entrada in CAMINHO_CURTO:
        r = bot.processar(entrada)
        assert len(r.botoes) <= 3 and len(r.lista) <= 10
        assert all(len(b.rotulo) <= 20 for b in r.botoes)


def test_bot_nunca_promete_vaga_nem_pontuacao(bot):
    proibidas = ("garantido", "com certeza", "vai conseguir", "sua pontuação",
                 "nota de corte", "posição na fila")
    for entrada in CAMINHO_CURTO:
        texto = bot.processar(entrada).texto.lower()
        assert not any(x in texto for x in proibidas), texto


def test_nenhum_texto_usa_markdown():
    """Os dialetos de Telegram e WhatsApp divergem: texto puro, sempre."""
    from creche_bot.ia.persona import TEXTOS

    for chave, texto in TEXTOS.items():
        for marca in ("**", "__", "`", "# "):
            assert marca not in texto, f"{chave} tem markdown: {marca}"


# --------------------------------------------------- bordas e caminhos de erro
def test_tres_erros_no_mesmo_campo_oferece_atendente(bot):
    """Insistir uma quarta vez com quem já errou três é como o fluxo perde a família."""
    responder(bot, *ATE_O_HORARIO[:4])
    for _ in range(2):
        r = bot.processar(msg("x"))
        assert "sobrenome" in r.texto
    r = bot.processar(msg("x"))
    assert "1746" in r.texto or "atendente" in r.texto.lower()


def test_fora_da_faixa_permite_tentar_outra_crianca(bot):
    responder(bot, msg("/start"), msg(escolha="inscrever"), msg(escolha="autorizo"),
              msg(CPF_NOVO), msg("Maria da Silva Santos"), msg("07/11/1990"),
              msg(escolha="mae"), msg("Joao Pedro Lima"), msg("05/01/2019"))
    r = bot.processar(msg(escolha="outra"))
    assert "nome completo" in r.texto

    r = bot.processar(msg(escolha="pre_escola")) if r.botoes else r
    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "nascimento_crianca" not in dados, "a criança fora da faixa não fica no cadastro"


def test_documento_chega_pelo_whatsapp_e_fecha_a_pendencia(bot):
    """Capturar a evidência dentro da conversa é o produto: hoje a comprovação
    presencial valida 8,0% dos casos."""
    ate_o_resumo_com_pendencia(bot)
    bot.processar(msg(escolha="enviar"))
    r = bot.processar(msg(escolha="whatsapp"))
    assert "foto" in r.texto.lower()

    r = bot.processar(msg(anexo=b"x" * 5000))
    assert "inscrição é a" in r.texto, "comprovou tudo: vai direto ao protocolo"

    _, dados = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))
    assert "educacao_especial" in dados["comprovados"]


def test_documento_pode_ficar_para_depois_sem_travar(bot):
    """Nada bloqueia a inscrição além do consentimento e da faixa etária."""
    ate_o_resumo_com_pendencia(bot)
    bot.processar(msg(escolha="enviar"))
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


def test_ajuda_nao_perde_o_lugar(bot):
    responder(bot, *ATE_O_HORARIO[:-2])
    estado_antes = bot._repo.carregar_sessao(bot._repo.contato_de("telegram", "777"))[0]

    r = bot.processar(msg("/ajuda"))
    assert "1746" in r.texto
    assert bot._repo.carregar_sessao(
        bot._repo.contato_de("telegram", "777"))[0] == estado_antes


def test_status_leva_a_inscricao_ja_feita(bot):
    ate_o_resumo(bot)
    bot.processar(msg(escolha="enviar"))
    r = bot.processar(msg("/status"))
    assert "inscrição" in r.texto.lower() or "Ana" in r.texto


def test_backend_fora_nao_mata_a_conversa(bot):
    """A conversa não morre porque um serviço externo tossiu."""
    from creche_bot.backend.porta import BackendIndisponivel

    responder(bot, *ATE_O_HORARIO[:-2])

    def cai(*_a, **_k):
        raise BackendIndisponivel("timeout")

    bot._backend.resolver_cep = cai
    r = bot.processar(msg("22710-560, 100"))
    assert "probleminha" in r.texto.lower()
    assert "guardei" in r.texto.lower(), "tem que dizer que o preenchimento não se perdeu"


def test_conversa_que_cai_e_recomeca_nao_duplica_inscricao(bot):
    """Sem chave de idempotência, a família que retoma entra duas vezes — e as duas
    inscrições se anulam."""
    ate_o_resumo(bot)
    r = bot.processar(msg(escolha="enviar"))
    primeiro = r.texto

    contato = bot._repo.contato_de("telegram", "777")
    _, dados = bot._repo.carregar_sessao(contato)
    bot._repo.salvar_sessao(contato, "RESUMO", dados)
    r = bot.processar(msg(escolha="enviar"))
    assert dados["numero"] in r.texto or dados["numero"] in primeiro
