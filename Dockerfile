# syntax=docker/dockerfile:1
# ---------- build stage: install dependencies into a virtualenv ----------
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --upgrade pip && /venv/bin/pip install -r requirements.txt
COPY tools/fetch_fonts.py tools/fetch_fonts.py
RUN mkdir -p app/static/fonts && (/venv/bin/python tools/fetch_fonts.py || echo "font download skipped")

# ---------- runtime stage: minimal, non-root, read-only code ----------
FROM python:3.13-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown app:app /data
WORKDIR /srv/app
COPY --from=build /venv /venv
COPY app ./app
COPY wsgi.py manage.py gunicorn.conf.py ./
COPY --from=build /src/app/static/fonts ./app/static/fonts
COPY content ./content-seed
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod -R a-w /srv/app && chmod 0555 /entrypoint.sh
ENV PATH=/venv/bin:$PATH \
    APP_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTENT_DIR=/data/content \
    INSTANCE_DIR=/data/instance
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" || exit 1
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "wsgi:app"]
