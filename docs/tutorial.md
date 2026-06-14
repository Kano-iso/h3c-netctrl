# H3C NetCtrl v1.0 技术教学文档

> 用易懂的方式解释项目中的关键技术链条，帮助你理解"从点按钮到设备执行"的完整过程

---

## 1. NETCONF 配置下发：从按钮到交换机

### 1.1 整体链条

当你点击前端"创建 VLAN"按钮时，数据经历了这样的旅程：

```
用户点击按钮
    ↓
前端 JS 构造 HTTP 请求 (POST /api/vlans)
    ↓
Nginx 反向代理转发到后端 (localhost:8000)
    ↓
FastAPI 路由接收请求，校验参数
    ↓
从数据库读取设备信息，解密密码
    ↓
构造 H3C 专用的 NETCONF XML 报文
    ↓
通过 ncclient 库建立 SSH 连接，发送 XML
    ↓
H3C 交换机解析 XML，执行配置变更
    ↓
交换机返回 XML 响应
    ↓
后端解析响应，返回 JSON 给前端
    ↓
前端刷新 VLAN 表格
```

### 1.2 关键环节详解

#### 环节 1：前端发请求

前端用 `fetch` 发一个 POST 请求，body 里带着 VLAN ID 和名称：

```javascript
// frontend/js/vlan.js
async function saveVlan() {
    const vlanId = parseInt(document.getElementById('vlan-id').value);
    const vlanName = document.getElementById('vlan-name').value.trim();

    result = await apiCall('/vlans', {
        method: 'POST',
        body: JSON.stringify({ vlan_id: vlanId, name: vlanName }),
    });
}
```

`apiCall` 是封装好的函数，统一处理 URL 拼接、错误展示、loading 状态。

#### 环节 2：后端接收并校验

FastAPI 用 Pydantic 模型自动校验请求参数：

```python
# backend/app/schemas.py
class VLANCreate(BaseModel):
    vlan_id: int = Field(ge=1, le=4094)  # 自动校验范围
    name: str
```

如果 vlan_id 不在 1-4094 范围内，FastAPI 直接返回 422 错误，不需要手写校验代码。

#### 环节 3：构造 NETCONF XML

这是最关键的环节。H3C 交换机不认识 JSON，它只认 NETCONF XML。

创建 VLAN 100 的 XML 长这样：

```xml
<config>
    <top xmlns="http://www.h3c.com/netconf/config:1.0">
        <VLAN>
            <VLANs>
                <VLANID>
                    <ID>100</ID>
                </VLANID>
            </VLANs>
        </VLAN>
    </top>
</config>
```

**为什么长这样？** 这是 H3C 厂商私有定义的 XML 结构，不是标准 YANG 模型。我们通过实际连接设备探测出来的。

对应的构造代码：

```python
# backend/app/routers/vlan.py
H3C_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"

def _build_vlan_create_xml(vlan_id: int, name: str) -> str:
    return f"""
    <config>
        <top xmlns="{H3C_CONFIG_NS}">
            <VLAN>
                <VLANs>
                    <VLANID>
                        <ID>{vlan_id}</ID>
                    </VLANID>
                </VLANs>
            </VLAN>
        </top>
    </config>
    """
```

删除 VLAN 时，在 VLANID 标签上加 `xc:operation="delete"` 属性：

```xml
<VLANID xc:operation="delete">
    <ID>100</ID>
</VLANID>
```

#### 环节 4：通过 ncclient 下发

ncclient 是 Python 的 NETCONF 客户端库，它在底层做的事情是：

1. 通过 paramiko 建立 SSH 连接到交换机的 830 端口
2. 双方交换 NETCONF 能力声明（hello 握手）
3. 发送 edit-config RPC（就是上面构造的 XML）
4. 接收交换机的响应

```python
# backend/app/netconf_client.py
class NetconfClient:
    def __enter__(self):
        self._manager = manager.connect(
            host=self.host,        # 192.168.100.100
            port=self.port,        # 830
            username=self.username,
            password=self.password,
            device_params={"name": "h3c"},  # 告诉 ncclient 这是 H3C 设备
            hostkey_verify=False,  # 不验证主机密钥（开发环境）
        )
        return self

    def edit_config(self, config_xml: str) -> str:
        result = self._manager.edit_config(
            target="running",      # 直接修改运行配置
            config=config_xml      # 上面构造的 XML
        )
        return result.xml
```

