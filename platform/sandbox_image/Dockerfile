# Image d'exécution isolée des agents / skills : minimale, sans secrets, non-root.
FROM python:3.11-slim
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin agent \
 && mkdir -p /work && chown agent:agent /work
WORKDIR /work
USER agent
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "--version"]
