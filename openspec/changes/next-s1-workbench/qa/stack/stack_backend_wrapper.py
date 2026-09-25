"""S1-027 stack 后端包装器：注入设备边界 fake 后启动【真实 FastAPI】应用（uvicorn）。

本文件只由 run_stack_qa.sh 作为 uvicorn 入口执行；生产 entrypoint（Dockerfile /
entrypoint 脚本）从不加载它。它只替换运行进程内三个路由模块的类属性
（interface.NetconfClient / sdn_access.SdnDeploymentExecutor / sdn_access.
SdnValidationCollector），不触碰生产源码、不暴露任何测试后门路由。
"""

import os
import sys

STACK_QA_DIR = os.environ.setdefault("STACK_QA_DIR", "/tmp/stack-qa")
os.makedirs(STACK_QA_DIR, exist_ok=True)
os.environ.setdefault("DB_PATH", os.path.join(STACK_QA_DIR, "db.sqlite"))
PORT = int(os.environ.get("STACK_QA_BACKEND_PORT", "18000"))

# 在 import app 之前把边界 fake 放进模块属性（生产入口不加载本模块，零污染）
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
from stack_fakes import FakeExecutor, FakeNetconfClient, FakeValidationCollector  # noqa: E402

import app.routers.interface as interface_mod  # noqa: E402
import app.routers.sdn_access as sdn_access_mod  # noqa: E402
import app.routers.sdn as sdn_mod  # noqa: E402

# S2 系列把执行器/收集器从 sdn_access 抽到 services，且 validation/sync 路由位于
# sdn.py——每个 import 该名字的模块都要按「调用点模块全局名」替换，否则该路径会走
# 真实收集器（network_mode:none 下产生 Network unreachable 脏快照）。
interface_mod.NetconfClient = FakeNetconfClient
sdn_access_mod.SdnDeploymentExecutor = FakeExecutor
sdn_access_mod.SdnValidationCollector = FakeValidationCollector
sdn_mod.SdnDeploymentExecutor = FakeExecutor
sdn_mod.SdnValidationCollector = FakeValidationCollector

from app.main import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
