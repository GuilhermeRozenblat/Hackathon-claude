"""Semeia o banco com conversas de demonstração, para o painel ter o que mostrar.

O painel lê o banco ao vivo. Banco vazio, painel vazio: funil, régua, creches escolhidas e
outbox aparecem todos como "nenhum registro". Este script enche as onze tabelas dirigindo a
própria máquina de estados, uma conversa por contato, cada uma parando num ponto diferente
do roteiro — porque é o degrau entre um estado e o seguinte que conta a história do abandono.

Não escreve SQL: fala pela `Repositorio`, como todo o resto do projeto fora de `dados/`.

    python scripts/semear_demo.py            # semeia no banco de DATABASE_URL
    python scripts/semear_demo.py --memoria  # ensaio, sem tocar em banco nenhum
    python scripts/semear_demo.py --apagar   # remove os contatos de demonstração

Os contatos vivem no canal "demo", nunca em "telegram". É isso que torna o seed reversível e
seguro: sem identidade de Telegram, a entrega de notificação não manda mensagem para ninguém.

Nunca imprime a connection string: ela carrega a senha do banco.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from creche_bot.backend.mapa import BackendMapa  # noqa: E402
from creche_bot.canal.tipos import MensagemEntrada  # noqa: E402
from creche_bot.conversa.maquina import Maquina  # noqa: E402
from creche_bot.dados.memoria import RepositorioMemoria  # noqa: E402
from creche_bot.dados.porta import EventoInscricao, Repositorio  # noqa: E402
from creche_bot.ia.redacao import RedatorEstatico  # noqa: E402
from creche_bot.notificacao.chaves import ChaveTemplate  # noqa: E402
from creche_bot.segredos import carregar_env  # noqa: E402

CANAL = "demo"
CPF = "111.444.777-35"          # válido no dígito verificador e sem dono

# Os três CEPs que o backend resolve sem internet, com o número da casa.
ENDERECOS = ("22710-560, 100", "20220-030, 50", "22775-003, 500")

# Uma linha do tempo plausível para quem já se inscreveu, além do "recebida" que o próprio
# roteiro grava. Vai pela porta, não pelo `outbox.sincronizar`: aquele lê e reescreve a marca
# d'água compartilhada, e um processo à parte rebobinaria a marca do worker que está no ar.
DEPOIS_DO_PROTOCOLO = (("classificada", "aguardando", "Inscrição classificada"),
                       ("convocada", "convocacao", "Convocação para a matrícula"))


def destino(dsn: str) -> str:
    partes = urlsplit(dsn)
    return f"{partes.hostname}:{partes.port or 5432}{partes.path}"


def caminho(nascimento: str, nome: str, responsavel: str, endereco: str) -> list[tuple]:
    """O roteiro inteiro como pares (texto, escolha). Cortar no meio é o abandono.

    `"@primeira"` significa "toque no primeiro botão da tela anterior": com a oferta real
    o id da creche é o código da unidade, e não dá para escrever aqui.
    """
    return [
        ("/start", None), (None, "inscrever"), (None, "autorizo"),
        (CPF, None), (nascimento, None),                          # bloco 1
        (None, "nunca"), (None, "pular"),                         # bloco 2 + gate do art. 11
        (nome, None), (None, "consta"), (responsavel, None),      # bloco 3
        (responsavel, None), (CPF, None), ("07/11/1990", None),
        ("21999998888", None), (None, "nao"), (None, "nao"),      # bloco 4
        (None, "certo"),                                          # bloco 5
        (endereco, None), (None, "confirma"), (None, "integral"),  # bloco 6
        (None, "@primeira"), (None, "pronto"),                    # bloco 7
        (None, "confirmar"),
        (None, "sim"), ("12345678901", None), (None, "pronto"),   # a régua, com CadÚnico
    ]


# Onde cada conversa para: um estado, ou o campo cuja resposta já entrou. Índice não serve,
# porque mexer no roteiro desalinharia o seed em silêncio; e o estado sozinho não bastaria,
# já que o bloco de cadastro inteiro acontece dentro de `CADASTRO`. Repetir `PROTOCOLO` é o
# que dá inscrição a mais de um contato.
PARADAS = ("nascimento_crianca", "nome_crianca", "cpf_responsavel", "CONTATO", "RESUMO",
           "ENDERECO_CEP", "HORARIO", "ESCOLAS", "CONFIRMA_ESCOLAS", "CRIT_CADUNICO",
           "PROTOCOLO", "PROTOCOLO", "PROTOCOLO")


def conversar(maquina: Maquina, repo: Repositorio, id_externo: str,
              turnos: list[tuple], ate: str) -> None:
    """Anda o roteiro até o estado pedido. Chegar lá e parar É o abandono que o painel mede."""
    contato_id = repo.contato_de(CANAL, id_externo)
    anterior = None
    for i, (texto, escolha) in enumerate(turnos):
        if escolha == "@primeira":
            if not (anterior and anterior.botoes):
                return                       # sem creche na lista, a conversa para aqui
            escolha = anterior.botoes[0].id
        anterior = maquina.processar(MensagemEntrada(
            canal=CANAL, id_externo=id_externo, id_mensagem=f"{id_externo}-{i}",
            texto=texto, escolha=escolha))
        estado, dados = repo.carregar_sessao(contato_id)
        if estado == ate or ate in dados:
            return


def semear(repo: Repositorio) -> None:
    backend = BackendMapa()
    maquina = Maquina(backend, RedatorEstatico(), repo)
    corte = backend.data_de_corte().year
    protocolos: list[tuple[str, str]] = []

    for i, parada in enumerate(PARADAS, 1):
        id_externo = f"demo-{i:02d}"
        # Três idades: berçário, maternal I e maternal II, para o painel não ter uma turma só.
        nascimento = date(corte - 2 - i % 3, 6, 10).strftime("%d/%m/%Y")
        turnos = caminho(nascimento, f"Criança Demo {i:02d}",
                         f"Responsável Demo {i:02d}", ENDERECOS[i % len(ENDERECOS)])
        conversar(maquina, repo, id_externo, turnos, parada)

        contato_id = repo.contato_de(CANAL, id_externo)
        estado, dados = repo.carregar_sessao(contato_id)
        print(f"{id_externo}  parou em {estado}")
        if (numero := dados.get("numero")):
            protocolos.append((numero, dados.get("nome_crianca", "")))

    _linha_do_tempo(repo, protocolos)


def _linha_do_tempo(repo: Repositorio, protocolos: list[tuple[str, str]]) -> None:
    """Etapas e avisos das inscrições que chegaram ao fim: é o que dá conteúdo às vistas
    de etapas e de outbox. Uma fica na fila de propósito, para o painel mostrar as duas."""
    for numero, nome in protocolos:
        inscricao = repo.inscricao(numero)
        for codigo, tipo, titulo in DEPOIS_DO_PROTOCOLO:
            repo.registrar_evento(EventoInscricao(protocolo=numero, etapa_codigo=codigo,
                                                  tipo=tipo, titulo=titulo))
            repo.enfileirar(numero, ChaveTemplate.ETAPA_AVANCOU.value,
                            {"nome_crianca": nome.split()[0] if nome else "a criança",
                             "nome_escola": inscricao.nome_escola if inscricao else "",
                             "numero": numero, "nome_responsavel": "",
                             "titulo_etapa": titulo})
        repo.atualizar_etapa(numero, DEPOIS_DO_PROTOCOLO[-1][0])

    pendentes = repo.pendentes()
    for evento in pendentes[:-1]:            # a última continua na fila
        repo.marcar_enviado(evento.id)
    print(f"\n{len(protocolos)} inscrições, {len(pendentes)} avisos "
          f"({max(len(pendentes) - 1, 0)} entregues, o resto na fila)")


def apagar(repo: Repositorio) -> None:
    total = 0
    for i in range(1, len(PARADAS) + 1):
        total += repo.apagar_tudo(repo.contato_de(CANAL, f"demo-{i:02d}"))
    print(f"contatos de demonstração apagados ({total} inscrições junto)")


def main() -> None:
    carregar_env(RAIZ / ".env")

    if "--memoria" in sys.argv:
        print("ensaio em memória, nada é gravado\n")
        semear(RepositorioMemoria())
        return

    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn or dsn.startswith("coloque"):
        sys.exit("DATABASE_URL não definido. Copie .env.example para .env. Veja "
                 "docs/BANCO.md")

    from creche_bot.dados.postgres import RepositorioPostgres

    print(f"conectando em {destino(dsn)} …\n")
    repo = RepositorioPostgres(dsn)
    apagar(repo) if "--apagar" in sys.argv else semear(repo)
    repo.fechar()


if __name__ == "__main__":
    main()
