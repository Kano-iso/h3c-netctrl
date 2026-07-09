"""v3.0 SDN 设备型号适配层

## 背景

v3.0 SDN 仅支持 H3C Comware V7 系列交换机（型号 S6850 / S6850-56HF 等）。
其他型号（H3C V5 / Cisco NXOS / Huawei CE）在 v3.0 P0 暂不支持。

## 职责

`SdnDeviceAdapter` 抽象基类只做两件事：
1. 型号识别（`supports_model`）：决定一个 device.asset.model 是否能用本适配器
2. 模板路由（`get_template`）：根据动作（vpc_create / vpc_delete / port_bind / port_unbind）返回对应模板

实际命令拼装由 Task 3 的 `H3cV7VpcCreateTemplate` / `H3cV7VpcDeleteTemplate` /
`H3cV7PortBindTemplate` / `H3cV7PortUnbindTemplate` 完成。

## 未来扩展

- v3.0.1+ 增加 H3cV5Adapter / CiscoAdapter / HuaweiAdapter
- 每个 adapter 独立 class，零侵入
"""

from abc import ABC, abstractmethod
from typing import List

from app.i18n_keys import err, error_response
from app.schemas import APIResponse


# v3.0 P0 唯一支持的设备型号（基于现有设备清单）
# ADR-101: 硬编码白名单, 不连数据库查
H3C_V7_SUPPORTED_MODELS: List[str] = [
    "S6850",
    "S6850-56HF",
    "S6850-54HF",
]


class VPCConfigTemplate(ABC):
    """VPC 配置命令模板抽象基类

    子类: H3cV7VpcCreateTemplate / H3cV7VpcDeleteTemplate
           H3cV7PortBindTemplate / H3cV7PortUnbindTemplate
    (Task 3 实现)
    """

    @abstractmethod
    def render(self, context: dict) -> List[dict]:
        """渲染模板, 返回 List[{mode, command}]

        Args:
            context: 模板变量字典（vpc / tenant / port_binding / device）
        Returns:
            List[ConfigCommand], 每项 {mode: "configure", command: "vsi vpca"}
        """
        raise NotImplementedError


class SdnDeviceAdapter(ABC):
    """SDN 设备型号适配层抽象基类

    v3.0 唯一实现: H3cV7Adapter
    """

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """本适配器支持的设备型号关键字列表"""
        raise NotImplementedError

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """判断 device.asset.model 是否能用本适配器

        匹配规则: 大小写不敏感, 子串匹配（任一关键字出现在 model 中）
        """
        raise NotImplementedError

    @abstractmethod
    def get_template(self, action: str) -> VPCConfigTemplate:
        """根据动作返回对应模板

        Args:
            action: vpc_create | vpc_delete | port_bind | port_unbind
        """
        raise NotImplementedError


class H3cV7Adapter(SdnDeviceAdapter):
    """H3C Comware V7 适配器（型号 S6850 等）

    ADR-101: 型号白名单硬编码
    ADR-102: 第 1 轮省略 import-rt / export-rt
    """

    @property
    def supported_models(self) -> List[str]:
        return list(H3C_V7_SUPPORTED_MODELS)

    def supports_model(self, model: str) -> bool:
        """大小写不敏感, 任一关键字出现在 model 中即可"""
        if not model:
            return False
        model_upper = model.upper()
        return any(kw.upper() in model_upper for kw in self.supported_models)

    def get_template(self, action: str) -> VPCConfigTemplate:
        """路由到对应模板 (Task 3 实现具体命令拼装)

        Task 2 阶段: 仅注册路由表, 模板类在 Task 3 引入
        """
        # 先检查 action 合法性 (避免被 Task 3 模板未实现掩盖)
        valid_actions = ("vpc_create", "vpc_delete", "port_bind", "port_unbind")
        if action not in valid_actions:
            raise ValueError(f"Unknown action: {action}, expected one of {list(valid_actions)}")

        # 延迟 import, 避免循环引用 & Task 3 模板未实现时报清晰错误
        try:
            from app.services.templates.h3c_v7_vpc_create import (
                H3cV7VpcCreateTemplate,
                H3cV7VpcDeleteTemplate,
            )
            from app.services.templates.h3c_v7_port_bind import (
                H3cV7PortBindTemplate,
                H3cV7PortUnbindTemplate,
            )
        except ImportError as e:
            raise NotImplementedError(
                f"H3C V7 模板未实现 (Task 3 待补): {e}. "
                f"action={action} 需要先实现对应的 Template 类"
            ) from e

        mapping = {
            "vpc_create": H3cV7VpcCreateTemplate,
            "vpc_delete": H3cV7VpcDeleteTemplate,
            "port_bind": H3cV7PortBindTemplate,
            "port_unbind": H3cV7PortUnbindTemplate,
        }
        return mapping[action]()


def get_adapter_for_model(model: str) -> SdnDeviceAdapter:
    """工厂函数: 根据 device model 返回对应 adapter

    型号不支持时返回带 i18n 错误信息的 APIResponse-like dict
    (调用方判断 isinstance 决定如何处理)

    v3.0: 仅支持 H3C V7, 其他型号明确报错
    """
    adapter = H3cV7Adapter()
    if adapter.supports_model(model):
        return adapter
    # 型号不支持 → 返 i18n 错误 (调用方用 error_response() 包装)
    return error_response(
        err.SDN_DEVICE_MODEL_UNSUPPORTED,
        params={"model": model or "<empty>", "supported": ", ".join(H3C_V7_SUPPORTED_MODELS)},
    )
