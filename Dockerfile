FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/subtitle-checker
COPY app/ ./app/
RUN mkdir -p /data && chown -R 10001:10001 /data /opt/subtitle-checker
USER 10001:10001
EXPOSE 8097
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8097/health',timeout=2)" || exit 1
CMD ["python", "-m", "app.server"]
