FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/switch

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ripgrep ca-certificates docker-cli \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system switch \
    && adduser --system --ingroup switch switch

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker/entrypoint.sh /usr/local/bin/switch-entrypoint

RUN pip install --no-cache-dir .
RUN chmod 0755 /usr/local/bin/switch-entrypoint

ENTRYPOINT ["switch-entrypoint"]

EXPOSE 55600

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "55600"]
