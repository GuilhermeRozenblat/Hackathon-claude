"""Testes dos contratos congelados. Rodam sem banco, sem rede, sem nenhuma trilha pronta.

Se um destes quebra, algum módulo violou uma fronteira — e o flip para o WhatsApp
quebraria em produção.
"""

import pytest

from creche_bot.canal.tipos import Botao, ItemLista, Local, MensagemSaida
from creche_bot.notificacao.chaves import VARIAVEIS, ChaveTemplate


def _botoes(n: int) -> tuple[Botao, ...]:
    return tuple(Botao(f"b{i}", f"Opção {i}") for i in range(n))


def test_tres_botoes_passa():
    assert len(MensagemSaida("Escolha:", botoes=_botoes(3)).botoes) == 3


def test_quatro_botoes_falha():
    """A trava do flip: o WhatsApp aceita 3."""
    with pytest.raises(AssertionError, match="WhatsApp aceita"):
        MensagemSaida("Escolha:", botoes=_botoes(4))


def test_rotulo_longo_falha():
    with pytest.raises(AssertionError, match="rótulo"):
        MensagemSaida("x", botoes=(Botao("b", "CEI Prof.ª Maria Aparecida da Silva"),))


def test_lista_ate_dez():
    itens = tuple(ItemLista(f"i{i}", f"Escola {i}") for i in range(10))
    assert len(MensagemSaida("Perto de você:", lista=itens).lista) == 10
    with pytest.raises(AssertionError):
        MensagemSaida("x", lista=(*itens, ItemLista("i10", "Escola 10")))


def test_botoes_e_lista_nao_coexistem():
    with pytest.raises(AssertionError, match="exclusiv"):
        MensagemSaida("x", botoes=_botoes(1), lista=(ItemLista("i", "t"),))


def test_ids_duplicados_falham():
    with pytest.raises(AssertionError, match="duplicados"):
        MensagemSaida("x", botoes=(Botao("mesmo", "A"), Botao("mesmo", "B")))


def test_texto_vazio_falha():
    with pytest.raises(AssertionError, match="sem texto"):
        MensagemSaida("   ")


def test_local_carrega_coordenadas():
    """sendVenue e o location do WhatsApp exigem lat/lng — endereço não substitui."""
    loc = Local(-23.51, -46.62, "Creche Jardim", "R. das Acácias, 240")
    assert (loc.lat, loc.lng) != (0, 0)


def test_toda_chave_tem_variaveis_declaradas():
    """Template do WhatsApp com variável faltando é erro em produção, não no deploy."""
    assert set(VARIAVEIS) == set(ChaveTemplate)


def test_dominio_nao_importa_infraestrutura():
    """Domínio não conhece canal, IA nem banco. Se conhecer, o flip deixa de ser barato."""
    import glob
    import pathlib
    import re

    for arquivo in glob.glob("creche_bot/dominio/*.py"):
        src = pathlib.Path(arquivo).read_text()
        assert not re.search(
            r"^\s*(from|import)\s+creche_bot\.(canal|ia|dados)", src, re.MULTILINE
        ), f"{arquivo} viola a fronteira do domínio"


def test_fakes_satisfazem_os_protocols():
    """Se um fake sai do contrato, a trilha que depende dele quebra só na integração."""
    from creche_bot.backend.mock import BackendMock
    from creche_bot.backend.porta import BackendCreche
    from fakes.canal_fake import CanalFake

    assert isinstance(BackendMock(), BackendCreche)
    assert hasattr(CanalFake(), "enviar")


def test_ia_nao_usa_api_fora_do_zdr():
    """Files API, Batch e code execution não são elegíveis a ZDR. Documento não passa lá."""
    import glob
    import pathlib
    import re

    proibido = re.compile(
        r"\.files\.|messages\.batches|code_execution|beta\.(agents|sessions)"
        r"|claude-fable|claude-mythos"
    )
    for arquivo in glob.glob("creche_bot/ia/*.py"):
        src = pathlib.Path(arquivo).read_text()
        assert not proibido.search(src), f"{arquivo} usa API não elegível a ZDR"


