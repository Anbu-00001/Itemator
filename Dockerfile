# The checks over HTTP (itemator/serve.py) for Cloud Run. Only the package is copied: no tests, results or war-room files.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 itemator
WORKDIR /app
COPY itemator/ /app/itemator/
USER itemator
CMD ["python", "-E", "-m", "itemator.serve"]
