/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"PingFang SC"',           // macOS / iOS 现代
          '"Hiragino Sans GB"',      // macOS fallback
          '"Microsoft YaHei"',       // Windows
          '"Noto Sans CJK SC"',      // Linux 思源黑体
          '"Source Han Sans SC"',    // Linux 思源黑体 alias
          '-apple-system', 'BlinkMacSystemFont', '"SF Pro Display"',
          '"Helvetica Neue"', 'system-ui', 'sans-serif'
        ],
        display: [
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Noto Sans CJK SC"',
          '-apple-system', 'BlinkMacSystemFont', '"SF Pro Display"',
          'system-ui', 'sans-serif'
        ],
        mono: ['"SF Mono"', '"JetBrains Mono"', 'ui-monospace', 'monospace']
      },
      colors: {
        // 米白/灰系 (Apple style)
        canvas: {
          DEFAULT: '#fbfbfd',  // 主背景
          50: '#ffffff',
          100: '#fbfbfd',
          200: '#f5f5f7',     // 卡片背景
          300: '#ececef',     // hover/分割
          400: '#d2d2d7'      // 边框
        },
        ink: {
          950: '#0a0a0c',
          900: '#1d1d1f',     // 主文字
          800: '#2c2c2e',
          700: '#424245',     // 二级文字
          600: '#6e6e73',     // 三级文字
          500: '#86868b',     // 提示
          400: '#a1a1a6',
          300: '#d2d2d7'
        },
        // Apple blue 替换紫色作为主色
        accent: {
          DEFAULT: '#0071e3',
          50: '#eef7ff',
          100: '#d8edff',
          200: '#b8ddff',
          300: '#8ec6ff',
          400: '#5eacff',
          500: '#0071e3',     // Apple Blue
          600: '#0058b0',
          700: '#004787',
          800: '#00396e',
          900: '#002b54'
        },
        good: '#30a46c',
        warn: '#f5a524',
        bad:  '#e5484d',
        info: '#3b82f6'
      },
      boxShadow: {
        // Apple 风格的精致阴影
        soft: '0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04)',
        card: '0 2px 8px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.03)',
        elevated: '0 8px 32px rgba(0,0,0,0.06), 0 2px 8px rgba(0,0,0,0.04)',
        ring: '0 0 0 1px rgba(0,0,0,0.06)',
        glow: '0 0 24px rgba(0,113,227,0.18)'
      },
      borderRadius: {
        DEFAULT: '0.625rem',
        lg: '0.875rem',
        xl: '1.125rem',
        '2xl': '1.375rem',
        '3xl': '1.75rem'
      },
      animation: {
        'fade-in': 'fadeIn .25s ease-out',
        'slide-up': 'slideUp .35s cubic-bezier(.2,.8,.2,1)',
        'pulse-slow': 'pulse 3s cubic-bezier(.4,0,.6,1) infinite'
      },
      keyframes: {
        fadeIn: { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        slideUp: {
          '0%': { opacity: 0, transform: 'translateY(8px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' }
        }
      }
    }
  }
}
