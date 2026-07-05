// frontend/src/i18n/en-US.js
// 英文 locale（次要 + 基础 key）
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
    groups: {
      ops: { label: 'Operations', desc: 'Direct device configuration' },
      'ops-mgmt': { label: 'Management', desc: 'Asset tracking · Config archive' },
      debug: { label: 'Troubleshooting', desc: 'Logs · Topology · AI assistance' },
    },
    items: {
      devices:    { label: 'Devices',         desc: 'Device list · Connectivity test' },
      ops:        { label: 'Ops Terminal',    desc: 'Command dispatch execution' },
      interfaces: { label: 'Interfaces',      desc: 'Access / Trunk configuration' },
      batch:      { label: 'Batch',           desc: 'Multi-device parallel execution' },
      cmdb:       { label: 'CMDB',            desc: 'Asset inventory' },
      backup:     { label: 'Backup',          desc: 'Scheduled backup · One-click rollback' },
      logs:       { label: 'Logs',            desc: 'Execution history · Error tracking' },
      topology:   { label: 'Topology',        desc: 'LLDP neighbor visualization' },
      ai:         { label: 'AI Assistant',    desc: 'Natural language troubleshooting' },
    },
  },
  footer: {
    intro: 'A lightweight H3C switch web management platform based on NETCONF. Command dispatch, interface coordination, asset tracking, batch operations — all in one interface for daily network operations.',
    col_product: 'Product',
    col_resource: 'Resources',
    col_about: 'About',
    link_device_mgmt:      'Device Management',
    link_ops_terminal:     'Ops Terminal',
    link_interface_config: 'Interface Config',
    link_batch_ops:        'Batch Operations',
    link_cmdb:             'CMDB Assets',
    link_op_logs:          'Operation Logs',
    link_backup_rollback:  'Backup / Rollback',
    link_topology:         'Topology',
    link_tech_docs:        'Tech Docs',
    link_changelog:        'Changelog',
    link_about_project:    'About Project',
    link_tech_stack:       'Tech Stack',
    link_dev_convention:   'Dev Convention',
    link_license:          'MIT License',
    link_contact:          'Contact Author',
    aria_github: 'GitHub',
    aria_docs:   'Docs',
    aria_email:  'Email',
    copyright:   '© 2026 H3C NetCtrl · Personal learning project',
    built_with:  'Built with Vue 3 · FastAPI · NETCONF',
  },
  common: {
    confirm: 'Confirm',
    cancel: 'Cancel',
    future: 'Future',
  },
}
