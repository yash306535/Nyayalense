// Flat config for the frontend. No build step and no dependencies: CI runs this
// with `npx eslint frontend`.
export default [
  {
    files: ['frontend/**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        fetch: 'readonly',
        console: 'readonly',
        localStorage: 'readonly',
        navigator: 'readonly',
        Intl: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        FormData: 'readonly',
        AbortController: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        requestAnimationFrame: 'readonly',
        speechSynthesis: 'readonly',
        SpeechSynthesisUtterance: 'readonly',
        CustomEvent: 'readonly',
        HTMLElement: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'no-undef': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      'prefer-const': 'error',
      'no-var': 'error',
      eqeqeq: ['error', 'always'],
      curly: ['error', 'multi-line'],
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-eval': 'error',
    },
  },
  {
    files: ['frontend/tests/**/*.js'],
    languageOptions: {
      globals: { process: 'readonly' },
    },
  },
];
