# UniFi Lock Controller Frontend

This Astro + React implementation recreates the Streamlit dashboard with a modern component stack (Tailwind, shadcn-style primitives) and a ports/adapters architecture so that backend integrations can be swapped in easily.

## Stack

- [Astro](https://astro.build) with the React renderer
- TypeScript
- Tailwind CSS
- shadcn-inspired UI primitives built with `class-variance-authority`
- Ports/adapters service layer (mock adapter backed by local JSON until API endpoints are available)

## Getting started

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:4321`.

## Key structure

- `src/data/mock-config.json` – mock configuration and device inventory
- `src/lib/ports` – ports (interfaces) describing the operations the UI needs
- `src/lib/adapters` – adapters implementing those ports (`MockLockControllerAdapter` reads the JSON file)
- `src/lib/services` – application services wiring adapters with UI
- `src/components` – React UI components (owners grid, PIN modal, unregistered devices, etc.)
- `src/pages` – Astro pages (`/`, `/owner/[key]`)
- `tests` – Playwright end-to-end scenarios
- `src/components/**/__tests__` – Vitest unit/component tests

### Backend configuration

The frontend defaults to local mock data. To point it at the FastAPI backend:

```bash
# frontend/.env (create if needed)
PUBLIC_USE_MOCK_DATA=false
PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Then restart `npm run dev`. The `ApiLockControllerAdapter` will consume the backend endpoints described in `src/lib/api/openapi.json` via the generated client in `src/lib/api/client.ts`.

## Tooling commands

| Script | Description |
| --- | --- |
| `npm run format` | Format the entire codebase with Prettier (& Tailwind class sorting) |
| `npm run format:check` | Verify formatting without writing |
| `npm run lint` / `npm run lint:fix` | ESLint with type-aware rules for Astro + React |
| `npm run typecheck` | `tsc --noEmit` for TypeScript |
| `npm run astro:check` | Astro component type check |
| `npm run test` / `npm run test:watch` | Vitest unit/component suite (jsdom) |
| `npm run test:coverage` | Vitest with coverage report (text + HTML in `coverage/`) |
| `npm run e2e` | Playwright headed run (Chromium only) |
| `npm run e2e:ci` | Playwright cross-browser run with line reporter |

Playwright stores traces, screenshots, and videos in `playwright-report/` on failure. Open the HTML report with:

```bash
npm run e2e:ci
npx playwright show-report
```

## Git hooks

- Husky installs automatically via `npm install`.
- `lint-staged` ensures only staged files are linted/formatted during `git commit`.

## Continuous integration

See `.github/workflows/frontend-ci.yml` for the CI pipeline: install, format check, lint, type checks, Vitest (coverage upload), and Playwright E2E with trace artifacts.
