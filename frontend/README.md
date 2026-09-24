# Poster web UI

React 19, Vite 8, TypeScript and Tailwind CSS 4. The screens follow the design canvas; the design tokens live in `src/index.css` under `@theme`.

## Develop

```bash
# terminal 1 — the Python API (repo root)
uv run linkedin-poster serve            # http://127.0.0.1:8000

# terminal 2 — this app
cd frontend
npm install
npm run dev                             # http://localhost:5180 (proxies /api to :8000)
```

To point the dev server at a different API, set `API_URL`, e.g. `API_URL=http://127.0.0.1:9000 npm run dev`.

```bash
npm run build     # type-check + production build to dist/
npm run lint      # oxlint
npm test          # vitest
```

## Layout

```
src/
  api/          typed client (client.ts), API types (types.ts), SSE stream reader (sse.ts)
  layout/       app shell: sidebar (nav, conversations, LinkedIn status), offline banner
  pages/        routed screens
  components/   Icon, StatusPill, ...
  hooks/        useResource (load + reload async data)
```

The run endpoints stream Server-Sent Events over a POST, which `EventSource` can't send. `api/sse.ts` therefore reads the stream with `fetch`.