def test_todo_tipo_de_etapa_tem_template():
    """Etapa nova do backend que caia num tipo conhecido não pode ficar sem notificação."""
    from typing import get_args

    from creche_bot.dominio.tipos import TipoEtapa
    from creche_bot.notificacao.chaves import POR_TIPO_ETAPA

    assert set(POR_TIPO_ETAPA) == set(get_args(TipoEtapa))


def test_etapa_presencial_exige_endereco():
    """Mandar a pessoa à creche sem dizer onde é o pior erro que este bot pode cometer."""
    from creche_bot.dominio.tipos import Etapa

    with pytest.raises(AssertionError, match="não tem endereço"):
        Etapa("entrega", "Entrega", "acao_presencial")

    Etapa("entrega", "Entrega", "acao_presencial", endereco_entrega="R. X, 10")


def test_convocacao_exige_prazo():
    """Prazo vencendo em silêncio é o que faz 7,7% perder a vaga já convocada."""
    from datetime import date

    from creche_bot.dominio.tipos import Etapa

    with pytest.raises(AssertionError, match="não tem prazo"):
        Etapa("convocada", "Vaga liberada", "convocacao")

    Etapa("convocada", "Vaga liberada", "convocacao", prazo=date(2027, 1, 29))


def test_grupamento_sai_da_idade_na_data_de_corte():
    """Bandas medidas na base de 2025. Creche vai até 3 anos e 11 meses; daí para cima
    é pré-escola, e a família precisa saber disso ANTES do resultado."""
    from datetime import date

    from creche_bot.dominio.tipos import grupamento_de

    corte = date(2026, 3, 31)
    assert grupamento_de(date(2025, 6, 1), corte) == "bercario"       # 9 meses
    assert grupamento_de(date(2024, 3, 30), corte) == "maternal_1"    # 24 meses
    assert grupamento_de(date(2023, 3, 30), corte) == "maternal_2"    # 36 meses
    assert grupamento_de(date(2022, 3, 30), corte) == "fora_da_faixa"  # 48 meses


def test_desfecho_e_a_melhor_situacao_entre_as_opcoes():
    """77,8% das linhas "Cancelado pelo sistema" pertencem a inscrição ATENDIDA: é o
    cancelamento automático das outras opções. Mostrar isso cru quebra a confiança."""
    from creche_bot.dominio.tipos import desfecho_entre

    assert desfecho_entre(["nao_seguiu", "vaga_confirmada", "cancelada"]) == "vaga_confirmada"
    assert desfecho_entre(["cancelada", "lista_de_espera"]) == "lista_de_espera"
    assert desfecho_entre(["selecionada", "lista_de_espera"]) == "selecionada"
    assert desfecho_entre([]) == "nao_seguiu"


def test_mock_honra_a_porta_inteira():
    """O mock é o espelho do contrato: BackendHTTP terá que passar nos mesmos testes."""
    from creche_bot.backend.mock import CPF_CONHECIDO, BackendMock

    b = BackendMock()
    endereco = b.resolver_cep("22710-560", "100")
    assert endereco is not None and endereco.bairro == "Curicica"
    assert b.resolver_cep("00000000", "1") is None, "CEP inexistente tem que devolver None"

    vagas = b.escolas_proximas(endereco, "bercario", "integral")
    assert vagas, "endereço conhecido tem que sugerir creche"
    assert all(v.grupamento == "bercario" and v.horario == "integral" for v in vagas)
    # Vaga aberta agora primeiro; depois, a mais perto. Nunca por pontuação.
    assert vagas == sorted(vagas, key=lambda v: (not v.vaga_ociosa, v.distancia_km))
    assert all(c is None or c.ano for v in vagas if (c := v.concorrencia) or True)

    cadastro = b.buscar_por_responsavel(CPF_CONHECIDO)
    assert cadastro is not None and cadastro.criancas
    assert b.buscar_por_responsavel("11144477735") is None

    numero = b.inscrever({"nome_crianca": "Ana", "chave_idempotencia": "k"},
                         [vagas[0].id_escola])
    assert b.inscrever({"chave_idempotencia": "k"}, []) == numero, (
        "chave de idempotência não pode gerar inscrição duplicada")

    for _ in range(6):
        b.avancar(numero)
    assert b.situacao(numero).etapa.tipo == "concluida"

    mudancas, marca = b.mudancas_desde(None)
    assert mudancas and b.mudancas_desde(marca)[0] == [], (
        "marca d\'água não avançou: a outbox duplicaria")


