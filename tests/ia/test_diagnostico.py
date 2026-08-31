"""Chave que não funciona tem que virar frase que a pessoa entende, sem eco da API."""

from __future__ import annotations

from creche_bot.ia.redacao import _motivo, diagnosticar


class FalhaDaApi(Exception):
    """O formato que o SDK da Anthropic levanta: exceção com `status_code`."""

    def __init__(self, status: int, mensagem: str = "") -> None:
        super().__init__(mensagem)
        self.status_code = status


def test_cada_status_vira_uma_frase_diferente():
    assert "não foi reconhecida" in _motivo(FalhaDaApi(401))
    assert "limite de uso" in _motivo(FalhaDaApi(429))
    assert "instável" in _motivo(FalhaDaApi(503))


def test_sem_credito_nao_e_a_mesma_coisa_que_chave_invalida():
    """Duas coisas que a pessoa resolve em lugares diferentes do console."""
    assert "crédito" in _motivo(FalhaDaApi(400, "Your credit balance is too low"))
    assert "crédito" not in _motivo(FalhaDaApi(400, "invalid request"))


def test_o_corpo_da_resposta_nunca_chega_ao_chat():
    erro = FalhaDaApi(401, "organization org-9f2 suspended, contact billing@exemplo.com")
    assert "org-9f2" not in _motivo(erro) and "exemplo.com" not in _motivo(erro)


def test_rede_fora_nao_acusa_a_chave_da_pessoa():
    class APIConnectionError(Exception):
        pass

    assert "rede" in _motivo(APIConnectionError("connection refused"))


def test_formato_errado_e_recusado_sem_tocar_na_rede():
    assert "sk-ant-" in diagnosticar("minha-chave-secreta")
