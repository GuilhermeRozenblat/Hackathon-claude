# Imagem do painel público (creche-conectada-v2.html).
#
# O COPY é a linha de defesa: só entram a página, os CSVs do mapa e o servidor.
# `.env`, banco, testes e o código do bot não existem dentro da imagem, então não
# há caminho — nem bug de path traversal — que os alcance.
#
# Contexto de build = raiz do repositório. O Railway usa este arquivo por causa
# do `dockerfilePath` em railway.json.

FROM python:3.12-slim

# Sem dependência nenhuma: o servidor é stdlib pura.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY creche-conectada-v2.html ./creche-conectada-v2.html
COPY creche_bot/MapaFilaCreche/*.csv ./creche_bot/MapaFilaCreche/
COPY deploy/servidor_site.py ./deploy/servidor_site.py

# Não roda como root.
RUN useradd --create-home --uid 10001 painel && chown -R painel:painel /app
USER painel

EXPOSE 8080
CMD ["python", "deploy/servidor_site.py"]
