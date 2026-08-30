"""Repositório em memória. Zero dependência, zero setup, some no restart.

Não é só para teste: é a garantia de que o trabalho no canal e na conversa nunca fica
bloqueado por uma refatoração do banco. `REPOSITORIO=memoria make bot` roda o bot inteiro
sem tocar em disco.
"""

from __future__ import annotations

import itertools
import uuid
from typing import Any

from creche_bot.dados.porta import EventoPendente, Inscricao

MAX_TENTATIVAS = 5


class RepositorioMemoria:
    def __init__(self) -> None:
        self._identidades: dict[tuple[str, str], str] = {}
        self._consentimentos: dict[str, str] = {}
        self._sessoes: dict[str, tuple[str, dict[str, Any]]] = {}
        self._inscricoes: dict[str, Inscricao] = {}
        self._outbox: dict[int, dict[str, Any]] = {}
        self._marcas: dict[str, str] = {}
        self._seq = itertools.count(1)

    # ------------------------------------------------------------- identidade
    def contato_de(self, canal: str, id_externo: str) -> str:
        return self._identidades.setdefault((canal, id_externo), str(uuid.uuid4()))

    def id_externo_de(self, contato_id: str, canal: str = "telegram") -> str | None:
        return next((ext for (c, ext), cid in self._identidades.items()
                     if cid == contato_id and c == canal), None)

    # ----------------------------------------------------------- consentimento
    def registrar_consentimento(self, contato_id: str, versao: str,
                                canal: str, id_externo: str) -> None:
        self._consentimentos[contato_id] = versao

    def tem_consentimento(self, contato_id: str) -> bool:
        return contato_id in self._consentimentos

    # ------------------------------------------------------------------ sessão
    def carregar_sessao(self, contato_id: str) -> tuple[str, dict[str, Any]]:
        estado, contexto = self._sessoes.get(contato_id, ("INICIO", {}))
        return estado, dict(contexto)          # cópia: o chamador muta o dict

    def salvar_sessao(self, contato_id: str, estado: str, contexto: dict[str, Any]) -> None:
        self._sessoes[contato_id] = (estado, dict(contexto))

    # --------------------------------------------------------------- inscrição
    def salvar_inscricao(self, inscricao: Inscricao) -> None:
        self._inscricoes[inscricao.protocolo] = inscricao

    def inscricao(self, protocolo: str) -> Inscricao | None:
        return self._inscricoes.get(protocolo)

    def atualizar_etapa(self, protocolo: str, etapa_codigo: str) -> None:
        if (i := self._inscricoes.get(protocolo)) is not None:
            self._inscricoes[protocolo] = Inscricao(
                i.protocolo, i.contato_id, i.id_escola, i.nome_escola,
                i.nome_crianca, etapa_codigo,
            )

    # ------------------------------------------------------------------ outbox
    def enfileirar(self, protocolo: str, chave: str, variaveis: dict[str, Any]) -> None:
        self._outbox[next(self._seq)] = {
            "protocolo": protocolo, "chave": chave, "variaveis": dict(variaveis),
            "enviado": False, "tentativas": 0,
        }

    def pendentes(self, limite: int = 50) -> list[EventoPendente]:
        saida = []
        for eid, e in sorted(self._outbox.items()):
            if e["enviado"] or e["tentativas"] >= MAX_TENTATIVAS:
                continue
            inscricao = self._inscricoes.get(e["protocolo"])
            if inscricao is None:
                continue
            saida.append(EventoPendente(eid, e["protocolo"], inscricao.contato_id,
                                        e["chave"], e["variaveis"]))
            if len(saida) >= limite:
                break
        return saida

    def marcar_enviado(self, evento_id: int) -> None:
        self._outbox[evento_id]["enviado"] = True

    def marcar_falha(self, evento_id: int) -> None:
        self._outbox[evento_id]["tentativas"] += 1

    # ------------------------------------------------------------ marca d'água
    def ler_marca(self, chave: str) -> str | None:
        return self._marcas.get(chave)

    def gravar_marca(self, chave: str, valor: str) -> None:
        self._marcas[chave] = valor

    # -------------------------------------------------------------------- LGPD
    def apagar_tudo(self, contato_id: str) -> int:
        protocolos = [p for p, i in self._inscricoes.items() if i.contato_id == contato_id]
        for p in protocolos:
            del self._inscricoes[p]
        for eid in [k for k, v in self._outbox.items() if v["protocolo"] in protocolos]:
            del self._outbox[eid]
        self._sessoes.pop(contato_id, None)
        self._consentimentos.pop(contato_id, None)
        for chave in [k for k, v in self._identidades.items() if v == contato_id]:
            del self._identidades[chave]
        return 1
