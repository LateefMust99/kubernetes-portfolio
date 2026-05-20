# BUILD STAGE 
FROM python:3.11.10-slim AS build

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# RUNTIME STAGE 
FROM python:3.11.10-slim AS runtime

COPY --from=build /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN useradd --create-home --uid 1000 app

COPY app.py .

RUN chown -R app:app /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "\
import urllib.request; \
urllib.request.urlopen('http://localhost:8080/healthz')"

USER app

CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
