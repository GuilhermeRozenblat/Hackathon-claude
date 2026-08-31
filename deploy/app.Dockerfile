# Imagem do projeto inteiro: painel, API do painel e o webhook do Telegram.
#
# Substitui `site.Dockerfile`, que servia só o painel estático — por isso o
# `api/banco.json` respondia 404 em produção: o servidor de lá não conhecia banco.
#
# **O COPY continua sendo a linha de defesa.** Só entra na imagem o que o servidor
# precisa. `.env`, `creche.db`, `.git/`, testes e scratchpad não existem lá dentro, então
# não há caminho — nem bug de path traversal — que os alcance. O `.dockerignore` ao lado
# é a segunda tranca, para o contexto de build nem sair da sua máquina.
#
# Contexto de build = raiz do repositório.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# As dependências primeiro, em camada própria: mudar código do bot não reinstala psycopg.
COPY pyproject.toml README.md ./
COPY creche_bot/__init__.py ./creche_bot/
# `[ia]` entra porque `/ia` valida a chave da pessoa com uma chamada real. `[audio]` também:
# ~170 MB de biblioteca, e o modelo (~460 MB) baixa no primeiro boot via `WHISPER=1`.
# `[dev]` não sobe — pytest e ruff não vão para produção. Ver docs/HOSPEDAGEM.md §6.
RUN pip install --no-cache-dir -e ".[ia,audio]"

# O código e os dados, nomeados um a um.
COPY creche_bot/ ./creche_bot/
COPY scripts/painel.py scripts/servidor.py ./scripts/
COPY creche-conectada.html ./creche-conectada.html

# Não roda como root: se algum dia houver execução remota aqui, ela não é privilegiada.
RUN useradd --create-home --uid 10001 painel && chown -R painel:painel /app
USER painel

# A plataforma injeta $PORT; 8080 é só o padrão de quem roda a imagem na mão.
ENV PORT=8080
EXPOSE 8080
CMD ["python", "scripts/servidor.py"]
