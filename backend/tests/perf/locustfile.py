"""locust 性能压测脚本（v2.4.2）

目标：定位后端 NETCONF / SSH 并发性能瓶颈，验证 v2.4.1 拆 3 容器后连接池无泄漏。

⚠️ 严格约束：只压测 Test-Switch-177 (192.168.100.177)，**绝对不能压生产设备 .4/.5/.100**。
原因：v2.3 教训，qa 工具误连生产导致配置污染。.177 是 test 设备，可反复压。

用户场景：
- NetconfConfigUser: 模拟 100 并发用户，每个调 GET /api/devices/7/interfaces（NETCONF 真链路）
- SshBackupUser: 模拟 50 并发用户，每个调 POST /api/devices/7/backup（SSH 拉配置）

跑法：
  docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend \\
    locust -f tests/perf/locustfile.py --headless -u 100 -r 10 --run-time 60s \\
    --host http://backend:8000

注意：
- 后端必须已起（monolith 或 split 模式均可）
- 默认 backend 容器内 http://backend:8000（DOCKER DNS）
- 本地直跑用 --host http://localhost:8000
"""
import random

from locust import HttpUser, task, between, events


# Test-Switch-177 设备 id（v2.4.1 导入测试机种子数据时固定为 7）
TEST_DEVICE_ID = 7


class NetconfConfigUser(HttpUser):
    """模拟用户并发查询 .177 接口列表（NETCONF 真链路）

    P99 阈值 < 5s（proposal.md § 真机验证）
    """
    wait_time = between(0.5, 2.0)  # 用户间隔 0.5-2s，模拟真实操作节奏

    @task(3)
    def list_interfaces(self):
        """NETCONF 查询接口列表（最常见的只读操作）"""
        with self.client.get(
            f"/api/devices/{TEST_DEVICE_ID}/interfaces",
            name="GET /devices/{id}/interfaces",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    resp.success()
                else:
                    # 后端 success=false（如设备 NETCONF 不可达）
                    resp.failure(f"backend error: {data.get('error', 'unknown')}")
            elif resp.status_code == 502:
                # 设备不可达（v2.4.2 预期：100 并发可能触发设备 NETCONF session 上限）
                resp.failure(f"NETCONF 设备不可达 (502): {resp.text[:200]}")
            else:
                resp.failure(f"unexpected status: {resp.status_code} - {resp.text[:200]}")


class SshBackupUser(HttpUser):
    """模拟用户并发触发 .177 备份（SSH 真链路）

    P99 阈值 < 30s（单次 SCP 拉 + CLI 跑 display current-configuration）
    """
    wait_time = between(2.0, 5.0)  # 备份比接口查询慢，用户操作间隔更大

    @task
    def create_backup(self):
        """触发单设备备份（startup + running 都拉）"""
        with self.client.post(
            f"/api/devices/{TEST_DEVICE_ID}/backup",
            json={"types": ["startup", "running"]},
            name="POST /devices/{id}/backup",
            catch_response=True,
            timeout=60,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    resp.success()
                else:
                    resp.failure(f"backend error: {data.get('error', 'unknown')}")
            else:
                resp.failure(f"unexpected status: {resp.status_code} - {resp.text[:200]}")


# locust 启动 / 停止时打印监控提示
@events.init.add_listener
def on_init(environment, **kwargs):
    print("=" * 60)
    print("  🚀 v2.4.2 locust 压测启动")
    print(f"  📌 目标设备: Test-Switch-177 (192.168.100.177, id={TEST_DEVICE_ID})")
    print(f"  🌐 目标 host: {environment.host}")
    print("  📊 监控命令: watch -n 1 'ss -tan | grep 192.168.100.177 | wc -l'")
    print("=" * 60)


@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    stats = environment.stats
    print("=" * 60)
    print("  📊 压测汇总:")
    print(f"  - 接口查询 P99: {stats.get('GET /devices/{id}/interfaces', 'GET /devices/7/interfaces').get_response_time_percentile(0.99):.0f}ms")
    print(f"  - 备份 P99: {stats.get('POST /devices/{id}/backup', 'POST /devices/7/backup').get_response_time_percentile(0.99):.0f}ms")
    print(f"  - 失败请求: {stats.num_failures}")
    print("=" * 60)
