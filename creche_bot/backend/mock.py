"""Backend falso, com os dados do roteiro v2. É o que roda hoje.

Espelha `BackendCreche` por inteiro: quando o `BackendHTTP` do outro time subir, ele
terá que passar nos mesmos testes. Nenhum dado aqui é real — números, escolas e pessoas
saíram do roteiro, e os percentuais que aparecem nos comentários vieram da base
histórica de 2021 a 2025 citada lá.

ponytail: dado em tupla literal. São 3 escolas e 12 critérios; um seeder de banco para
isso seria mais código que os dados.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import date, datetime, timedelta
from functools import lru_cache

from creche_bot.dominio.tipos import (
    CadastroAnterior,
    Concorrencia,
    CriancaConhecida,
    Criterio,
    DadosExtraidos,
    Desfecho,
    Endereco,
    Etapa,
    FormaEntrega,
    Grupamento,
    Horario,
    Pendencia,
    PontoEntrega,
    Situacao,
    VagaSugerida,
)

# CPF de teste com dígito verificador válido. Qualquer outro CPF válido cai no caminho
# "não achei cadastro" — 72,1% dos casos em 2025.
CPF_CONHECIDO = "52998224725"
NUMERO_CONHECIDO = "2026-0847213"

_CURICICA = Endereco(cep="22710560", numero="100", logradouro="Rua Franz Weissmann",
                     bairro="Curicica", lat=-22.9601, lng=-43.4048)

log = logging.getLogger(__name__)

# CEPs do roteiro: resolvem sem rede, e é o que mantém teste e demo determinísticos.
# Fora daqui o mock consulta a BrasilAPI — ver `_buscar_cep`.
_CEPS: dict[str, tuple[str, str, float, float]] = {
    "22710560": ("Rua Franz Weissmann", "Curicica", -22.9601, -43.4048),
    "22775003": ("Avenida Ayrton Senna", "Barra da Tijuca", -22.9946, -43.3654),
    "20220030": ("Rua do Catete", "Catete", -22.9262, -43.1776),
}

# id, nome, endereço, lat, lng, grupamentos, horários, km, vaga ociosa,
# (famílias por vaga, ano), referência, polo
_ESCOLAS: tuple[tuple, ...] = (
    ("edi-leila-diniz", "EDI Leila Diniz", "Estrada de Curicica, 200", -22.9585, -43.4021,
     ("bercario", "maternal_1", "maternal_2"), ("integral", "parcial"),
     0.4, True, None, "", "POLO CURICICA"),
    ("cm-crianca-do-futuro", "CM Criança do Futuro", "Rua Mapendi, 55", -22.9673, -43.3959,
     ("bercario", "maternal_1"), ("integral",),
     1.2, False, (5.0, 2025), "", "POLO CURICICA"),
    ("cm-maria-conceicao", "CM Maria da Conceição S. de Carvalho",
     "Av. Salvador Allende, 1200", -22.9750, -43.3901,
     ("bercario", "maternal_1", "maternal_2"), ("integral", "parcial"),
     1.8, False, (13.0, 2025), "RIO 2", "POLO JACAREPAGUA"),
)

# A régua do processo 195/2025, como ela viria de `ic.pergunta_processo`. Ordem, pesos e
# texto mudam todo ano — por isso isto é dado, e o bot lê em vez de saber.
_CRITERIOS: tuple[Criterio, ...] = (
    Criterio("cadunico", "Família inscrita no CadÚnico", 51, "8.1",
             documento="Número do NIS"),
    Criterio("bolsa_familia", "Recebe Bolsa Família ou Cartão Carioca", 2, "8.1",
             documento="Número do NIS"),
    Criterio("educacao_especial",
             "A criança tem deficiência, transtorno do desenvolvimento ou altas habilidades",
             25, "8.2", sensivel=True, documento="Laudo ou relatório médico"),
    Criterio("monoparental", "A criança é criada por só uma pessoa responsável", 4, "8.3",
             documento="Certidão de nascimento"),
    Criterio("refugiada", "A família está no Brasil como refugiada", 2, "8.3",
             documento="Protocolo de refúgio ou documento do CONARE"),
    Criterio("irmao_matriculado", "A criança tem irmão ou irmã já matriculado na rede",
             0, "8.3"),
    Criterio("violencia_domestica", "Alguém de casa está em situação de violência doméstica",
             4, "8.4", sensivel=True,
             documento="B.O., medida protetiva ou encaminhamento", documento_opcional=True),
    Criterio("responsavel_deficiencia", "Algum responsável pela criança tem deficiência",
             3, "8.4", sensivel=True, documento="Laudo"),
    Criterio("doenca_cronica", "Alguém de casa tem doença crônica grave", 3, "8.4",
             sensivel=True, documento="Laudo ou relatório médico"),
    Criterio("uso_substancias", "Alguém de casa faz uso abusivo de álcool ou outras drogas",
             2, "8.4", sensivel=True,
             documento="Declaração ou encaminhamento", documento_opcional=True),
    Criterio("situacao_prisional",
             "Alguém de casa está preso ou saiu da prisão nos últimos 5 anos", 2, "8.4",
             sensivel=True, documento="Declaração", documento_opcional=True),
)

_CRAS: tuple[PontoEntrega, ...] = (
    PontoEntrega("CRAS Curicica", "Estrada dos Bandeirantes, 4100",
                 "Segunda a sexta, 9h às 17h", -22.9612, -43.4103),
    PontoEntrega("CRAS Taquara", "Rua André Rocha, 800", "Segunda a sexta, 9h às 17h",
                 -22.9280, -43.3812),
)

# Desfechos mockados: um por estado possível, para o bloco C ser andável inteiro.
# A frequência de 2025 está no comentário — é o peso real de cada tela.
_DESFECHOS: tuple[Desfecho, ...] = (
    Desfecho(NUMERO_CONHECIDO, "Ana Beatriz da Silva", date(2024, 1, 10),   # 67,7%
             "vaga_confirmada", ("EDI Leila Diniz", "CM Criança do Futuro"),
             escola_atendida="EDI Leila Diniz",
             endereco_escola="Estrada de Curicica, 200", lat=-22.9585, lng=-43.4021,
             inicio_das_aulas=date(2027, 2, 8)),
    Desfecho("2026-0847220", "Pedro Henrique da Silva", date(2022, 3, 15),  # 11,2%
             "lista_de_espera", ("EDI Leila Diniz", "CM Criança do Futuro"),
             pendencias=("cadunico",)),
    Desfecho("2026-0847231", "Lucas Andrade", date(2023, 7, 2),            # 9,5%
             "nao_seguiu", ("CM Criança do Futuro",)),
    Desfecho("2026-0847244", "Sofia Ribeiro", date(2023, 11, 20),          # 7,7%
             "perdeu_prazo", ("EDI Leila Diniz",),
             escola_atendida="EDI Leila Diniz", prazo_confirmacao=date(2027, 1, 29)),
    Desfecho("2026-0847255", "Miguel Fontes", date(2024, 2, 5),            # 3,8%
             "cancelada", ("CM Maria da Conceição S. de Carvalho",)),
    Desfecho("2026-0847266", "Helena Braga", date(2023, 5, 9),             # 0,2%
             "selecionada", ("EDI Leila Diniz",), escola_atendida="EDI Leila Diniz",
             endereco_escola="Estrada de Curicica, 200",
             prazo_confirmacao=date(2027, 1, 29)),
    Desfecho("2026-0847277", "Théo Nogueira", date(2024, 4, 18),           # 0,0%
             "ativa", ("CM Criança do Futuro",)),
)

# Etapas que o mock percorre para alimentar as notificações R1 a R4.
_ROTEIRO_ETAPAS: tuple[Etapa, ...] = (
    Etapa("recebida", "Inscrição recebida", "aguardando"),
    Etapa("falta_documento", "Falta comprovação", "acao_no_chat",
          pendencias=(Pendencia("educacao_especial", "Laudo da educação especial", "chat"),)),
    Etapa("classificada", "Classificação divulgada", "aguardando"),
    Etapa("convocada", "Vaga liberada", "convocacao", prazo=date.today() + timedelta(days=7)),
    Etapa("confirmada", "Vaga confirmada", "concluida"),
)


# O bot despacha por `TipoEtapa`; a consulta mostra `EstadoInscricao`. Uma tabela liga
# as duas visões — e o BackendHTTP fará o mesmo a partir do status bruto do banco.
_ESTADO_POR_ETAPA: dict[str, str] = {
    "aguardando": "ativa",
    "acao_no_chat": "ativa",
    "acao_presencial": "ativa",
    "convocacao": "selecionada",
    "concluida": "vaga_confirmada",
    "encerrada": "nao_seguiu",
}


def so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


_BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{}"


@lru_cache(maxsize=512)
def _buscar_cep(cep: str) -> tuple[str, str, float, float] | None:
    """CEP de verdade, para o mock não travar a conversa nos três CEPs do roteiro.

    Vai só o CEP — nunca o número, nunca o nome, e a resposta não é logada. CEP sozinho
    é dado público dos Correios; o número da casa, que junto com ele localiza a família,
    fica aqui dentro.

    ponytail: o backend do município resolve isto do lado de lá, com a base de logradouro
    e o geocoder dele. Enquanto ele não sobe, o dublê consulta a BrasilAPI. Rede fora ou
    CEP inexistente devolve None — o mesmo caminho de antes, "não achei esse CEP".
    """
    if len(cep) != 8 or cep.startswith("00"):
        return None   # nenhum CEP brasileiro começa com 00: nem gasta a consulta
    # Sem User-Agent próprio a BrasilAPI devolve 403 para o urllib.
    pedido = urllib.request.Request(_BRASILAPI.format(cep),
                                    headers={"User-Agent": "creche-bot"})
    try:
        with urllib.request.urlopen(pedido, timeout=4) as r:
            d = json.load(r)
    except Exception:
        log.warning("consulta de CEP falhou; caindo para CEP não encontrado")
        return None

    logradouro = d.get("street") or d.get("city") or ""
    bairro = d.get("neighborhood") or d.get("city") or ""
    if not logradouro:
        return None
    coord = (d.get("location") or {}).get("coordinates") or {}
    try:
        lat, lng = float(coord["latitude"]), float(coord["longitude"])
    except (KeyError, TypeError, ValueError):
        lat, lng = _CURICICA.lat, _CURICICA.lng   # sem geocoder, o pino não é o forte do mock
    return logradouro, bairro, lat, lng


class BackendMock:
    def __init__(self, processo_aberto: bool = True) -> None:
        self._processo_aberto = processo_aberto
        self._situacoes: dict[str, Situacao] = {}
        self._por_chave: dict[str, str] = {}
        self._etapa_de: dict[str, int] = {}
        self._nascimento: dict[str, date] = {}
        self._mudadas: list[str] = []
        self._seq = 0

    # ------------------------------------------------------------- processo
    def periodo_de_inscricao(self) -> tuple[date, date]:
        hoje = date.today()
        if self._processo_aberto:
            return hoje - timedelta(days=2), hoje + timedelta(days=10)
        return date(hoje.year - 1, 12, 9), date(hoje.year - 1, 12, 12)

    def data_do_resultado(self) -> date:
        return self.periodo_de_inscricao()[1] + timedelta(days=40)

    def data_de_corte(self) -> date:
        """31/03 do ano letivo seguinte — regra do processo, não constante do bot."""
        return date(self.periodo_de_inscricao()[1].year + 1, 3, 31)

    def criterios_do_processo(self) -> list[Criterio]:
        return list(_CRITERIOS)

    # ------------------------------------------------------------ histórico
    def buscar_por_responsavel(self, cpf: str) -> CadastroAnterior | None:
        if so_digitos(cpf) != CPF_CONHECIDO:
            return None
        return CadastroAnterior(
            cpf=CPF_CONHECIDO, nome_responsavel="Maria da Silva Santos",
            data_nascimento=date(1992, 6, 14), telefone="21998877665",
            endereco=_CURICICA,
            criancas=(CriancaConhecida("Ana Beatriz da Silva", date(2024, 1, 10)),),
            esperou_na_fila=True,
        )

    # ------------------------------------------------------------- endereço
    def resolver_cep(self, cep: str, numero: str) -> Endereco | None:
        digitos = so_digitos(cep)
        dados = _CEPS.get(digitos) or _buscar_cep(digitos)
        if dados is None:
            return None
        logradouro, bairro, lat, lng = dados
        return Endereco(digitos, numero, logradouro, bairro, lat, lng)

    # ---------------------------------------------------------------- oferta
    def escolas_proximas(self, endereco: Endereco, grupamento: Grupamento,
                         horario: Horario, n: int = 3) -> list[VagaSugerida]:
        sugestoes = [
            VagaSugerida(
                id_escola=eid, nome=nome, endereco=end, lat=lat, lng=lng,
                grupamento=grupamento, horario=horario, distancia_km=km,
                vaga_ociosa=ociosa,
                concorrencia=Concorrencia(*conc) if conc else None,
                referencia=ref, polo=polo, horario_atendimento="Segunda a sexta, 8h às 16h",
            )
            for eid, nome, end, lat, lng, grupos, horarios, km, ociosa, conc, ref, polo
            in _ESCOLAS
            if grupamento in grupos and horario in horarios
        ]
        # Vaga aberta agora vem primeiro; depois, a mais perto. Nunca por pontuação.
        sugestoes.sort(key=lambda v: (not v.vaga_ociosa, v.distancia_km))
        return sugestoes[:n]

    # ------------------------------------------------------------ inscrição
    def validar_nis(self, nis: str) -> tuple[bool, tuple[str, ...]]:
        digitos = so_digitos(nis)
        if len(digitos) != 11:
            return False, ()
        # Com o NIS o servidor consulta as duas bases de uma vez.
        return True, ("cadunico", "bolsa_familia")

    def inscrever(self, dados: dict, preferencias: list[str]) -> str:
        # Conversa de WhatsApp cai e recomeça. Sem esta chave, a família que retoma
        # entra duas vezes no processo e as duas inscrições se anulam.
        chave = dados.get("chave_idempotencia")
        if chave and chave in self._por_chave:
            return self._por_chave[chave]

        self._seq += 1
        numero = f"{self.data_de_corte().year}-{self._seq:07d}"
        nome_escola = next((e[1] for e in _ESCOLAS if e[0] in preferencias), "creche")
        self._situacoes[numero] = Situacao(
            numero=numero, nome_crianca=dados.get("nome_crianca", "a criança"),
            nome_escola=nome_escola, etapa=_ROTEIRO_ETAPAS[0], atualizado_em=datetime.now())
        self._etapa_de[numero] = 0
        if (nasc := dados.get("nascimento_crianca")):
            self._nascimento[numero] = date.fromisoformat(nasc)
        self._mudadas.append(numero)
        if chave:
            self._por_chave[chave] = numero
        return numero

    def enviar_documento(self, numero: str, codigo_criterio: str,
                         arquivo: bytes, mime: str) -> DadosExtraidos:
        if len(arquivo) < 1024:
            return DadosExtraidos(confianca="baixa", observacao="imagem pequena demais")
        if codigo_criterio in ("cadunico", "bolsa_familia"):
            return DadosExtraidos("comprovante_nis", "alta", nis="12345678901")
        return DadosExtraidos("laudo_medico", "alta")

    def pontos_de_entrega(self, forma: FormaEntrega, id_escola: str,
                          cep: str) -> list[PontoEntrega]:
        if forma == "cras":
            return list(_CRAS)
        escola = next((e for e in _ESCOLAS if e[0] == id_escola), _ESCOLAS[0])
        return [PontoEntrega(escola[1], escola[2], "Segunda a sexta, 8h às 16h",
                             escola[3], escola[4])]

    # -------------------------------------------------------------- consulta
    def _vivas(self) -> list[Desfecho]:
        """Inscrições feitas nesta sessão também são consultáveis.

        Sem isto, quem acabou de se inscrever pelo bot e manda /status ouve que não tem
        inscrição — e é justamente quem mais volta para conferir.
        """
        return [
            Desfecho(numero=s.numero, nome_crianca=s.nome_crianca,
                     data_nascimento=self._nascimento.get(s.numero, date(1900, 1, 1)),
                     estado=_ESTADO_POR_ETAPA[s.etapa.tipo],
                     escolas=(s.nome_escola,), escola_atendida=s.nome_escola,
                     prazo_confirmacao=s.etapa.prazo,
                     data_resultado=self.data_do_resultado(),
                     pendencias=tuple(x.codigo for x in s.etapa.pendencias))
            for s in self._situacoes.values()
        ]

    def consultar_por_numero(self, numero: str, nascimento: date) -> list[Desfecho]:
        alvo = numero.strip()
        return [d for d in (*_DESFECHOS, *self._vivas())
                if d.numero == alvo and d.data_nascimento == nascimento]

    def consultar_por_nome(self, nome: str, nascimento: date,
                           filiacao: str) -> list[Desfecho]:
        alvo = " ".join(nome.lower().split())
        return [d for d in (*_DESFECHOS, *self._vivas())
                if d.nome_crianca.lower() == alvo and d.data_nascimento == nascimento]

    def consultar_por_responsavel(self, cpf: str) -> list[Desfecho]:
        if so_digitos(cpf) != CPF_CONHECIDO:
            return []
        return [d for d in _DESFECHOS if d.nome_crianca.endswith("da Silva")]

    # --------------------------------------------------------- notificações
    def situacao(self, numero: str) -> Situacao:
        return self._situacoes[numero]

    def mudancas_desde(self, marca: str | None) -> tuple[list[Situacao], str]:
        desde = int(marca or 0)
        novas = self._mudadas[desde:]
        return [self._situacoes[n] for n in novas], str(len(self._mudadas))

    def avancar(self, numero: str) -> Situacao:
        """Só existe no mock: empurra uma etapa para demonstrar R1 a R4 sem o backend."""
        indice = min(self._etapa_de[numero] + 1, len(_ROTEIRO_ETAPAS) - 1)
        self._etapa_de[numero] = indice
        anterior = self._situacoes[numero]
        self._situacoes[numero] = Situacao(
            numero=numero, nome_crianca=anterior.nome_crianca,
            nome_escola=anterior.nome_escola, etapa=_ROTEIRO_ETAPAS[indice],
            atualizado_em=datetime.now())
        self._mudadas.append(numero)
        return self._situacoes[numero]
