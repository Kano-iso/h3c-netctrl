/**
 * 设备信息管理
 */

let currentDevice = null;

/**
 * 加载设备信息
 */
async function loadDevice() {
    const result = await apiCall('/device');
    const container = document.getElementById('device-info');

    if (!result.success) {
        container.innerHTML = `<p class="text-danger">加载失败: ${result.error}</p>`;
        return;
    }

    currentDevice = result.data;

    if (!currentDevice) {
        container.innerHTML = `
            <p class="text-muted">未配置设备</p>
            <button class="btn btn-primary btn-sm" onclick="openDeviceModal()">添加设备</button>
        `;
        return;
    }

    container.innerHTML = `
        <div class="row">
            <div class="col-md-3"><strong>名称:</strong> ${currentDevice.name}</div>
            <div class="col-md-3"><strong>IP:</strong> ${currentDevice.host}</div>
            <div class="col-md-2"><strong>端口:</strong> ${currentDevice.port}</div>
            <div class="col-md-2"><strong>用户名:</strong> ${currentDevice.username}</div>
            <div class="col-md-2">
                <button class="btn btn-outline-secondary btn-sm" onclick="openDeviceModal()">编辑</button>
            </div>
        </div>
    `;
}

/**
 * 打开设备配置弹窗
 */
function openDeviceModal() {
    const modal = new bootstrap.Modal(document.getElementById('deviceModal'));
    const title = document.getElementById('deviceModalTitle');

    if (currentDevice) {
        title.textContent = '编辑设备';
        document.getElementById('device-name').value = currentDevice.name;
        document.getElementById('device-host').value = currentDevice.host;
        document.getElementById('device-port').value = currentDevice.port;
        document.getElementById('device-username').value = currentDevice.username;
        document.getElementById('device-password').value = '';
    } else {
        title.textContent = '添加设备';
        document.getElementById('device-form').reset();
    }

    modal.show();
}

/**
 * 保存设备信息
 */
async function saveDevice() {
    const btn = document.getElementById('btn-save-device');
    setLoading(btn, true);

    const data = {
        name: document.getElementById('device-name').value.trim(),
        host: document.getElementById('device-host').value.trim(),
        port: parseInt(document.getElementById('device-port').value),
        username: document.getElementById('device-username').value.trim(),
        password: document.getElementById('device-password').value,
    };

    if (!data.name || !data.host || !data.username) {
        showError('请填写所有必填字段');
        setLoading(btn, false);
        return;
    }

    const method = currentDevice ? 'PUT' : 'POST';
    const result = await apiCall('/device', {
        method: method,
        body: JSON.stringify(data),
    });

    setLoading(btn, false);

    if (result.success) {
        bootstrap.Modal.getInstance(document.getElementById('deviceModal')).hide();
        loadDevice();
    } else {
        showError(result.error);
    }
}

/**
 * 测试设备连接
 */
async function testConnection() {
    const btn = document.getElementById('btn-test-conn');
    setLoading(btn, true);

    const result = await apiCall('/device/test', { method: 'POST' });

    setLoading(btn, false);

    if (result.success) {
        document.getElementById('device-info').innerHTML += `
            <div class="mt-2 alert alert-success py-1">连接成功</div>
        `;
    } else {
        showError(result.error);
    }
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-save-device').addEventListener('click', saveDevice);
    document.getElementById('btn-test-conn').addEventListener('click', testConnection);
    loadDevice();
});
