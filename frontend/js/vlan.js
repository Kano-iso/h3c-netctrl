/**
 * VLAN 管理
 */

let editingVlanId = null;
let deletingVlanId = null;

/**
 * 加载 VLAN 列表
 */
async function loadVlans() {
    const loading = document.getElementById('vlan-loading');
    const tbody = document.getElementById('vlan-tbody');
    const empty = document.getElementById('vlan-empty');
    const table = document.getElementById('vlan-table');

    loading.classList.remove('d-none');
    table.classList.add('d-none');
    empty.classList.add('d-none');

    const result = await apiCall('/vlans');

    loading.classList.add('d-none');

    if (!result.success) {
        showError(result.error);
        return;
    }

    const vlans = result.data || [];

    if (vlans.length === 0) {
        empty.classList.remove('d-none');
        return;
    }

    table.classList.remove('d-none');
    tbody.innerHTML = vlans.map(v => `
        <tr>
            <td>${v.vlan_id}</td>
            <td>${v.name}</td>
            <td>
                <button class="btn btn-outline-primary btn-sm" onclick="openEditVlan(${v.vlan_id}, '${v.name}')">编辑</button>
                <button class="btn btn-outline-danger btn-sm" onclick="confirmDeleteVlan(${v.vlan_id})">删除</button>
            </td>
        </tr>
    `).join('');
}

/**
 * 打开新增 VLAN 弹窗
 */
function openAddVlan() {
    editingVlanId = null;
    document.getElementById('vlanModalTitle').textContent = '新增 VLAN';
    document.getElementById('vlan-id').value = '';
    document.getElementById('vlan-id').disabled = false;
    document.getElementById('vlan-name').value = '';
    new bootstrap.Modal(document.getElementById('vlanModal')).show();
}

/**
 * 打开编辑 VLAN 弹窗
 */
function openEditVlan(vlanId, vlanName) {
    editingVlanId = vlanId;
    document.getElementById('vlanModalTitle').textContent = '编辑 VLAN';
    document.getElementById('vlan-id').value = vlanId;
    document.getElementById('vlan-id').disabled = true;
    document.getElementById('vlan-name').value = vlanName;
    new bootstrap.Modal(document.getElementById('vlanModal')).show();
}

/**
 * 保存 VLAN（新增或编辑）
 */
async function saveVlan() {
    const btn = document.getElementById('btn-save-vlan');
    setLoading(btn, true);

    const vlanId = parseInt(document.getElementById('vlan-id').value);
    const vlanName = document.getElementById('vlan-name').value.trim();

    // 前端校验
    if (isNaN(vlanId) || vlanId < 1 || vlanId > 4094) {
        showError('VLAN ID必须在1-4094范围内');
        setLoading(btn, false);
        return;
    }
    if (!vlanName) {
        showError('VLAN名称不能为空');
        setLoading(btn, false);
        return;
    }

    let result;
    if (editingVlanId !== null) {
        // 编辑模式
        result = await apiCall(`/vlans/${editingVlanId}`, {
            method: 'PUT',
            body: JSON.stringify({ name: vlanName }),
        });
    } else {
        // 新增模式
        result = await apiCall('/vlans', {
            method: 'POST',
            body: JSON.stringify({ vlan_id: vlanId, name: vlanName }),
        });
    }

    setLoading(btn, false);

    if (result.success) {
        bootstrap.Modal.getInstance(document.getElementById('vlanModal')).hide();
        loadVlans();
    } else {
        showError(result.error);
    }
}

/**
 * 确认删除 VLAN
 */
function confirmDeleteVlan(vlanId) {
    deletingVlanId = vlanId;
    document.getElementById('delete-message').textContent = `确认删除VLAN ${vlanId}？`;
    new bootstrap.Modal(document.getElementById('deleteModal')).show();
}

/**
 * 执行删除 VLAN
 */
async function doDeleteVlan() {
    const btn = document.getElementById('btn-confirm-delete');
    setLoading(btn, true);

    const result = await apiCall(`/vlans/${deletingVlanId}`, { method: 'DELETE' });

    setLoading(btn, false);

    if (result.success) {
        bootstrap.Modal.getInstance(document.getElementById('deleteModal')).hide();
        loadVlans();
    } else {
        showError(result.error);
    }
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-add-vlan').addEventListener('click', openAddVlan);
    document.getElementById('btn-save-vlan').addEventListener('click', saveVlan);
    document.getElementById('btn-confirm-delete').addEventListener('click', doDeleteVlan);
    document.getElementById('btn-refresh-vlans').addEventListener('click', loadVlans);
    loadVlans();
});
