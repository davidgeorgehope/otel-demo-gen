# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI service with `main.py` entrypoint plus scenario generators (`generator.py`, `scenario_llm_gen.py`).
- `frontend/`: React/Vite app; UI lives in `src/`, shared assets in `public/`, styling via Tailwind configs.
- `k8s/`, `helm/`: Cluster manifests and charts; place environment overrides here rather than inside app code.
- `scripts/deploy.sh`: Docker build and Kubernetes deploy helper—extend its functions when automating releases.
- Root helpers: `docker-compose.yml` for local collector + UI, `otel-collector-config.yaml` for OTLP routing, `.env.example` for required secrets.

## Build, Test, and Development Commands
- `./start-local.sh`: Provision deps and run backend + frontend with automatic ports.
- `cd backend && pip install -r requirements.txt`: Sync Python dependencies.
- `cd backend && uvicorn main:app --reload --port 8000`: Standalone API serve for debugging.
- `cd frontend && npm install`: Install Node toolchain.
- `cd frontend && npm run dev`: Launch the UI with the API proxied at `/api`.
- `cd frontend && npm run lint` / `npm run build`: Lint or bundle before submitting changes.

## Coding Style & Naming Conventions
- Python: adhere to PEP 8, four-space indent, snake_case modules, and typed Pydantic models.
- JavaScript: follow `eslint.config.js`, prefer functional components, hooks in camelCase, and PascalCase file names for React views.
- YAML/JSON configs should carry descriptive prefixes (`config_`, `otel_`) to stay discoverable.

## Testing Guidelines
- Add pytest suites under `backend/tests/` mirroring module names (`test_generator.py`).
- Frontend specs belong in `frontend/src/__tests__/`, using React Testing Library and Vite's default Vitest runner when introduced.
- Document any new test commands (e.g., `pytest`, `npm run test`) in your PR and run them alongside `npm run lint`.

## Commit & Pull Request Guidelines
- Commits stay short and present tense, matching history such as `"fix header"` or `"error handling"`.
- Separate backend and frontend changes when practical to aid reviewers.
- Pull requests need a concise summary, affected paths, manual verification steps, and linked issues. Attach screenshots or curl output when behavior changes.
- Update `.env.example` instead of committing real secrets; call out configuration impacts in the PR body.

## Deployment Notes
- `scripts/deploy.sh deploy` builds, pushes, and applies Kubernetes resources; `scripts/deploy.sh status` checks cluster state.
- Combine `docker-compose up` with `./start-local.sh` to feed telemetry into the bundled OpenTelemetry Collector during local demos.
