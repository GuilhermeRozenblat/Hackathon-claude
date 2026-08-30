"""Backend falso, em memória. Roda ENQUANTO o backend real não existe.

Serve a dois propósitos, e nenhum é "teste unitário":
  1. Validar o bot no Telegram com dados que parecem reais;
  2. Ser o espelho do contrato — quando `BackendHTTP` chegar, os testes que passam aqui
     devem passar lá sem mudar uma linha.

Por isso os números são plausíveis, não redondos. Dado bonito esconde bug de layout.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from creche_bot.dominio.tipos import (
    CadastroExistente,
    DadosExtraidos,
    Etapa,
    Faixa,
    FormaEntrega,
    NotaCorte,
    Pendencia,
    PontoEntrega,
    Situacao,
    Turma,
    VagaSugerida,
)

MATERNAL_I = Turma("Maternal I")
ANO = 2027

# CPF que o data lake "conhece" — digite-o no bot para exercitar o caminho do Bloco 1 SIM.
CPF_CONHECIDO = "11122233344"

_CADASTRO = CadastroExistente(
    cpf=CPF_CONHECIDO,
    nome_candidato="Sofia Ribeiro Alves",
    data_nascimento=date(2024, 3, 18),
    origem_escolar="particular",
    matricula=None,
    tem_necessidade=False,
    nome_mae="Juliana Ribeiro Alves",
    nome_pai="Marcos Alves",
    nome_responsavel="Juliana Ribeiro Alves",
    telefone="(21) 98877-6655",
    email=None,                       # campo faltando de propósito: o resumo tem que
)                                     # mostrar "não informado" e deixar preencher

# (id, nome, bairro, endereço, lat, lng, vagas, nota de corte, km, horário)
_ESCOLAS = [
    ("E1", "Creche Municipal Tia Ciata", "Gamboa", "R. Sacadura Cabral, 190",
     -22.8975, -43.1880, 14, 62.5, 1.1, "8h às 17h"),
    ("E2", "EDI Nise da Silveira", "Santo Cristo", "R. Equador, 843",
     -22.8991, -43.1975, 9, 78.0, 2.3, "7h30 às 17h"),
    ("E3", "Creche Municipal Zilda Arns", "Centro", "Av. Presidente Vargas, 1700",
     -22.9068, -43.1889, 6, 88.5, 3.0, "8h às 16h"),
    ("E4", "EDI Paulo Freire", "Saúde", "R. do Livramento, 55",
     -22.8960, -43.1855, 0, 91.0, 1.4, "8h às 17h"),   # sem vaga: não pode aparecer
]

_CRAS = [
    PontoEntrega("CRAS Gamboa", "R. da Gamboa, 120", "8h às 17h, seg a sex",
                 -22.8968, -43.1902),
    PontoEntrega("CRAS Centro", "Av. Rio Branco, 277 — sala 4", "9h às 16h, seg a sex",
                 -22.9060, -43.1760),
]

_DOCUMENTOS = [
    "Certidão de nascimento da criança",
    "CPF da criança",
    "Comprovante de residência recente",
    "Documento de identidade do responsável",
    "Cartão de vacinação em dia",
]

# Roteiro de etapas do município. A ordem é o "passo N de 5" que o bot mostra.
_ROTEIRO: list[dict[str, Any]] = [
    {"codigo": "inscricao_recebida", "titulo": "Inscrição recebida", "tipo": "aguardando"},
    {"codigo": "envio_documentos", "titulo": "Envio dos documentos", "tipo": "acao_no_chat",
     "pendencias": [("comprovante_residencia", "Comprovante de residência", "chat"),
                    ("cartao_vacina", "Cartão de vacinação", "chat")]},
    {"codigo": "entrega_na_unidade", "titulo": "Entrega dos originais",
     "tipo": "acao_presencial"},
    {"codigo": "aguardando_analise", "titulo": "Análise da secretaria", "tipo": "aguardando"},
    {"codigo": "resultado", "titulo": "Resultado", "tipo": "concluida"},
]


def so_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _faixa(nota: float, todas: list[float]) -> Faixa:
    """Faixa é RELATIVA à lista mostrada. Nota de corte absoluta não diz nada à família,
    que não conhece a própria pontuação."""
    if not todas:
        return "sem_vaga"
    menor, maior = min(todas), max(todas)
    if maior == menor:
        return "media"
    posicao = (nota - menor) / (maior - menor)
    return "alta" if posicao <= 0.33 else "media" if posicao <= 0.66 else "baixa"


class BackendMock:
    def __init__(self) -> None:
        self._situacoes: dict[str, Situacao] = {}
        self._mudadas: list[str] = []
        self._seq = 0

    # ------------------------------------------------------------- data lake
    def buscar_candidato(self, cpf: str, data_nascimento: date) -> CadastroExistente | None:
        if so_digitos(cpf) != CPF_CONHECIDO:
            return None
        if data_nascimento != _CADASTRO.data_nascimento:
            return None            # CPF certo + data errada = não é a mesma criança
        return _CADASTRO

    # ------------------------------------------------------------------ vagas
    def escolas_proximas(self, cep_ou_bairro: str, data_nascimento: date,
                         n: int = 3) -> list[VagaSugerida]:
        abertas = [e for e in _ESCOLAS if e[6] > 0]     # sem vaga não entra no painel
        notas = [e[7] for e in abertas]
        sugestoes = [
            VagaSugerida(
                id_escola=i, nome=nome, bairro=bairro, endereco=end, lat=lat, lng=lng,
                turma=MATERNAL_I, vagas_disponiveis=vagas,
                nota_corte=NotaCorte(nota, ANO - 1), faixa=_faixa(nota, notas),
                distancia_km=km, horario_atendimento=horario,
            )
            for i, nome, bairro, end, lat, lng, vagas, nota, km, horario in abertas
        ]
        sugestoes.sort(key=lambda v: (v.nota_corte.pontos, v.distancia_km))
        return sugestoes[:n]

    # -------------------------------------------------------------- entrega
    def pontos_de_entrega(self, forma: FormaEntrega, id_escola: str,
                          cep_ou_bairro: str) -> list[PontoEntrega]:
        if forma == "cras":
            return list(_CRAS)
        if forma == "creche":
            e = next(x for x in _ESCOLAS if x[0] == id_escola)
            return [PontoEntrega(e[1], e[3], e[9], e[4], e[5])]
        return []

    def documentos_exigidos(self, id_escola: str) -> list[str]:
        return list(_DOCUMENTOS)

    def enviar_documento(self, protocolo: str, arquivo: bytes, mime: str) -> DadosExtraidos:
        # Arquivo minúsculo = foto ruim. Deixa o caminho de confiança baixa testável.
        if len(arquivo) < 1024:
            return DadosExtraidos(confianca="baixa",
                                  observacao="imagem muito pequena, não deu para ler")
        return DadosExtraidos(
            tipo_documento="certidao_nascimento", confianca="alta",
            nome_candidato="Sofia Ribeiro Alves", data_nascimento=date(2024, 3, 18),
            nome_responsavel="Juliana Ribeiro Alves", cep="20220-030",
        )

    # ------------------------------------------------------------- inscrição
    def inscrever(self, dados: dict, preferencias: list[str],
                  forma_entrega: FormaEntrega) -> Situacao:
        self._seq += 1
        protocolo = f"RIO-{ANO}-{self._seq:05d}"
        primeira = next(e for e in _ESCOLAS if e[0] == preferencias[0])
        # Quem entrega presencialmente já nasce na etapa de entrega; quem manda pelo
        # WhatsApp começa em "documentos".
        indice = 2 if forma_entrega in ("creche", "cras") else 1
        situacao = Situacao(protocolo=protocolo, id_escola=primeira[0],
                            nome_escola=primeira[1], etapa=self._etapa(indice, primeira),
                            atualizado_em=datetime.now())
        self._situacoes[protocolo] = situacao
        self._mudadas.append(protocolo)
        return situacao

    def situacao(self, protocolo: str) -> Situacao:
        return self._situacoes[protocolo]

    def mudancas_desde(self, marca: str | None) -> tuple[list[Situacao], str]:
        desde = int(marca or 0)
        return [self._situacoes[p] for p in self._mudadas[desde:]], str(len(self._mudadas))

    # --------------------------------------------- gatilho manual, só para demo
    def avancar(self, protocolo: str) -> Situacao:
        """Empurra para a próxima etapa. NÃO faz parte de `BackendCreche` — é o que o
        comando /avancar usa para exercitar a notificação sem o backend real."""
        atual = self._situacoes[protocolo]
        escola = next(e for e in _ESCOLAS if e[0] == atual.id_escola)
        proxima = min(atual.etapa.ordem, len(_ROTEIRO) - 1)
        nova = Situacao(protocolo, atual.id_escola, atual.nome_escola,
                        self._etapa(proxima, escola), datetime.now())
        self._situacoes[protocolo] = nova
        self._mudadas.append(protocolo)
        return nova

    # -------------------------------------------------------------- internos
    def _etapa(self, indice: int, escola: tuple) -> Etapa:
        passo = _ROTEIRO[indice]
        prazo = date.today() + timedelta(days=10)
        pend = tuple(Pendencia(c, t, e, prazo) for c, t, e in passo.get("pendencias", []))
        presencial = passo["tipo"] == "acao_presencial"
        return Etapa(
            codigo=passo["codigo"], titulo=passo["titulo"], tipo=passo["tipo"],
            ordem=indice + 1, total=len(_ROTEIRO), pendencias=pend,
            prazo=prazo if presencial or pend else None,
            endereco_entrega=escola[3] if presencial else None,
            lat=escola[4] if presencial else None, lng=escola[5] if presencial else None,
        )
