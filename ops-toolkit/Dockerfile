FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    netcat-openbsd \
    openssh-client \
    sshpass \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ncclient netmiko paramiko

RUN mkdir -p /scripts /captures

# 预制脚本
COPY scripts/ /scripts/
RUN chmod +x /scripts/*.sh && cp /scripts/*.sh /usr/local/bin/

WORKDIR /scripts

# 默认交互 shell（不自动跑脚本，由用户指定）
CMD ["/bin/bash"]