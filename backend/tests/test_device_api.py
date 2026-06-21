"""设备管理 API 测试"""


def test_create_device(client):
    """测试创建设备"""
    resp = client.post("/api/devices", json={
        "name": "SW-Test",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "Admin123!"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["name"] == "SW-Test"
    assert data["data"]["host"] == "192.168.1.1"


def test_list_devices(client):
    """测试获取设备列表"""
    # 先创建一个设备
    client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "Admin123!"
    })
    resp = client.get("/api/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1


def test_get_device(client):
    """测试获取单个设备"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "Admin123!"
    })
    device_id = create_resp.json()["data"]["id"]
    resp = client.get(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "SW-1"


def test_update_device(client):
    """测试更新设备"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "Admin123!"
    })
    device_id = create_resp.json()["data"]["id"]
    resp = client.put(f"/api/devices/{device_id}", json={"name": "SW-Updated"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "SW-Updated"


def test_delete_device(client):
    """测试删除设备"""
    create_resp = client.post("/api/devices", json={
        "name": "SW-1",
        "host": "192.168.1.1",
        "port": 830,
        "username": "admin",
        "password": "Admin123!"
    })
    device_id = create_resp.json()["data"]["id"]
    resp = client.delete(f"/api/devices/{device_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
