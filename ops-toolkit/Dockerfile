FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    netcat-openbsd \
    openssh-client \
    sshpass \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir ncclient netmiko paramiko

RUN mkdir -p /scripts /captures /opt/docs

# 预制脚本
COPY ops-toolkit/scripts/ /scripts/
RUN chmod +x /scripts/*.sh && cp /scripts/*.sh /usr/local/bin/

# v24-toolkit-ux-and-doc-discovery: 工具回显指向 /opt/docs/ 下的文档
COPY docs/ /opt/docs/

WORKDIR /scripts

# 默认交互 shell（不自动跑脚本，由用户指定）
CMD ["/bin/bash"]