`with NetconfClient(...) as client:` 这种写法叫 **上下文管理器**，退出 with 块时自动关闭连接，不会泄漏。

#### 环节 5：错误分类

连接交换机可能遇到各种问题，我们把它们翻译成中文：

```python
# backend/app/netconf_client.py
def classify_connection_error(error: Exception) -> str:
    if isinstance(error, socket.gaierror):
        return "设备不可达，请检查IP地址"
    if "Connection refused" in str(error):
        return "连接被拒绝，请检查NETCONF服务是否开启（端口830）"
    if isinstance(error, AuthenticationError):
        return "认证失败，请检查用户名或密码"
    ...
```

这样前端展示的错误信息是"认证失败，请检查用户名或密码"，而不是 `AuthenticationError: Invalid credentials`。

---

## 2. 密码加密存储

### 2.1 为什么不能明文存密码？

如果数据库被泄露，明文密码直接暴露。加密后，即使拿到数据库也无法还原密码。

### 2.2 Fernet 加密流程

```
明文密码 "Admin123!@#"
    ↓
Fernet.encrypt(明文.encode())  ← 用 ENCRYPTION_KEY 加密
    ↓
密文 "gAAAAABm..." (存在数据库 password_encrypted 字段)
    ↓
使用时：Fernet.decrypt(密文.encode())  ← 用同一个 KEY 解密
    ↓
明文密码 "Admin123!@#" (只在内存中，用于连接设备)
```

代码只有几行：

```python
# backend/app/utils/crypto.py
from cryptography.fernet import Fernet

def encrypt_password(plaintext: str) -> str:
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.encrypt(plaintext.encode()).decode()

def decrypt_password(encrypted: str) -> str:
    f = Fernet(settings.ENCRYPTION_KEY.encode())
    return f.decrypt(encrypted.encode()).decode()
```

**关键点**：`ENCRYPTION_KEY` 存在 `.env` 文件中，`.env` 被 `.gitignore` 排除，不会提交到 Git。

---

## 3. 数据库读写

### 3.1 SQLAlchemy ORM 的作用

ORM（对象关系映射）让你用 Python 类操作数据库，不用写 SQL：

```python
# 写入
device = Device(name="Spine-01", host="192.168.100.100")
db.add(device)
db.commit()

# 查询
device = db.query(Device).first()

# 更新
device.name = "Spine-01-Updated"
db.commit()
```

### 3.2 数据库文件在哪？

SQLite 的数据库就是一个文件：`data/dev.db`（8KB）。

这个文件通过 Docker volume 挂载到宿主机，容器重启不会丢失：

```yaml
# docker-compose.dev.yml
volumes:
  - ./data:/app/data   # 宿主机 ./data → 容器 /app/data
```

### 3.3 表结构自动创建

FastAPI 启动时执行：

```python
# backend/app/main.py
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
```

这行代码检查所有 ORM 模型，如果对应的表不存在就自动创建。不需要手动建表。

---

## 4. 前后端联动

### 4.1 Nginx 反向代理

前端页面由 Nginx 提供（端口 80），API 请求由 Nginx 转发到后端（端口 8000）：

```
浏览器 → http://localhost:80/
         ├── /           → Nginx 返回 index.html
         ├── /js/*.js    → Nginx 返回 JS 文件
         └── /api/*      → Nginx 转发到 http://backend:8000/api/*
```

配置只有几行：

```nginx
# frontend/nginx.conf
location /api/ {
    proxy_pass http://backend:8000/api/;
}
```

这样前端 JS 调用 `/api/vlans` 时，实际请求到了后端容器。

### 4.2 统一响应格式

所有 API 返回相同结构：

```json
{
    "success": true,
    "data": [...],
    "error": null
}
```

或错误时：

```json
{
    "success": false,
    "data": null,
    "error": "VLAN 100已存在"
}
```

