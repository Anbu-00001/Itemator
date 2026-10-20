FROM python:3.12-slim
RUN useradd -m -u 1000 user && pip install --no-cache-dir duckdb==1.1.3
USER user
WORKDIR /home/user/app
COPY --chown=user . .
ENV PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["python", "hf_runner/server.py"]
