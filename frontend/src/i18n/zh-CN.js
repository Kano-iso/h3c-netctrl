// frontend/src/i18n/zh-CN.js
// 中文 locale（默认 + 基础 key）
// 命名规范：<module>.<sub>.<semantic>（如 nav.items.devices.label）
// 后续 task 逐步扩充各模块 key
// 详见: openspec/changes/v26-i18n/specs/frontend-i18n-migration/spec.md 决策 1

export default {
  app: {
    title: 'H3C NetCtrl',
    toggle_locale: '切换语言',
    switch_to: '切换到英文',
    locale_zh: '中',
    locale_en: 'EN',
  },
  nav: {
    dashboard: '总览',
    groups: {
      ops: { label: '运维操作', desc: '直接对设备下发配置' },
      'ops-mgmt': { label: '运营管理', desc: '资产盘点 · 配置存档' },
      debug: { label: '排查诊断', desc: '日志 · 拓扑 · AI 辅助' },
    },
    items: {
      devices:    { label: '设备',     desc: '设备清单 · 连接测试' },
      ops:        { label: '运维终端', desc: '命令派发式执行' },
      interfaces: { label: '接口',     desc: 'Access / Trunk 配置' },
      batch:      { label: '批量操作', desc: '多设备并行执行' },
      cmdb:       { label: 'CMDB',     desc: '资产台账' },
      backup:     { label: '备份回滚', desc: '定时备份 · 一键回滚' },
      logs:       { label: '操作日志', desc: '执行历史 · 错误定位' },
      topology:   { label: '拓扑视图', desc: 'LLDP 邻居可视化' },
      ai:         { label: 'AI 助手', desc: '自然语言排错' },
    },
  },
  footer: {
    intro: '基于 NETCONF 的轻量 H3C 交换机 Web 管控平台。命令派发、接口联动、资产盘点、批量操作，一个界面完成日常网络运维。',
    col_product: '产品',
    col_resource: '资源',
    col_about: '关于',
    link_device_mgmt:      '设备管理',
    link_ops_terminal:     '运维终端',
    link_interface_config: '接口配置',
    link_batch_ops:        '批量操作',
    link_cmdb:             'CMDB 资产',
    link_op_logs:          '操作日志',
    link_backup_rollback:  '备份 / 回滚',
    link_topology:         '拓扑视图',
    link_tech_docs:        '技术文档',
    link_changelog:        'Changelog',
    link_about_project:    '项目简介',
    link_tech_stack:       '技术栈',
    link_dev_convention:   '开发规范',
    link_license:          'MIT License',
    link_contact:          '联系作者',
    aria_github: 'GitHub',
    aria_docs:   '文档',
    aria_email:  '邮件',
    copyright:   '© 2026 H3C NetCtrl · 个人学习项目',
    built_with:  'Built with Vue 3 · FastAPI · NETCONF',
  },
  common: {
    confirm: '确认',
    cancel: '取消',
    future: '未来',
  },
  // v2.6 设备状态显示（utils/status.js 用）
  status: {
    device: {
      online:      '在线',
      warning:     '告警',
      maintenance: '维护',
      offline:     '离线',
      unknown:     '未采集',
    },
    iface: {
      up:                     'UP',
      down:                   'DOWN',
      testing:                '测试中',
      unknown:                '—',
      administratively_down:  '禁用',
    },
  },
  // v2.6 通用错误消息（api/index.js 用）
  errors: {
    network_failed:        '网络请求失败，请检查后端服务是否运行',
    download_failed_http:  '下载失败: HTTP {status}',
    download_failed_network: '下载失败，请检查后端服务是否运行',
  },
}