def test_regua_do_processo_e_dado_nao_codigo():
    """Entre 2023 e 2024 só 3 das 13 perguntas sobreviveram e o teto caiu de 465 para
    100 pontos. Régua no código quebra na virada do ano."""
    from creche_bot.backend.mock import BackendMock

    criterios = BackendMock().criterios_do_processo()
    assert criterios, "sem régua o bloco 8 não existe"
    assert {c.grupo for c in criterios} >= {"8.1", "8.2", "8.3", "8.4"}
    assert all(c.sensivel for c in criterios if c.grupo == "8.4"), (
        "situação sensível sem a marca não dispara o consentimento do art. 11")
    # Os critérios opcionais são exatamente os que seria violento exigir.
    opcionais = {c.codigo for c in criterios if c.documento_opcional}
    assert opcionais == {"violencia_domestica", "uso_substancias", "situacao_prisional"}


def test_extracao_de_foto_ruim_nao_inventa_dado():
    from creche_bot.backend.mock import BackendMock

    r = BackendMock().enviar_documento("2026-1", "educacao_especial", b"x" * 10, "image/jpeg")
    assert r.confianca == "baixa"
    assert r.nis is None and r.nome is None


def test_abreviacao_cabe_e_distingue():
    """Nome de creche municipal estoura os 20 chars do WhatsApp com folga."""
    from creche_bot.canal.tipos import MAX_ROTULO, abreviar, botoes_nomeados

    assert abreviar("CEI Prof.ª Maria Aparecida da Silva") == "Maria Aparecida"
    assert abreviar("Creche Jardim das Flores") == "Jardim Flores"
    assert abreviar("CEI Girassol") == "CEI Girassol"

    colisao = botoes_nomeados([
        ("a", "Creche Municipal do Jardim Norte"),
        ("b", "Creche Municipal do Jardim Sul"),
    ])
    rotulos = [b.rotulo for b in colisao]
    assert len(set(rotulos)) == 2, "duas escolas com o mesmo rótulo: o usuário erra e não sabe"
    assert all(len(r) <= MAX_ROTULO for r in rotulos)


def test_persistencia_nao_vaza_para_fora_da_pasta():
    """Fora de creche_bot/dados/ não existe SQL, cursor nem conexão.

    Se esta fronteira furar, quem mexe no banco quebra quem mexe no chat — que é
    exatamente o que o desacoplamento existe para impedir.
    """
    import pathlib
    import re

    vazamento = re.compile(
        r"\bsqlite3\b|\bpsycopg\b|\bsqlalchemy\b|\basyncpg\b"
        r"|\bSELECT \b|\bINSERT INTO\b|\bDELETE FROM\b|\bUPDATE \w+ SET\b"
        r"|\.cursor\(|\.execute\(|\.commit\(",
        re.IGNORECASE,
    )
    # __main__ é a raiz de composição: é o único lugar que pode escolher a implementação.
    culpados = [
        str(f) for f in pathlib.Path("creche_bot").rglob("*.py")
        if "dados" not in f.parts and f.name != "__main__.py"
        and vazamento.search(f.read_text())
    ]
    assert not culpados, f"persistência vazou para: {culpados}"


def test_as_duas_implementacoes_satisfazem_a_porta():
    from creche_bot.dados.memoria import RepositorioMemoria
    from creche_bot.dados.porta import Repositorio

    assert isinstance(RepositorioMemoria(), Repositorio)

    # O Postgres não é instanciável sem banco, e este teste roda sem nenhum: compare a
    # superfície da classe. O comportamento é cobrado em tests/dados, contra o banco.
    from creche_bot.dados.postgres import RepositorioPostgres

    metodos = {m for m in vars(Repositorio) if not m.startswith("_")}
    assert metodos <= set(dir(RepositorioPostgres)), (
        f"faltam na implementação Postgres: {metodos - set(dir(RepositorioPostgres))}")
