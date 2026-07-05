// v2.5 vitest 框架 smoke test
// 验证：happy-dom 环境 + @vue/test-utils mount + Select 组件渲染
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import Select from '../components/Select.vue'

describe('vitest smoke test', () => {
  it('happy-dom 环境可用（document 定义存在）', () => {
    expect(document).toBeDefined()
    expect(document.createElement).toBeDefined()
  })

  it('Select 组件 mount 成功，渲染 placeholder', () => {
    const wrapper = mount(Select, {
      props: {
        options: [
          { id: 1, name: '设备A' },
          { id: 2, name: '设备B' },
        ],
        modelValue: null,
        placeholder: '请选择设备',
      },
    })
    expect(wrapper.text()).toContain('请选择设备')
  })

  it('Select 组件点击触发器后下拉菜单展开', async () => {
    const wrapper = mount(Select, {
      props: {
        options: [
          { id: 1, name: '设备A' },
          { id: 2, name: '设备B' },
        ],
        modelValue: null,
      },
    })
    // 初始菜单不展开
    expect(wrapper.findAll('button').length).toBe(1) // 只有触发器按钮

    // 点击触发器
    await wrapper.find('button').trigger('click')
    expect(wrapper.findAll('button').length).toBe(3) // 触发器 + 2 个选项
    expect(wrapper.text()).toContain('设备A')
    expect(wrapper.text()).toContain('设备B')
  })
})
