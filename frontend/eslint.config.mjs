import path from "node:path";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import astro from "eslint-plugin-astro";
import astroParser from "astro-eslint-parser";
import reactHooks from "eslint-plugin-react-hooks";
import importPlugin from "eslint-plugin-import";
import testingLibrary from "eslint-plugin-testing-library";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tsconfigPath = path.resolve(__dirname, "tsconfig.json");

export default tseslint.config(
  {
    ignores: [
      "dist",
      ".astro",
      ".vite",
      "coverage",
      "playwright-report",
      "test-results",
      "node_modules"
    ]
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked.map((config) => ({
    ...config,
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ...config.languageOptions,
      parserOptions: {
        ...config.languageOptions?.parserOptions,
        project: tsconfigPath,
        tsconfigRootDir: __dirname,
        ecmaVersion: "latest",
        sourceType: "module"
      }
    }
  })),
  {
    files: ["**/*.astro"],
    plugins: {
      astro
    },
    languageOptions: {
      parser: astroParser,
      parserOptions: {
        parser: tseslint.parser,
        project: tsconfigPath,
        tsconfigRootDir: __dirname,
        extraFileExtensions: [".astro"]
      }
    },
    rules: {
      ...astro.configs.recommended.rules
    }
  },
  {
    files: ["**/*.{ts,tsx,jsx,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      import: importPlugin
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "import/order": [
        "error",
        {
          groups: ["builtin", "external", "internal", "parent", "sibling", "index"],
          "newlines-between": "always",
          alphabetize: { order: "asc", caseInsensitive: true }
        }
      ],
      "no-unsafe-optional-chaining": "error",
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^ignored" }
      ]
    }
  },
  {
    files: ["**/*.astro/*.ts"],
    languageOptions: {
      parserOptions: {
        project: tsconfigPath,
        tsconfigRootDir: __dirname
      }
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^ignored" }
      ],
      "@typescript-eslint/no-floating-promises": "error"
    }
  },
  {
    files: ["**/__tests__/**/*", "**/*.{test,spec}.{ts,tsx}"],
    plugins: {
      "testing-library": testingLibrary
    },
    languageOptions: {
      globals: {
        ...testingLibrary.environments?.jsdom?.globals,
        vi: true
      }
    },
    rules: {
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "testing-library/no-debugging-utils": "warn"
    }
  },
  {
    files: ["**/*.{config,mjs,cjs,cts,mts}"],
    languageOptions: {
      globals: {
        console: "readonly",
        URL: "readonly",
        process: "readonly"
      }
    },
    rules: {
      "@typescript-eslint/no-var-requires": "off"
    }
  }
);
