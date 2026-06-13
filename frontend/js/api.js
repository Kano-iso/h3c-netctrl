/**
 * 统一 API 调用函数
 * 封装 fetch 请求，统一处理错误和 loading 状态
 */

const API_BASE = '/api';

/**
 * 调用后端 API
 * @param {string} path - API 路径（如 /device）
 * @param {object} options - fetch 选项
 * @returns {Promise<object>} API 响应数据
 */
async function apiCall(path, options = {}) {
    const url = API_BASE + path;
    const config = {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    };

    try {
        const response = await fetch(url, config);
        const data = await response.json();
        return data;
    } catch (error) {
        return { success: false, error: '网络请求失败，请检查服务是否运行' };
    }
}

// --- 错误展示 ---

let errorTimer = null;

/**
 * 显示全局错误信息
 * @param {string} message - 错误消息
 */
function showError(message) {
    const area = document.getElementById('error-area');
    area.innerHTML = `
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    // 5秒后自动消失
    if (errorTimer) clearTimeout(errorTimer);
    errorTimer = setTimeout(() => {
        area.innerHTML = '';
    }, 5000);
}

/**
 * 清除错误信息
 */
function clearError() {
    document.getElementById('error-area').innerHTML = '';
}

// --- Loading 状态 ---

/**
 * 设置按钮 loading 状态
 * @param {HTMLElement} btn - 按钮元素
 * @param {boolean} loading - 是否 loading
 */
function setLoading(btn, loading) {
    if (loading) {
        btn.disabled = true;
        btn._originalText = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> 处理中...';
    } else {
        btn.disabled = false;
        if (btn._originalText) {
            btn.innerHTML = btn._originalText;
        }
    }
}
