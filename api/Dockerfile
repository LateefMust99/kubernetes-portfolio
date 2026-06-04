# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
RUN useradd --uid 1000 --create-home app
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY app.py .
EXPOSE 8080
USER app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]