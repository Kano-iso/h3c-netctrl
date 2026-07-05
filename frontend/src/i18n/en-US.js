// frontend/src/i18n/en-US.js
// 英文 locale（次要 + 基础 key）
// 后续 task 同步翻译，key 数量与 zh-CN 保持一致（CI 校验）
// 风格指引：
//   - 语义一致（不创造新文案）
//   - 简洁为主（按钮 / 标签用 1-3 词）
//   - 专有名词保留（H3C / NETCONF / VLAN / VPN / IP 等）

export default {
  app: {
    title: 'H3C NetCtrl',
    toggle_locale: 'Switch language',
    switch_to: 'Switch to Chinese',
    locale_zh: '中',
    locale_en: 'EN',
  },
  nav: {
    dashboard: 'Dashboard',
  },
  common: {
    confirm: 'Confirm',
    cancel: 'Cancel',
  },
}
