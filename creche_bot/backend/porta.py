"""CONTRATO CONGELADO — Fase 0.3. A fronteira com os dados do município.

Aqui mora o que NÃO é nosso: o data lake da Matrícula Rio, a oferta de escolas com nota
de corte, e o andamento da inscrição. O backend é construído por outro time.

## A divisão que importa

  `creche_bot/backend/`  → dados do MUNICÍPIO (data lake, escolas, status)
  `creche_bot/dados/`    → estado NOSSO (sessão, consentimento, outbox)

São portas diferentes, donos diferentes, e nenhuma sabe da outra.

## A regra que faz o link ser barato: camada anticorrupção

O JSON do backend é dele: nomes de campo, códigos de etapa e formato de data vão mudar
sem nos avisar. **Nada disso pode vazar para `conversa/`.** `BackendHTTP` traduz na
fronteira e devolve só os tipos de `dominio/tipos.py`. Depois de `http.py`, ninguém no
projeto vê `dict`, `json` ou `response`.
"""

from datetime import date
from typing import Protocol, runtime_checkable

from creche_bot.dominio.tipos import (
    CadastroExistente,
    DadosExtraidos,
    FormaEntrega,
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
    def buscar_candidato(
        self, cpf: str, data_nascimento: date
    ) -> CadastroExistente | None:
        """Consulta o data lake. `None` = candidato desconhecido, preenche do zero.

        CPF + data de nascimento juntos: CPF sozinho não é prova de vínculo, e a data
        evita mostrar o cadastro de outra criança para quem digitou errado.
        """

    def escolas_proximas(
        self, cep_ou_bairro: str, data_nascimento: date, n: int = 3
    ) -> list[VagaSugerida]:
        """Top N já ordenado, com nota de corte. O bot NÃO reordena nem recalcula."""

    def pontos_de_entrega(self, forma: FormaEntrega, id_escola: str,
                          cep_ou_bairro: str) -> list[PontoEntrega]:
        """Onde levar os documentos: a creche escolhida, ou os CRAS mais próximos."""

    def documentos_exigidos(self, id_escola: str) -> list[str]:
        """Lista para a família conferir antes de sair de casa."""

    def inscrever(self, dados: dict, preferencias: list[str],
                  forma_entrega: FormaEntrega) -> Situacao:
        """Efetiva a inscrição. `preferencias` são ids de escola EM ORDEM.

        Devolve a situação inicial, já com protocolo e primeira etapa.
        """

    def enviar_documento(self, protocolo: str, arquivo: bytes, mime: str) -> DadosExtraidos:
        """Recebe um documento e devolve o que leu dele."""

    def situacao(self, protocolo: str) -> Situacao:
        """Onde a inscrição está agora. Fonte da verdade para as notificações."""

    def mudancas_desde(self, marca: str | None) -> tuple[list[Situacao], str]:
        """Situações que mudaram desde `marca`. Devolve (mudanças, nova marca).

        Polling com marca d'água em vez de webhook: o backend não precisa nos conhecer, e
        um restart nosso não perde nem duplica evento.
        """
