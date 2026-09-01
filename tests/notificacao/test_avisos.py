"""R1 a R4: os fluxos em que o bot fala primeiro.

Por que importam: em 2025, 5.519 famílias (7,7%) foram convocadas e perderam a vaga, e a
maior parte nunca soube que foi chamada. Hoje "não foi avisada" e "foi avisada e desistiu"
viram o mesmo registro no banco. Só a primeira é problema que o bot resolve.
"""

from __future__ import annotations

from datetime import date

import pytest

from creche_bot.backend.mock import BackendMock
from creche_bot.dados.memoria import RepositorioMemoria
from creche_bot.dados.porta import Inscricao
from creche_bot.notificacao.catalogo import renderizar
from creche_bot.notificacao.chaves import VARIAVEIS, ChaveTemplate
from creche_bot.notificacao.outbox import entregar, sincronizar, variaveis_de
from fakes.canal_fake import CanalFake


@pytest.fixture
def cenario():
    backend, repo, canal = BackendMock(), RepositorioMemoria(), CanalFake()
    contato = repo.contato_de("telegram", "555")
    numero = backend.inscrever({"nome_crianca": "Ana Beatriz da Silva"},
                               ["edi-leila-diniz"])
    repo.salvar_inscricao(Inscricao(protocolo=numero, contato_id=contato,
                                    id_escola="edi-leila-diniz",
                                    nome_escola="EDI Leila Diniz",
                                    nome_crianca="Ana Beatriz da Silva",
                                    etapa_codigo="recebida"))
    sincronizar(backend, repo)          # consome a inscrição inicial
    entregar(canal, repo)
    canal.limpar()
    return backend, repo, canal, numero


def test_toda_chave_tem_render_para_telegram():
    """Chave sem template é mensagem que não sai. Cada uma vira um template da Meta."""
    for chave in ChaveTemplate:
        variaveis = {v: "x" for v in VARIAVEIS[chave]}
        assert renderizar(chave, variaveis).texto


def test_variavel_faltando_falha_no_render_nao_no_envio():
    """No WhatsApp, template com variável faltando é erro em produção."""
    with pytest.raises(ValueError, match="faltam as variáveis"):
        renderizar(ChaveTemplate.CONVOCACAO, {"nome_crianca": "Ana"})


def test_r1_cobra_o_documento_pendente(cenario):
    backend, repo, canal, numero = cenario
    backend.avancar(numero)             # -> falta_documento
    assert sincronizar(backend, repo) == 1
    assert entregar(canal, repo) == 1

    msg = canal.ultima
    assert "Faltou um documento" in msg.texto
    assert "Laudo da educação especial" in msg.texto
    assert "não conta na classificação" in msg.texto


def test_r2_convoca_com_prazo_e_botao(cenario):
    backend, repo, canal, numero = cenario
    for _ in range(3):                  # -> convocada
        backend.avancar(numero)
    sincronizar(backend, repo)
    entregar(canal, repo)

    msg = canal.ultima
    assert "Saiu vaga" in msg.texto and "confirmar" in msg.texto
    assert {b.id for b in msg.botoes} == {"confirmar_vaga", "nao_vou_poder"}


def test_r4_resultado_nao_promete_o_que_nao_pode(cenario):
    backend, repo, canal, numero = cenario
    for _ in range(4):                  # -> confirmada
        backend.avancar(numero)
    sincronizar(backend, repo)
    entregar(canal, repo)

    texto = canal.ultima.texto.lower()
    assert "classificada" in texto
    for proibido in ("garantido", "com certeza", "pontuação", "posição"):
        assert proibido not in texto


def test_convocacao_sem_prazo_nem_e_construivel():
    """A guarda vive no tipo: prazo vencendo em silêncio é o vazamento dos 7,7%."""
    from creche_bot.dominio.tipos import Etapa

    with pytest.raises(AssertionError, match="não tem prazo"):
        Etapa("convocada", "Vaga liberada", "convocacao")


def test_entregar_duas_vezes_nao_duplica(cenario):
    backend, repo, canal, numero = cenario
    backend.avancar(numero)
    sincronizar(backend, repo)

    assert entregar(canal, repo) == 1
    assert entregar(canal, repo) == 0, "reprocessar não pode reenviar"


def test_marca_dagua_nao_rebusca_o_que_ja_veio(cenario):
    backend, repo, _, numero = cenario
    backend.avancar(numero)
    assert sincronizar(backend, repo) == 1
    assert sincronizar(backend, repo) == 0, "sem marca, a outbox duplicaria"


def test_despacho_e_por_tipo_nunca_por_codigo():
    """O backend pode inventar um código amanhã; se cair num tipo conhecido, funciona."""
    from creche_bot.dominio.tipos import Etapa, Situacao

    inventada = Situacao(numero="2026-1", nome_crianca="Ana Beatriz",
                         nome_escola="EDI Leila Diniz",
                         etapa=Etapa("conferencia_2a_via_2027", "Conferência",
                                     "acao_presencial", prazo=date(2027, 1, 20),
                                     endereco_entrega="Estrada de Curicica, 200"))
    chave, variaveis = variaveis_de(inventada, "Ana Beatriz da Silva")
    assert chave is ChaveTemplate.ACAO_PRESENCIAL
    assert renderizar(chave, variaveis).texto


def test_nenhuma_variavel_carrega_dado_sensivel(cenario):
    """As variáveis vão para o log da Meta e para a fila. Nome de criança já é o limite."""
    backend, repo, _, numero = cenario
    backend.avancar(numero)
    sincronizar(backend, repo)

    for evento in repo.pendentes():
        texto = " ".join(str(v) for v in evento.variaveis.values()).lower()
        for proibido in ("cpf", "nis", "violência", "deficiência", "preso"):
            assert proibido not in texto


# ------------------------------------------------------- o botão da push tem dono
def test_todo_botao_de_notificacao_e_tratado_pela_conversa():
    """Botão de push é o único do sistema sem tela por trás.

    Ele chega dias ou meses depois — a convocação de junho responde a uma inscrição de
    março —, quando a sessão de 72h já expirou e o despacho por estado não alcança nada.
    Sem dono, o toque em "Confirmar vaga" caía em `INICIO` e a família recebia a saudação
    com o prazo correndo. Este teste falha no dia em que alguém acrescentar um botão novo
    ao catálogo e esquecer de dizer para onde ele leva.
    """
    from creche_bot.conversa.maquina import DA_NOTIFICACAO
    from creche_bot.notificacao.catalogo import renderizar
    from creche_bot.notificacao.chaves import VARIAVEIS, ChaveTemplate

    tratados = set(DA_NOTIFICACAO) | {"retomar"}   # `retomar` entra junto do /start
    for chave in ChaveTemplate:
        msg = renderizar(chave, dict.fromkeys(VARIAVEIS[chave], "x"))
        for botao in msg.botoes:
            assert botao.id in tratados, (
                f"{chave.name} emite o botão {botao.id!r}, que nenhum estado trata: "
                "quem tocar nele recebe a saudação inicial")
