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

      // A `const` referenced in a hook dependency array above its declaration is a
      // temporal-dead-zone ReferenceError at render time - lint and the build both
      // passed while /assessment crashed on load that way. Function declarations are
      // hoisted and exempt; callbacks that reference a later const are ordered instead.
      'no-use-before-define': ['error', { functions: false, classes: true, variables: true, allowNamedExports: true }],

      // Derive state during render rather than writing it from an effect; see
      // hooks/useResetOnChange.js for the pattern this codebase uses.
      'react-hooks/set-state-in-effect': 'error',

      // Keep component modules exporting only components, so Fast Refresh can hot-swap
      // them. Hooks and plain helpers live in their own files (context/useAuth.js,
      // context/useTheme.js, components/Form/formHelpers.js).
      'react-refresh/only-export-components': ['error', { allowConstantExport: true }],
    },
  },
];
