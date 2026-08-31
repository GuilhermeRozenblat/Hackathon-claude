"""CONTRATO CONGELADO: v2. A fronteira com os dados do município.

Aqui mora o que NÃO é nosso: o histórico da Matrícula Rio, a régua do processo vigente,
a oferta de creches e o andamento da inscrição. O backend é construído por outro time, e
o sistema de registro continua sendo o matricula.rio, e o bot é canal complementar.

## A divisão que importa

  `creche_bot/backend/`  → dados do MUNICÍPIO (histórico, régua, oferta, situação)
  `creche_bot/dados/`    → estado NOSSO (sessão, consentimento, outbox)

São portas diferentes, donos diferentes, e nenhuma sabe da outra.

## Camada anticorrupção

O JSON do backend é dele: nomes de campo, códigos de etapa e formato de data vão mudar
sem nos avisar. **Nada disso pode vazar para `conversa/`.** `BackendHTTP` traduz na
fronteira e devolve só os tipos de `dominio/tipos.py`. Depois de `http.py`, ninguém no
projeto vê `dict`, `json` ou `response`.

## O que o backend decide e o bot não

Pontuação, classificação e posição na fila. A régua é norma (Resolução SME nº 542/2025),
roda em SQL determinístico depois do fechamento das inscrições, e não existe no momento
da conversa. O bot pergunta, comprova e informa; não estima.
"""

from datetime import date
from typing import Protocol, runtime_checkable

from creche_bot.dominio.tipos import (
    CadastroAnterior,
    Criterio,
    DadosExtraidos,
    Desfecho,
    Endereco,
    FormaEntrega,
    Grupamento,
    Horario,
    PanoramaRegiao,
    PontoEntrega,
    Situacao,
    VagaSugerida,
)


class BackendIndisponivel(Exception):
    """O backend caiu, deu timeout ou devolveu lixo.

    Quem chama TRATA. A conversa não pode morrer porque um serviço externo tossiu: o bot
    avisa em linguagem de gente, guarda o que já tem, e oferece tentar de novo.
    """


@runtime_checkable
class BackendCreche(Protocol):
    # ------------------------------------------------------------- processo
    def periodo_de_inscricao(self) -> tuple[date, date]:
        """Início e fim do processo vigente. Fora dele o bot só oferece aviso."""

    def data_do_resultado(self) -> date:
        """Quando a classificação sai. É a única data que o bot promete."""

    def data_de_corte(self) -> date:
        """Data em que a idade da criança é medida para definir o grupamento."""

    def criterios_do_processo(self) -> list[Criterio]:
        """A régua vigente, na ordem, já sem as perguntas autopreenchíveis.

        Vem da tabela do processo. Entre 2023 e 2024 só 3 das 13 perguntas sobreviveram
        e o teto caiu de 465 para 100 pontos: régua no código quebra na virada do ano.
        """

    # ------------------------------------------------------------ histórico
    def buscar_por_responsavel(self, cpf: str) -> CadastroAnterior | None:
        """Consulta o histórico pelo CPF do ADULTO. `None` = preenche do zero.

        O CPF do responsável é a âncora: é mais confiável que o da criança, reconhece
        reinscrição e irmãos, e exigir CPF de criança de 0 a 3 anos no primeiro turno
        derruba família na porta.
        """

    # ------------------------------------------------------------- endereço
    def resolver_cep(self, cep: str, numero: str) -> Endereco | None:
        """CEP + número -> logradouro, bairro e coordenadas. `None` = CEP não existe.

        Bairro e rua NUNCA são digitados: o campo livre gerou 1.608 grafias para ~925
        bairros na base histórica.
        """

    # ---------------------------------------------------------------- oferta
    def escolas_proximas(self, endereco: Endereco, grupamento: Grupamento,
                         horario: Horario, n: int = 3) -> list[VagaSugerida]:
        """Creches que atendem aquele grupamento naquele horário, já ordenadas.

        O bot NÃO reordena nem recalcula. Raio padrão de 2 km: 72,8% dos confirmados
        ficaram na própria 1ª opção, e entre os que trocaram, 82,9% andaram até 2 km.
        """

    def panorama_da_regiao(self, endereco: Endereco) -> PanoramaRegiao | None:
        """O que aconteceu na microárea no processo passado. `None` = sem base.

        Contexto, não previsão: quantas famílias pediram, quantas foram atendidas e
        quantas vagas estão ociosas ali agora. Serve para a família escolher as opções
        sabendo em que região está, que é a decisão que ela realmente toma no bloco 10.

        O bot não deriva probabilidade disso e não pode: a classificação roda depois do
        fechamento das inscrições. Quem renderiza é obrigado a estampar `ano`.
        """

    # ------------------------------------------------------------ inscrição
    def validar_nis(self, nis: str) -> tuple[bool, tuple[str, ...]]:
        """(válido, códigos de critério que ele comprova).

        Com o NIS o servidor consulta CadÚnico e Bolsa Família de uma vez, e é por isso
        que as duas perguntas cabem num turno só.
        """

    def inscrever(self, dados: dict, preferencias: list[str]) -> str:
        """Efetiva e devolve o número da inscrição. `preferencias` em ORDEM.

        `dados` traz também `chave_idempotencia`: conversa que cai e recomeça não pode
        virar inscrição duplicada.
        """

    def enviar_documento(self, numero: str, codigo_criterio: str,
                         arquivo: bytes, mime: str) -> DadosExtraidos:
        """Recebe a comprovação de um critério e devolve o que leu dela."""

    def pontos_de_entrega(self, forma: FormaEntrega, id_escola: str,
                          cep: str) -> list[PontoEntrega]:
        """Onde levar o documento: a creche escolhida, ou os CRAS mais próximos."""

    # -------------------------------------------------------------- consulta
    def consultar_por_numero(self, numero: str, nascimento: date) -> list[Desfecho]:
        """Caminho 1 do portal: número da inscrição + nascimento da criança."""

    def consultar_por_nome(self, nome: str, nascimento: date,
                           filiacao: str) -> list[Desfecho]:
        """Caminho 2 do portal: nome + nascimento + filiação.

        Existe porque nem todo mundo guarda o número, e porque há criança sem filiação
        registrada na certidão. Manter os dois caminhos é obrigatório.
        """

    def consultar_por_responsavel(self, cpf: str) -> list[Desfecho]:
        """Todas as inscrições do responsável. 2,8% têm mais de uma criança."""

    # --------------------------------------------------------- notificações
    def situacao(self, numero: str) -> Situacao:
        """Onde a inscrição está agora. Fonte da verdade para as notificações."""

    def mudancas_desde(self, marca: str | None) -> tuple[list[Situacao], str]:
        """Situações que mudaram desde `marca`. Devolve (mudanças, nova marca).

        Polling com marca d'água em vez de webhook: o backend não precisa nos conhecer,
        e um restart nosso não perde nem duplica evento.
        """
