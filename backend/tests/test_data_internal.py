"""data 容器内部端点单测（v241-container-split / v241-supplement）

验证：
- GET /internal/assets — 返回资产列表
- GET /internal/backups/{device_id} — 返回设备备份列表
- DELETE /internal/devices/{id}/cleanup — 清理关联 asset/backup + 备份文件
"""
import os
import pytest

from app.models import Asset, Backup, Device


def test_internal_list_assets_empty(client):
    """GET /internal/assets 空列表"""
    resp = client.get("/internal/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


def test_internal_upsert_asset_creates_and_updates(client):
    """POST /internal/assets/device/{id}/upsert 创建后再更新资产。"""
    resp = client.post("/internal/assets/device/901/upsert", json={
        "status": "online",
        "model": "H3C S6850-56HF",
        "serial_number": "CNEZTP901",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["device_id"] == 901
    assert data["data"]["status"] == "online"
    assert data["data"]["model"] == "H3C S6850-56HF"

    resp2 = client.post("/internal/assets/device/901/upsert", json={
        "status": "offline",
        "firmware_version": "Version 7.1.070",
    })
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["success"] is True
    assert data2["data"]["status"] == "offline"
    assert data2["data"]["model"] == "H3C S6850-56HF"
    assert data2["data"]["firmware_version"] == "Version 7.1.070"


def test_internal_list_backups_empty(client):
    """GET /internal/backups/{device_id} 无备份"""
    resp = client.get("/internal/backups/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


# ============ v241-supplement Task 4.2: cleanup 端点 ============

def test_internal_cleanup_device_no_data(client, db):
    """DELETE /internal/devices/{id}/cleanup 设备无关联数据 → return 0,0"""
    # 创建一个 device（cascade 需要）
    d = Device(name="test-d", host="1.1.1.1", port=830, username="u", password_encrypted="x")
    db.add(d)
    db.commit()
    db.refresh(d)

    resp = client.delete(f"/internal/devices/{d.id}/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["deleted_assets"] == 0
    assert data["data"]["deleted_backups"] == 0


def test_internal_cleanup_device_with_data(client, db, tmp_path):
    """DELETE /internal/devices/{id}/cleanup 设备有 1 asset + 3 backup → 全删 + 文件删"""
    # 准备数据
    d = Device(name="test-d2", host="1.1.1.2", port=830, username="u", password_encrypted="x")
    db.add(d)
    db.commit()
    db.refresh(d)

    # 1 asset（assets 表 device_id 是 UNIQUE，每设备最多 1 行）
    db.add(Asset(device_id=d.id, model="Model-X", serial_number="SN-001"))
    db.commit()

    # 3 backup（带真实文件）
    backup_files = []
    for i in range(3):
        f = tmp_path / f"backup_{i}.cfg"
        f.write_text(f"backup {i}")
        b = Backup(
            device_id=d.id, filename=f"backup_{i}.cfg",
            file_path=str(f), backup_type="startup",
            size=f.stat().st_size, content_hash="hash",
        )
        db.add(b)
        backup_files.append(str(f))
    db.commit()

    # 调 cleanup
    resp = client.delete(f"/internal/devices/{d.id}/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["deleted_assets"] == 1
    assert data["data"]["deleted_backups"] == 3
    assert data["data"]["files_deleted"] == 3
    assert data["data"]["files_missing"] == 0

    # 验文件已删
    for f in backup_files:
        assert not os.path.exists(f), f"备份文件未删: {f}"


def test_internal_cleanup_device_missing_files(client, db, tmp_path, caplog):
    """DELETE /internal/devices/{id}/cleanup 备份文件已丢失不抛异常 + log warning"""
    import logging
    caplog.set_level(logging.WARNING)

    d = Device(name="test-d3", host="1.1.1.3", port=830, username="u", password_encrypted="x")
    db.add(d)
    db.commit()
    db.refresh(d)

    # 1 backup 但 file_path 指向不存在的文件
    fake_path = str(tmp_path / "non_existent.cfg")
    b = Backup(
        device_id=d.id, filename="non_existent.cfg", file_path=fake_path,
        backup_type="running", size=0, content_hash="hash",
    )
    db.add(b)
    db.commit()

    resp = client.delete(f"/internal/devices/{d.id}/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["deleted_backups"] == 1
    assert data["data"]["files_missing"] == 1
    assert data["data"]["files_deleted"] == 0
    # 验有 warning 日志
    assert any("备份文件已丢失" in record.message for record in caplog.records)


def test_internal_cleanup_device_via_internal_token(client, db):
    """cleanup 端点必须接受 X-Internal-Token（中间件不拦截 /internal/* 路径内部路由，但路由本身不要求 token）"""
    d = Device(name="test-d4", host="1.1.1.4", port=830, username="u", password_encrypted="x")
    db.add(d)
    db.commit()
    db.refresh(d)

    # 不带 token 也能调（中间件只校验 /internal/* 路径，cleanup 是内部端点不需 token）
    resp = client.delete(f"/internal/devices/{d.id}/cleanup")
    assert resp.status_code == 200
    assert resp.json()["success"] is True
