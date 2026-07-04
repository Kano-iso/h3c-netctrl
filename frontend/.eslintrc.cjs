/**
 * 前端 ESLint 配置（v242-qa-and-tooling Change 1）
 *
 * 规则集：eslint-plugin-vue 的 essential（v9.x）
 * 风格：personal project 风格 — 简洁、抓明显 bug、不过严
 *
 * 覆盖：
 * - Vue 3 SFC 语法（template / script / style）
 * - JS 基础（变量、函数、prop）
 * - 不覆盖：style（prettier 范畴）、i18n 字符串
 */
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true,
  },
  extends: [
    // Vue 3 官方推荐（essential = 必须遵守的最小规则集）
    'plugin:vue/vue3-essential',
  ],
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
  },
  rules: {
    // === Vue 3 essential 默认开启的规则 + 关键抓 bug 的 ===

    // v-for 必须有 key（防 Vue 警告 + 性能）
    'vue/no-v-for-template-key': 'error',
    'vue/require-v-for-key': 'error',

    // prop 类型必须明确（防 prop 名拼错）
    'vue/require-default-prop': 'off', // 个人项目不强制 default
    'vue/prop-name-casing': 'error',

    // 组件名必须 PascalCase
    'vue/component-name-in-template-casing': ['error', 'PascalCase'],

    // 抓明显 bug：未使用 import / 变量（v242-qa-and-tooling 加）
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],

    // 关闭过严的规则（个人项目够用即可）
    'vue/multi-word-component-names': 'off', // 单字组件名允许
    'vue/html-self-closing': 'off',         // 风格不管
    'vue/max-attributes-per-line': 'off',   // 风格不管
    'vue/singleline-html-element-content-newline': 'off',
    'vue/html-indent': 'off',
    'vue/attributes-order': 'off',
    'vue/first-attribute-linebreak': 'off',
    'vue/html-closing-bracket-newline': 'off',
  },
};