前端统一处理：

```javascript
const result = await apiCall('/vlans');
if (!result.success) {
    showError(result.error);  // 显示红色错误提示
    return;
}
// 使用 result.data
```

---

## 5. 日志系统

### 5.1 双输出

日志同时输出到两个地方：
- **stdout**：`docker compose logs backend` 可查看
- **文件**：`logs/app.log`，挂载到宿主机可查看

### 5.2 日志级别

| 级别 | 用途 | 示例 |
|---|---|---|
| INFO | 操作记录 | "VLAN创建成功: vlan_id=100" |
| DEBUG | 调试信息 | NETCONF 请求/响应 XML（密码脱敏） |
| ERROR | 异常记录 | "VLAN查询失败: 设备连接超时" + 完整堆栈 |

### 5.3 密码脱敏

DEBUG 日志中密码显示为 `***********`：

```python
debug_password = re.sub(r'.', '*', self.password)
logger.debug(f"连接参数: password={debug_password}")
```

---

## 6. 容器化开发

### 6.1 为什么用容器？

- 宿主机不装 Python、pip、nginx 等依赖
- 团队成员环境一致，不会出现"我这里能跑"
- 一条命令 `make dev` 启动完整环境

### 6.2 挂载策略

```
宿主机                    容器内
./backend/          →    /app/          (代码，热重载)
./data/             →    /app/data/     (数据库，持久化)
./frontend/         →    /usr/share/nginx/html/  (静态文件)
./frontend/nginx.conf → /etc/nginx/conf.d/default.conf
```

**代码挂载的意义**：改了 Python 文件，uvicorn 自动重启，不需要重新构建镜像。

**不挂载的东西**：pip 安装的依赖包（在镜像内），没有镜像就无法运行。

### 6.3 常用命令

```bash
make dev           # 启动开发环境
make dev-rebuild   # 重新构建镜像（改了 requirements.txt 后需要）
make stop          # 停止
make logs          # 查看日志
make backup        # 备份数据库
```

---

## 7. NETCONF 查询 VLAN 的完整示例

以"查询 VLAN 列表"为例，展示完整的数据流：

### 步骤 1：前端发请求

```javascript
const result = await apiCall('/vlans');  // GET /api/vlans
```

### 步骤 2：后端构造查询 XML

```python
filter_xml = '<top xmlns="http://www.h3c.com/netconf/config:1.0"><VLAN></VLAN></top>'
```

### 步骤 3：ncclient 发送 get-config RPC

底层发送的 NETCONF 报文（简化）：

```xml
<rpc message-id="1" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
    <get-config>
        <source><running/></source>
        <filter type="subtree">
            <top xmlns="http://www.h3c.com/netconf/config:1.0">
                <VLAN></VLAN>
            </top>
        </filter>
    </get-config>
</rpc>
```

### 步骤 4：H3C 交换机返回响应

```xml
<rpc-reply message-id="1">
    <data>
        <top xmlns="http://www.h3c.com/netconf/config:1.0">
            <VLANs>
                <VLANID><ID>1</ID></VLANID>
                <VLANID><ID>100</ID><AccessPortList>2-21</AccessPortList></VLANID>
            </VLANs>
        </top>
    </data>
</rpc-reply>
```

### 步骤 5：后端解析 XML

```python
root = ET.fromstring(xml_str)
for elem in root.iter():
    if tag == "VLANID":
        for child in elem:
            if child_tag == "ID":
                vlan_id = int(child.text)  # 提取 1, 100
```

### 步骤 6：返回 JSON 给前端

```json
{
    "success": true,
    "data": [
        {"vlan_id": 1, "name": "VLAN 1"},
        {"vlan_id": 100, "name": "VLAN 100"}
    ]
}
```

### 步骤 7：前端渲染表格

```javascript
tbody.innerHTML = vlans.map(v => `
    <tr>
        <td>${v.vlan_id}</td>
        <td>${v.name}</td>
        <td>编辑 | 删除</td>
    </tr>
`).join('');
```

这就是从按钮到设备再回到屏幕的完整旅程。
