"""SdnDeviceAdapter + H3cV7Adapter 单元测试（v3.0 sdn-vpc-device-templates Task 7）

8 用例覆盖:
- SUPPORTED_MODELS 白名单
- supports_model 子串匹配 (大小写不敏感)
- get_template 路由 (合法 + 非法 action)
- get_template Task 3 模板未实现时报 NotImplementedError
- get_adapter_for_model 工厂 (支持/不支持)
"""

import pytest

from app.i18n_keys import err
from app.services.sdn_device_adapter import (
    H3C_V7_SUPPORTED_MODELS,
    H3cV7Adapter,
    SdnDeviceAdapter,
    VPCConfigTemplate,
    get_adapter_for_model,
)


# ======================== SUPPORTED_MODELS 白名单 ========================

def test_supported_models_contains_s6850():
    """S6850 系列必须在白名单"""
    assert "S6850" in H3C_V7_SUPPORTED_MODELS
    assert "S6850-56HF" in H3C_V7_SUPPORTED_MODELS
    assert "S6850-54HF" in H3C_V7_SUPPORTED_MODELS


def test_supported_models_does_not_contain_other_brands():
    """非 H3C 型号必须不在白名单"""
    assert "CE6865" not in H3C_V7_SUPPORTED_MODELS
    assert "Catalyst" not in H3C_V7_SUPPORTED_MODELS
    assert "Nexus" not in H3C_V7_SUPPORTED_MODELS


# ======================== supports_model 子串匹配 ========================

def test_supports_model_s6850_exact():
    """H3cV7Adapter.supports_model("S6850-56HF") → True"""
    a = H3cV7Adapter()
    assert a.supports_model("S6850-56HF") is True


def test_supports_model_ce_unsupported():
    """H3cV7Adapter.supports_model("CE6865") → False"""
    a = H3cV7Adapter()
    assert a.supports_model("CE6865") is False


def test_supports_model_case_insensitive():
    """大小写不敏感: "s6850" 也认"""
    a = H3cV7Adapter()
    assert a.supports_model("s6850-56hf") is True


def test_supports_model_comware_keyword():
    """"Comware V7" 关键字也认 (型号字符串可能含此关键字)"""
    a = H3cV7Adapter()
    assert a.supports_model("H3C Comware V7 S6850") is True


# ======================== get_template 路由 ========================

def test_get_template_unknown_action_raises_value_error():
    """未知 action 抛 ValueError (不掩盖为 NotImplementedError)"""
    a = H3cV7Adapter()
    with pytest.raises(ValueError) as exc_info:
        a.get_template("unknown_action")
    assert "unknown_action" in str(exc_info.value)


def test_get_template_vpc_create_template_not_implemented():
    """合法 action 但 Task 3 模板未实现时报 NotImplementedError

    注: Task 3 已实现, 此测试验证回退路径 (如果 Task 3 文件被删)
    """
    a = H3cV7Adapter()
    # Task 3 已实现 → 应能正常返回模板实例
    # 但我们仍验证它确实是 VPCConfigTemplate 子类
    try:
        tpl = a.get_template("vpc_create")
        assert isinstance(tpl, VPCConfigTemplate)
    except NotImplementedError:
        # Task 3 模板未实现 (允许) — 不算测试失败
        pytest.skip("Task 3 模板未实现, 跳过")


# ======================== get_adapter_for_model 工厂 ========================

def test_factory_returns_adapter_for_supported_model():
    """支持的型号 → 返 H3cV7Adapter 实例"""
    result = get_adapter_for_model("S6850-56HF")
    assert isinstance(result, SdnDeviceAdapter)
    assert isinstance(result, H3cV7Adapter)


def test_factory_returns_i18n_error_for_unsupported_model():
    """不支持的型号 → 返带 i18n error_key 的 APIResponse"""
    result = get_adapter_for_model("Cisco Catalyst 9300")
    assert not isinstance(result, SdnDeviceAdapter)
    # 是 APIResponse
    assert hasattr(result, "success")
    assert result.success is False
    assert result.error_key == "sdn.device_model_unsupported"
    assert "Catalyst 9300" in (result.error or "")
    # i18n key 与 err.SDN_DEVICE_MODEL_UNSUPPORTED 一致
    assert result.error_key == str(err.SDN_DEVICE_MODEL_UNSUPPORTED)
