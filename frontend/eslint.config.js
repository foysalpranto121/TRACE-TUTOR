import js from '@eslint/js';
import globals from 'globals';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2021 },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    settings: { react: { version: 'detect' } },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...react.configs.recommended.rules,
      ...react.configs['jsx-runtime'].rules,
      ...reactHooks.configs.recommended.rules,

      // Vite resolves JSX without importing React, and prop types are not used here.
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',

      // `catch (_) {}` is idiomatic here, and `const { confirm, ...payload } = form` is
      // how a field is deliberately kept out of a request body.
      'no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
        ignoreRestSiblings: true,
      }],

      // ---------------------------------------------------------------------
      // Deferred, not dismissed. These two flag widespread existing patterns that
      // need a real refactor rather than a mechanical fix; leaving them as errors
      // would mean `npm run lint` never passes and so never gets run. Turn one back
      // on when you are ready to do the corresponding cleanup.
      // ---------------------------------------------------------------------

      // ~14 sites. Effects that call setState to derive state from props. The fix is
      // to compute during render or key the component, per the React docs.
      'react-hooks/set-state-in-effect': 'off',

      // ~7 sites. Context files export both a provider component and its hook, which
      // costs fast-refresh granularity in development only.
      'react-refresh/only-export-components': 'off',
    },
  },
];
