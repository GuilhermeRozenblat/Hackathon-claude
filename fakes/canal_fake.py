"""Dublê de canal. Captura o que seria enviado, para B e E testarem sem rede."""

from creche_bot.canal.tipos import MensagemSaida


class CanalFake:
    def __init__(self) -> None:
        self.enviadas: list[tuple[str, MensagemSaida]] = []

    def enviar(self, id_externo: str, msg: MensagemSaida) -> None:
        self.enviadas.append((id_externo, msg))

    @property
    def ultima(self) -> MensagemSaida:
        return self.enviadas[-1][1]

    def limpar(self) -> None:
        self.enviadas.clear()
