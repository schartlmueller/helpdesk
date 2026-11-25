FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Die LDAP-Anbindung (python-ldap) wird beim Installieren übersetzt und
# braucht dafür Compiler und die OpenLDAP-Bibliotheken.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libldap2-dev libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home app \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
