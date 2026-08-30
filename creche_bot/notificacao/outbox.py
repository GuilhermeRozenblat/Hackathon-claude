"""Transactional outbox: lógica pura, zero SQL. A persistência entra pela porta.

O trabalho é em dois tempos, e separá-los é o que dá idempotência:
  1. `sincronizar()` pergunta ao backend o que mudou e enfileira;
  2. `entregar()` manda o que está na fila e marca.

Se o envio falhar, o evento continua na fila e NÃO é buscado de novo no backend.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from creche_bot.backend.porta import BackendCreche, BackendIndisponivel
from creche_bot.canal.tipos import MensagemSaida
from creche_bot.dados.porta import Repositorio
from creche_bot.dominio.tipos import Situacao
from creche_bot.notificacao.catalogo import renderizar
from creche_bot.notificacao.chaves import POR_TIPO_ETAPA, ChaveTemplate

log = logging.getLogger(__name__)

MARCA = "backend"


class Canal(Protocol):
    def enviar(self, id_externo: str, msg: MensagemSaida) -> None: ...


def variaveis_de(sit: Situacao, nome_crianca: str) -> tuple[ChaveTemplate, dict[str, Any]]:
    """Situação -> (chave, variáveis).

    Despacha por `etapa.tipo`, NUNCA por `etapa.codigo`: o código é vocabulário do backend
    e muda por município; o tipo é nosso e é fechado. Etapa nova que caia num tipo
    conhecido funciona sem código novo.
    """
    e = sit.etapa
    chave = POR_TIPO_ETAPA[e.tipo]
    prazo = e.prazo.strftime("%d/%m") if e.prazo else "sem prazo definido"
    base: dict[str, Any] = {
        "nome_crianca": nome_crianca.split()[0] if nome_crianca else "sua criança",
        "nome_escola": sit.nome_escola,
        "numero": sit.numero,
        "nome_responsavel": "",
    }

    if chave is ChaveTemplate.ETAPA_AVANCOU:
        base |= {"titulo_etapa": e.titulo}
    elif chave is ChaveTemplate.DOCUMENTO_PENDENTE:
        base |= {"pendencias": "\n".join(f"📄 {p.titulo}" for p in e.pendencias)}
    elif chave is ChaveTemplate.ACAO_PRESENCIAL:
        base |= {"endereco": e.endereco_entrega, "prazo": prazo, "lat": e.lat, "lng": e.lng}
    elif chave in (ChaveTemplate.CONVOCACAO, ChaveTemplate.LEMBRETE_CONVOCACAO):
        base |= {"prazo": prazo}
    return chave, base


def sincronizar(backend: BackendCreche, repo: Repositorio) -> int:
    """Pergunta ao backend o que mudou desde a última marca e enfileira o que interessa."""
    try:
        mudancas, nova_marca = backend.mudancas_desde(repo.ler_marca(MARCA))
    except BackendIndisponivel as e:
        log.warning("backend indisponível na sincronização: %s", e)
        return 0

    enfileirados = 0
    for sit in mudancas:
        registro = repo.inscricao(sit.numero)
        if registro is None:
            continue                                   # inscrição de outra instalação
        if registro.etapa_codigo == sit.etapa.codigo:
            continue                                   # nada mudou de fato
        chave, variaveis = variaveis_de(sit, registro.nome_crianca)
        repo.enfileirar(sit.numero, chave.value, variaveis)
        repo.atualizar_etapa(sit.numero, sit.etapa.codigo)
        enfileirados += 1

    repo.gravar_marca(MARCA, nova_marca)
    return enfileirados


def entregar(canal: Canal, repo: Repositorio, limite: int = 50) -> int:
    enviados = 0
    for evento in repo.pendentes(limite):
        id_externo = repo.id_externo_de(evento.contato_id)
        if id_externo is None:
            repo.marcar_enviado(evento.id)             # contato sem canal: não insiste
            continue
        try:
            canal.enviar(id_externo, renderizar(ChaveTemplate(evento.chave),
                                                evento.variaveis))
        except Exception:
            repo.marcar_falha(evento.id)
            log.exception("falha ao entregar evento %s", evento.id)   # id, nunca conteúdo
            continue
        repo.marcar_enviado(evento.id)
        enviados += 1
    return enviados


def rodar_worker(backend: BackendCreche, canal: Canal, repo: Repositorio,
                 intervalo_s: float = 5.0) -> None:
    log.info("worker de outbox no ar")
    while True:
        try:
            sincronizar(backend, repo)
            entregar(canal, repo)
        except Exception:
            log.exception("ciclo do worker falhou")   # nunca deixa a thread morrer
        time.sleep(intervalo_s)
