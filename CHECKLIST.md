# Build Checklist

Legend: `[x]` done · `[ ]` pending. The **✅ Tested by user** box at the end of each phase is ticked only after you've run that phase's tests yourself.

## Phase 0 — Project setup
- [x] `uv` project, `pyproject.toml`, `.gitignore`, `git init`
- [x] Folder skeleton (`app/{graph,agents,prompts,schemas,tools,llm,db}`, `tests/{unit,agents,e2e}`)
- [x] `.env.example` + `app/config.py` (pydantic-settings, per-role model override)
- [x] `app/llm/client.py` — `get_llm(role)` → ChatOpenAI on OpenCode Zen
- [x] `app/llm/structured.py` — native structured output with JSON-parse fallback + retries
- [x] `app/llm/prompts.py` — load markdown prompts from `app/prompts/`
- [x] `app/main.py` — `ping` command
- [x] `tests/unit/test_structured.py` (10 passing)
- [x] Live ping against Zen verified (`space-bunny-free`, native + JSON modes)
- [x] ✅ Tested by user

## Phase 1 — Topic Scout agent
- [x] `tools/sources/feeds.py` (RSS/Atom, parallel fetch, age filter) + `config/feeds.yaml` (2 niches + default)
- [x] `tools/sources/hackernews.py` (Algolia HN API: front page + keyword search)
- [x] `tools/sources/niches.py` (niche/alias resolution) + `tools/sources/candidates.py` (dedupe + pre-rank + cap)
- [x] `schemas/topic.py` — `Candidate`, `TopicSelection`, `TopicChoice`
- [x] `prompts/topic_scout.md`
- [x] `agents/topic_scout.py` — `run(state)` node + `choose_topic()` (source URLs taken from candidates, never from the LLM)
- [x] `dev scout` CLI command (`--niche`, `--instructions`, `--show`, `--sources-only`)
- [x] Tests: feeds, HN, niches, ranking, agent (fake LLM)
- [x] **Free-tier protection** (added on request): shared rate limiter, 429 backoff, per-run call budget, usage report, max_tokens cap, native-mode memo
- [x] Tests: `tests/unit/test_llm_limits.py` (41 passing total)
- [x] Live run verified (ai-engineering + software-engineering niches)
- [x] ✅ Tested by user

