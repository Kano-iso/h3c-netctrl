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

# v242-paramiko-tool: 复用 backend SSHExecutor（不手搓 paramiko 代码）
# ssh_executor.py 只依赖 logging/re/time/paramiko，容器内都已具备
# 单独 COPY 一个文件，比挂 backend/ 整个目录干净（避免依赖 backend 其他模块）
COPY backend/app/utils/ssh_executor.py /opt/ssh_executor.py

# 预制脚本
COPY ops-toolkit/scripts/ /scripts/
RUN chmod +x /scripts/*.sh && cp /scripts/*.sh /usr/local/bin/

# v24-toolkit-ux-and-doc-discovery: 工具回显指向 /opt/docs/ 下的文档
COPY docs/ /opt/docs/

WORKDIR /scripts

# 默认交互 shell（不自动跑脚本，由用户指定）
CMD ["/bin/bash"]