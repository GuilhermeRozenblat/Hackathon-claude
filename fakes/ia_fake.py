"""Dublê de IA. Persona e classificação, sem rede e sem gastar token.

A extração NÃO está aqui: é do backend externo (`creche_bot/backend/mock.py`).
"""

from creche_bot.dominio.tipos import Classificacao, Intencao


class IAFake:
    def __init__(self) -> None:
        self.proxima_intencao: Intencao = "responder"
        self.chamadas: list[str] = []

    def classificar(self, texto: str, estado: str) -> Classificacao:
        self.chamadas.append(f"classificar:{estado}")
        return Classificacao(intencao=self.proxima_intencao)

    def redigir(self, instrucao: str, dados: dict) -> str:
        self.chamadas.append(f"redigir:{instrucao[:30]}")
        return f"[persona] {instrucao}"