## Phase 2 — Researcher agent
- [x] ~~Tavily~~ → **free search, no API key**: `tools/sources/web_search.py` (`ddgs` metasearch; pluggable `SearchProvider`; 24h disk cache, pacing, backoff, per-run budget)
- [x] `tools/sources/articles.py` — full article text via `trafilatura` (Scout's source URLs + top search hits)
- [x] `schemas/research.py` — `SearchResult`, `Article`, `Source`, `ResearchPlan`, `BriefDraft`, `ResearchBrief`
- [x] `prompts/researcher_queries.md` (query planning) + `prompts/researcher.md` (cited brief)
- [x] `agents/researcher.py` — `run(state)` node + `research()`; citations validated in code (unknown IDs dropped, uncited stats dropped, inline "[n]" stripped)
- [x] `dev research` CLI command + `dev scout --research` chain
- [x] Tests: web search (cache/budget/backoff), articles, researcher agent (59 passing total)
- [x] Fix: detect replies truncated at `max_tokens` (fail fast instead of wasted retries); `LLM_MAX_TOKENS` 4096 → 16000
- [x] Live run verified (seeded research + scout→research chain)
- [x] ✅ Tested by user

## Phase 3 — Writer + Critic agents
- [x] `schemas/post.py` — `Draft` (hashtag normalization, `full_text()`), `Scores`, `CriticReview`, `Critique`
- [x] `tools/post_rules.py` — free rule checks: 3000-char limit, markdown, hook length, hashtags, URLs, wall-of-text
- [x] `config/voice.md` — editable author voice used by the Writer
- [x] `prompts/writer.md`, `prompts/critic.md`
- [x] `agents/writer.py` (write + revise from critic/human feedback), `agents/critic.py` (verdict decided in code: rule errors or any score < `CRITIC_MIN_SCORE` → revise)
- [x] `agents/context.py` — shared brief/draft/feedback formatting
- [x] `dev write` CLI (`--topic` or `--reuse-brief`, `--revisions`); briefs saved to `data/last_brief.json`
- [x] Tests: rules, schema, writer, critic, nodes (77 passing total)
- [x] Live run verified: first-draft pass, and forced revise loop hitting the revision cap
- [x] ✅ Tested by user

## Phase 4 — Manager + graph (chat, no publishing)
- [x] `schemas/manager.py` — `ManagerDecision` (plan, instructions, niche, topic_override, use_candidate_id, feedback, reply)
- [x] `prompts/manager.md`, `agents/manager.py` — plans once, reports back once (report-back mode enforced in code)
- [x] `graph/state.py` (`PostState`, `new_turn`), `graph/builder.py` (worker wrapper: error capture, activity log, topic reset), `graph/routing.py` (dispatcher: prerequisites, skip re-review, auto revise loop, step cap), `graph/checkpointer.py` (SQLite)
- [x] `chat` REPL: streamed agent progress, draft + critic display, `/draft`, `/quit`, `--thread` resume, `--niche`
- [x] Tests: routing (unit) + 8 e2e graph scenarios with scripted Manager (96 passing total)
- [x] Live run verified: full pipeline (7 calls), edit on resumed thread (4 calls), question (1 call)
- [x] Fix: Manager re-planned the user's edit on report-back and looped (15 calls) → report-back can't plan; regression test added
- [x] ✅ Tested by user

## Phase 5 — Human review + resume
- [x] `schemas/review.py` — `ReviewAction`; `Draft.from_full_text()` parses edited posts
- [x] `agents/human_review.py` — `interrupt()` with approve / edit / revise / reject; rule errors (e.g. >3000 chars) block approval
- [x] Every new reviewed draft auto-routes to human review before the Manager reports; Manager can also plan `human_review`
- [x] Approval guard: `publisher` can't be dispatched unless `approved` (review is inserted); a new draft always resets approval (enforced in the graph wrapper, not the agent)
- [x] CLI review prompt: approve / edit (`$EDITOR`, paste fallback) / revise / reject / later; pending review shown on chat start
- [x] `resume --thread` and `threads` (lists conversations + "waiting for your review") commands
- [x] Fix: `GraphInterrupt` subclasses `Exception` — worker wrapper now re-raises LangGraph control flow instead of swallowing it
- [x] Fix: model sent `use_candidate_id: 0` for "none" and the plan was dropped → placeholder values normalized in `ManagerDecision`
- [x] Fix: empty report-back reply showed a raw activity dump → readable state-based fallback
- [x] Tests: review actions, approval gate, auto-review routing, pending-review + new message (117 passing total)
- [x] Live run verified: review → later → quit → `threads` shows waiting → `resume` → revise → auto-revision → approve
- [x] ✅ Tested by user

## Phase 6 — LinkedIn publishing
- [x] `tools/linkedin/oauth.py` + `auth` / `auth --status` — local callback server, CSRF `state` check, token saved 0600
- [x] `tools/linkedin/client.py` — `/v2/userinfo`, `POST /rest/posts` (LinkedIn-Version 202609); "little" format escaping (unescaped `(` etc. truncates posts); no auto-retry on POST
- [x] `agents/publisher.py` — approval re-check, already-published check (text hash), final y/N confirm via `interrupt()`, dry run
- [x] `db/models.py`, `db/repository.py` — post history (published / dry_run); Topic Scout dedupes against published topics
- [x] `history` command; `chat --dry-run`; Manager plans `publisher` only on "post it"
- [x] Fix: "post it" with no draft skipped the critic → review prerequisite is writer+critic (but a user-edited draft is never sent to the critic)
- [x] Tests: client/escaping/errors, OAuth flow (real local callback + mocked LinkedIn), token perms/expiry, history, 9 e2e publish scenarios (148 passing total); `tests/conftest.py` isolates data/ from tests
- [x] Live run verified: dry-run publish via chat (2 calls), `history --all`, `auth` without app credentials
- [x] **Needs you:** LinkedIn app credentials → `auth` → a real post (not possible without your account)
- [x] ✅ Tested by user

## Phase 7 — Polish
- [x] `langgraph.json` + `app/graph/studio.py` — verified `langgraph dev` serves the graph (all 12 nodes)
- [x] Fix: per-turn counters were reset by the CLI's input only → moved into a `begin_turn` graph node (Studio/API clients would hit the Manager cap on turn 2); regression test
- [x] README rewritten as a full guide (quick start, everyday use, LinkedIn setup, config, Studio, dev)
- [x] Error handling: chat survives network errors/timeouts/5xx (friendly message), Ctrl+C cancels just the turn, unexpected errors keep the REPL alive; connection retries on RSS/HN/article fetches
- [x] Models settled: `space-bunny-free` for all roles (re-probed 2026-09-24: still the only free model usable via API); `LLM_FALLBACK_MODELS` auto-switches on 404/403 (stealth models rotate)
- [x] `doctor` command: checks LLM, RSS, HN, web search, LinkedIn token expiry, storage
- [x] ruff lint + format configured and clean; 151 tests passing
- [x] ✅ Tested by user


## Phase 8 — HTTP API for the web UI (FastAPI)
- [x] `app/services/` — logic shared by CLI + API (thread snapshots/listing/status, doctor checks, error messages); CLI `threads`/`doctor`/`llm_session` now use it
- [x] `app/api/server.py` — REST + Server-Sent Events (`start`, `step`, `interrupt`, `error`, `done`) streaming of agent progress
- [x] Endpoints: `GET/POST /api/threads`, `GET /api/threads/{id}`, `POST …/messages` (SSE), `POST …/resume` (SSE), `/api/history`, `/api/doctor`, `/api/linkedin` + `/connect`, `/api/settings`, `GET/PUT /api/voice`, `/api/health`
- [x] One run at a time (lock taken inside the stream so a dropped client can't leak it → 409 otherwise); dry-run flag scoped to the run; localhost-only by default (warning otherwise); CORS for Vite dev
- [x] `serve` CLI command (uvicorn, `/docs` for the OpenAPI UI)
- [x] Tests: 12 API tests with TestClient + fake agents (163 passing total)
- [x] Live run verified: real threads/snapshots, streamed a real chat turn over SSE, CORS preflight
- [x] ✅ Tested by user

## Phase 9 — Frontend scaffold (React + Vite + Tailwind)
- [x] `frontend/` Vite 8 + React 19 + TypeScript + Tailwind 4 (`@tailwindcss/vite`); design tokens in `src/index.css` `@theme`; Instrument Serif / IBM Plex Sans / IBM Plex Mono
- [x] App shell: sidebar (nav, conversations with status pills, new conversation, LinkedIn status card), React Router routes (`/chat`, `/chat/:id`, `/history`, `/settings`), API-offline banner
- [x] Typed API client (`src/api/client.ts`, `types.ts`) + fetch-based SSE reader (`sse.ts`, EventSource can't POST); Vite dev proxy `/api` → :8000
- [x] Chat page wired to real thread data (full workspace in Phase 10); History / Settings placeholders (Phase 11)
- [x] Dev port 5180 (5173 was taken by another app on this machine); API CORS allows both
- [x] Fix: Chrome's auto-dark mode inverted the palette → `color-scheme: only light`
- [x] `npm run build` / `lint` / `test` clean (4 SSE parser tests: split chunks, multi-byte chars, CRLF)
- [x] Live check in Chrome: shell renders with real conversations, no console errors
- [ ] ✅ Tested by user

## Phase 10 — Core flow screens
- [ ] Chat workspace: messages, live agent checklist, composer + suggestion chips, dry-run toggle, usage line
- [ ] Draft panel: post preview with "…see more" fold, critic scores, Draft / Research / Sources tabs
- [ ] Review screen: approve / edit / revise / reject / later, rule checks
- [ ] Publish confirmation modal + published toast
- [ ] ✅ Tested by user

## Phase 11 — Supporting screens & polish
- [ ] Research brief, History, Health & settings (doctor, LinkedIn connect, models, limits, voice editor)
- [ ] Loading / empty / error states; keyboard + accessibility pass
- [ ] Production build served by the API (`serve` hosts `frontend/dist`)
- [ ] ✅ Tested by user

---

## Notes / Decisions
- **2026-09-24 — Zen free tier restriction:** most free Zen models (`big-pickle`, `mimo-v2.5-free`, `nemotron-3-ultra-free`, `nemotron-3.5-lightning-free`) return `403 FreeTierError: "OpenCode's free tier can only be used from within OpenCode"` when called via the API. **`space-bunny-free` works** (reasoning model, ~2s replies, native tool calling OK) and is the default. Any paid Zen model can be set via `DEFAULT_MODEL` / `<ROLE>_MODEL` if needed.
- **Phase 1 — HN source:** uses the Algolia HN Search API instead of the Firebase API (keyword search + points/comments in one request).
- **Phase 1 — Scout cost:** 1 LLM call (~3.5k input tokens), 10–50s depending on how long the model reasons.
- **Free-tier limits (all in `.env`):** `LLM_REQUESTS_PER_MINUTE=20` (shared limiter), `LLM_RATE_LIMIT_RETRIES=3` with `LLM_RATE_LIMIT_BACKOFF=10` (10s/20s/40s or `Retry-After`), `MAX_LLM_CALLS_PER_RUN=30`, `LLM_MAX_TOKENS=16000`. Every command prints `LLM calls | tokens in/out`.
- **Phase 2 — search:** Tavily dropped on request. Using `ddgs` (free DuckDuckGo-based metasearch, no key). It's unofficial and throttles bursts, so queries are spaced 2s apart, retried with backoff (5s/10s), cached 24h in `data/cache/search/`, and capped by `MAX_SEARCHES_PER_RUN=6`. A failing query is skipped, not fatal.
- **Phase 2 — Researcher cost:** 2 LLM calls (plan queries + write brief; +1 if the JSON fallback kicks in), ≤4 searches, ≤6 full pages. ~30–90s.
- **Phase 2 — max_tokens finding:** `space-bunny-free` counts reasoning tokens toward `max_tokens` (~3–4k thinking for a brief). At 4096 the JSON was cut off (`finish_reason=length`); default raised to 16000 and truncation now fails fast with a clear message.
- **Phase 3 — cost:** Writer 1 call (~10–40s), Critic 1 call (~20–50s); each revision +2 calls. `--reuse-brief` skips research entirely.
- **Phase 3 — verdict:** the LLM only scores; code decides pass/revise so the loop is predictable. Posts with markdown or >3000 chars can never pass.
- **Phase 4 — cost per chat turn:** full post ≈ 7 LLM calls (Manager plan + Scout + Researcher×2 + Writer + Critic + Manager report); edit ≈ 4; question ≈ 1. Each auto-revision +2.
- **Phase 4 — design:** Manager returns a *plan*; a code-only dispatcher runs it (inserting prerequisites, driving the critic loop). Keeps Manager calls at ≤2 per turn instead of one per hop.
- **Phase 5 — review UX:** "later" leaves the review pending in the checkpoint; sending a new chat message instead starts a fresh turn (the pending review is dropped, draft kept unapproved; say "let me review it" to bring it back).
- **Phase 5 — live coverage:** later/resume/revise/approve exercised live; edit and reject covered by e2e tests (edit opens `$EDITOR`).
- **Phase 6 — publish flow:** approving ≠ publishing. "post it" → (review if needed) → `Publish as <you>? [y/N]` → post. Default is no.
- **Phase 6 — API facts (checked 2026-09-24 in LinkedIn docs):** Posts API `POST /rest/posts`, headers `LinkedIn-Version: YYYYMM` + `X-Restli-Protocol-Version: 2.0.0`, post id in `x-restli-id`; commentary uses "little" format with reserved chars `| { } @ [ ] ( ) < > # \ * _ ~`. Hashtags are made alphanumeric-only for that reason.
- Tests mock the OpenAI SDK with `httpx2.MockTransport` (the SDK uses `httpx2`; respx only intercepts `httpx`).
- `uv` created the venv with Python 3.14; project requires >= 3.12.
