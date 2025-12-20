import next from '@next/eslint-plugin-next'
import tseslint from '@typescript-eslint/eslint-plugin'
import tsParser from '@typescript-eslint/parser'
import importPlugin from 'eslint-plugin-import'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'

const jsxA11yRecommendedWarn = Object.fromEntries(
  Object.entries(jsxA11y.configs.recommended.rules).map(([name, rule]) => {
    if (Array.isArray(rule)) return [name, ['warn', ...rule.slice(1)]]
    return [name, 'warn']
  }),
)

/** @type {import('eslint').Linter.FlatConfig[]} */
export default [
  {
    ignores: [
      '**/.next/**',
      '**/.amplify-hosting/**',
      '**/node_modules/**',
      '**/out/**',
      '**/dist/**',
      '**/coverage/**',
    ],
  },
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      '@next/next': next,
      react,
      'react-hooks': reactHooks,
      '@typescript-eslint': tseslint,
      import: importPlugin,
      'jsx-a11y': jsxA11y,
    },
    settings: {
      react: { version: 'detect' },
    },
    rules: {
      ...next.configs.recommended.rules,
      ...next.configs['core-web-vitals'].rules,
      ...jsxA11yRecommendedWarn,

      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // Keep existing behavior (TypeScript already covers most of this)
      'react/react-in-jsx-scope': 'off',
    },
  },
]
