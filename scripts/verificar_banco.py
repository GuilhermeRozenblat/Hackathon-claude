"""Cria o schema no Postgres e prova que a porta inteira funciona contra ele.

Diagnóstico, não produção. Faz um ciclo completo com um contato de mentira e apaga tudo
pelo mesmo caminho da LGPD art. 18 — se sobrar linha, o script acusa.

    python scripts/verificar_banco.py            # aplica o schema e testa
    python scripts/verificar_banco.py --esquema  # só aplica o schema
    python scripts/verificar_banco.py --apagar   # derruba o schema (pede confirmação)

Nunca imprime a connection string: ela carrega a senha do banco.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from creche_bot.dados.porta import Inscricao  # noqa: E402
from creche_bot.dados.postgres import RepositorioPostgres  # noqa: E402
from creche_bot.segredos import carregar_env  # noqa: E402

CANAL, ID_EXTERNO = "diagnostico", "verificar-banco"


def destino(dsn: str) -> str:
    """Host e banco, sem usuário e sem senha — dá para colar num chat."""
    partes = urlsplit(dsn)
    return f"{partes.hostname}:{partes.port or 5432}{partes.path}"


def main() -> None:
    carregar_env(RAIZ / ".env")
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn or dsn.startswith("coloque"):
        sys.exit("DATABASE_URL não definido. Copie .env.example para .env — veja "
                 "docs/BANCO.md")

    print(f"conectando em {destino(dsn)} …")

    if "--apagar" in sys.argv:
        # O schema guarda inscrição de gente de verdade. Só some se for digitado.
        repo = RepositorioPostgres(dsn, criar_esquema=False)
        if input(f"apagar o schema 'creche' em {destino(dsn)}? [s/N] ").strip() != "s":
            sys.exit("nada foi apagado.")
        repo.apagar_esquema()
        repo.fechar()
        print("schema 'creche' apagado.")
        return

    repo = RepositorioPostgres(dsn)
    print("schema 'creche' aplicado (tabelas, índices e RLS)")

    if "--esquema" in sys.argv:
        repo.fechar()
        return

    contato_id = repo.contato_de(CANAL, ID_EXTERNO)
    assert repo.contato_de(CANAL, ID_EXTERNO) == contato_id, "contato_de não é idempotente"
    print("identidade   ok  (idempotente)")

    repo.registrar_consentimento(contato_id, "v1", CANAL, ID_EXTERNO)
    assert repo.tem_consentimento(contato_id)
    print("consentimento ok")

    repo.salvar_sessao(contato_id, "ESCOLHENDO_ESCOLA", {"cep": "20220-030", "n": 3})
    assert repo.carregar_sessao(contato_id) == ("ESCOLHENDO_ESCOLA",
                                                {"cep": "20220-030", "n": 3})
    print("sessão        ok  (jsonb ida e volta)")

    protocolo = "DIAGNOSTICO-1"
    repo.salvar_inscricao(Inscricao(protocolo, contato_id, "esc-0", "CEI Teste", "Fulana"))
    repo.atualizar_etapa(protocolo, "analise")
    assert repo.inscricao(protocolo).etapa_codigo == "analise"
    print("inscrição     ok")

    repo.enfileirar(protocolo, "etapa_avancou", {"ordem": 1, "acento": "João"})
    (evento,) = [e for e in repo.pendentes() if e.protocolo == protocolo]
    assert evento.variaveis["acento"] == "João", "encoding do jsonb saiu errado"
    repo.marcar_enviado(evento.id)
    assert not [e for e in repo.pendentes() if e.protocolo == protocolo]
    print("outbox        ok  (enfileira, entrega, não repete)")

    repo.gravar_marca("diagnostico", "2026-08-30T00:00:00")
    assert repo.ler_marca("diagnostico") == "2026-08-30T00:00:00"
    print("marca d'água  ok")

    assert repo.apagar_tudo(contato_id) == 1
    assert repo.inscricao(protocolo) is None
    assert repo.id_externo_de(contato_id, CANAL) is None
    assert repo.carregar_sessao(contato_id) == ("INICIO", {})
    print("expurgo LGPD  ok  (não sobrou órfão)")

    repo.fechar()
    print("\nbanco pronto. `make bot` já persiste de verdade.")


if __name__ == "__main__":
    main()
