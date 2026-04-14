// @ts-check
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
const unusedImports = require('eslint-plugin-unused-imports');
const simpleImportSort = require('eslint-plugin-simple-import-sort');
const eslintPluginPrettierRecommended = require('eslint-plugin-prettier/recommended');
module.exports = tseslint.config(
  {
    ignores: [
      'dist/**/*',
      'node_modules/**/*',
      'app/**/*',
      '.gitignore',
      'package-lock.json',
      'package.json',
      'eslint.config.js',
      '.env',
    ],
  },
  {
    files: ['**/*.ts'],
    plugins: {
      'unused-imports': unusedImports,
      'simple-import-sort': simpleImportSort,
    },
    extends: [
      eslint.configs.recommended,
      ...tseslint.configs.recommended,
      ...tseslint.configs.stylistic,
      eslintPluginPrettierRecommended,
    ],
    rules: {
      'simple-import-sort/imports': 'error',
      'simple-import-sort/exports': 'error',
      'prettier/prettier': 'error',
      '@typescript-eslint/no-unused-vars': 'off',
      'unused-imports/no-unused-imports': 'error',
      'unused-imports/no-unused-vars': [
        'warn',
        {
          vars: 'all',
          varsIgnorePattern: '^_',
          args: 'after-used',
          argsIgnorePattern: '^_',
        },
      ],
    },
  }
);
