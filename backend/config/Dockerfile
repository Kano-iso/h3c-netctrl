FROM python:3.10-slim

WORKDIR /app

RUN sed -i 's|deb.debian.org|mirrors.volces.com|g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's|security.debian.org|mirrors.volces.com/debian-security|g' /etc/apt/sources.list.d/debian.sources

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.volces.com/pypi/simple/ -r requirements.txt

CMD ["uvicorn", "config.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
