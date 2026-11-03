import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

// Type-aware lint focused on deprecated API usage. ADS deprecates props in
// JSDoc before removing them; `@typescript-eslint/no-deprecated` turns those
// into errors so we follow the documented replacement instead of guessing.
export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "e2e/.auth/**",
      "e2e/.results/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "@typescript-eslint": tseslint.plugin,
      "react-hooks": reactHooks,
    },
    rules: {
      "@typescript-eslint/no-deprecated": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
);
