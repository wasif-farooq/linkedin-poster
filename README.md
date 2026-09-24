# LinkedIn Poster

A manager-led multi-agent app built on [LangGraph](https://langchain-ai.github.io/langgraph/). You chat with a **Manager**, and it directs a small team:

| Agent | Job |
|---|---|
| 🔎 **Topic Scout** | Picks a fresh, relevant story from RSS feeds and Hacker News, and skips topics you've already posted about |
| 📚 **Researcher** | Reads the source articles, runs free web searches, and writes a brief in which every claim cites a source |
| ✍️ **Writer** | Turns the brief into a plain-text LinkedIn post in your voice (`config/voice.md`) |
| 🧐 **Critic** | Scores the hook, insight, accuracy, clarity and tone, runs free rule checks, and sends weak drafts back for revision |
| 👤 **You** | Approve, edit, revise or reject every draft |
| 🚀 **Publisher** | Posts to LinkedIn, only after your approval and a final yes/no |

```
you ⇄ Manager ──plan──▶ dispatcher ──▶ Scout → Researcher → Writer ⇄ Critic → your review → Publisher
         ▲                                                                                    │
         └──────────────────────────── report back ◀──────────────────────────────────────────┘
```

The Manager makes a plan, and code runs it. The dispatcher adds missing steps and runs the Critic's revise loop, up to a cap. Anything safety-related is enforced in code, never left to the model:
- You must approve before anything is published.
- A new draft cancels any earlier approval.
- The same post is never published twice.

## Quick start

```bash
uv sync
cp .env.example .env        # optional: env vars from your shell work too
export OPEN_CODE_KEY=...    # OpenCode Zen API key
uv run linkedin-poster doctor
uv run linkedin-poster chat --dry-run
```

In the chat, say "find a trending AI topic and draft a post". Review the draft, approve it, then say "post it". Because of `--dry-run`, the post is only recorded locally. Drop `--dry-run` once LinkedIn is connected (see below).

## Everyday use

```bash
uv run linkedin-poster chat                       # new conversation (prints its thread ID)
uv run linkedin-poster chat --niche "software engineering"
uv run linkedin-poster threads                    # conversations, incl. "waiting for your review"
uv run linkedin-poster resume --thread <id>       # continue, starting with any pending review
uv run linkedin-poster history                    # what you've published (--all adds dry runs)
uv run linkedin-poster doctor                     # check model, feeds, search, LinkedIn, storage
```

**Things to say to the Manager:**
- "find a trending AI topic and draft a post"
- "write about \<topic\>"
- "use the runner-up"
- "find another topic"
- "make it shorter"
- "punchier hook"
- "less formal"
- "show me the sources"
- "let me review it"
- "post it"

In the chat, `/draft` shows the current draft and `/quit` exits. Ctrl+C cancels the current turn but keeps the conversation.

**Reviewing a draft:** each new draft pauses for you once the Critic has scored it.

| Key | Action |
|---|---|
| `a` | Approve: locks in the final post. It isn't published until you say "post it" |
| `e` | Edit it yourself in `$EDITOR`. Your version is approved if it's under 3,000 characters and has no markdown |
| `r` | Revise: tell the Writer what to change. It rewrites, the Critic re-checks, and the draft comes back to you |
| `x` | Reject: drops the draft but keeps the topic and research |
| `l` | Later: leaves the review pending, so you can come back with `resume` |

**Publishing:** saying "post it" runs your review first if the draft isn't approved yet. It then asks one last `Publish to LinkedIn as <you>? [y/N]`, where the default is no.
- Identical text is never posted twice, so resuming after a crash is safe.
- The API call is never retried automatically.
- Special characters are escaped for LinkedIn's post format. Unescaped, text after a `(` can silently vanish.

## Connect LinkedIn (one-time)

1. Go to <https://www.linkedin.com/developers/apps> and click **Create app**. LinkedIn requires the app to be linked to a LinkedIn Page; any page you admin works.
2. On the **Products** tab, add **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**. Both are self-serve.
3. On the **Auth** tab, add the redirect URL `http://localhost:8765/callback`, then copy the **Client ID** and **Primary Client Secret**.
4. Put them in `.env` as `LINKEDIN_CLIENT_ID=...` and `LINKEDIN_CLIENT_SECRET=...`.
5. Run `uv run linkedin-poster auth`. It opens your browser for consent and saves the token to `data/linkedin_token.json`, readable only by you.
6. Check it with `uv run linkedin-poster auth --status`. `doctor` warns you when fewer than 7 days are left.

Tokens last about 60 days, and LinkedIn doesn't let most apps refresh them. When yours expires, run `auth` again.

## Configuration

Everything is set in `.env` (see `.env.example`) or in environment variables.

**Models (OpenCode Zen, OpenAI-compatible API):**
- The default model is `space-bunny-free` for every agent. As of 2026-09-24 it's the only free Zen model that works outside OpenCode. The others return `FreeTierError`.
- To set one model for everything, use `DEFAULT_MODEL`. To set a model for one agent, use a per-agent override: `MANAGER_MODEL`, `TOPIC_SCOUT_MODEL`, `RESEARCHER_MODEL`, `WRITER_MODEL` or `CRITIC_MODEL`.
- `LLM_FALLBACK_MODELS`: comma-separated models to switch to if the current one is removed or blocked (HTTP 404/403). Free "stealth" models rotate, so adding a paid model here is a cheap safety net.
- `ping --model <id>` tries any model directly.

**Content:**
- `config/voice.md`: your tone and style. The Writer follows it on every post.
- `config/feeds.yaml`: niches with their RSS feeds and Hacker News keywords. An unknown niche uses the default feeds, with keywords taken from the niche name.
- `CRITIC_MIN_SCORE` (default 7): any Critic score below this sends the draft back for revision. `MAX_REVISIONS` (default 2) caps the automatic revisions.
- `POST_TARGET_MIN_CHARS` / `POST_TARGET_MAX_CHARS`: the target length for posts.

**Free-tier protection.** All agents share one key, so these limits apply to all of them:

| Setting | Default | What it does |
|---|---|---|
| `LLM_REQUESTS_PER_MINUTE` | 20 | Shared client-side rate limiter |
| `LLM_RATE_LIMIT_RETRIES` / `LLM_RATE_LIMIT_BACKOFF` | 3 / 10s | On HTTP 429, waits 10s, 20s, then 40s, or the server's `Retry-After` |
| `MAX_LLM_CALLS_PER_RUN` | 30 | Hard stop per chat turn, so a loop can't burn the quota |
| `LLM_MAX_TOKENS` | 16000 | Cap on output tokens per call. Reasoning tokens count toward it, and a cut-off reply fails fast with a clear message |
| `MAX_SEARCHES_PER_RUN` | 6 | Live web searches per turn. Cached results (24h) are free |
| `SEARCH_MIN_INTERVAL` / `SEARCH_BACKOFF` | 2s / 5s | Gap between searches, and the retry wait (doubled each retry) |
| `MAX_ARTICLES_PER_RUN` | 6 | Full pages the Researcher reads |

Typical cost: a full post takes about 7 LLM calls and up to 4 searches, an edit about 4 calls, and a question 1. Every command prints a usage line, for example `LLM calls: 7 | tokens in: 17,899 out: 14,104 | searches: 4 (+0 cached)`.

**Web search is free and needs no key.** It uses [`ddgs`](https://pypi.org/project/ddgs/), a DuckDuckGo-based metasearch. Article text is extracted with `trafilatura`.

## Web API (for the React UI)

```bash
uv run linkedin-poster serve            # http://127.0.0.1:8000 — interactive docs at /docs
```

It runs the same graph as the CLI and shares its conversations. Live agent progress is streamed as Server-Sent Events (`start`, `step`, `interrupt`, `error`, `done`). Only one run happens at a time; a second request gets HTTP 409. The API has no login and can publish to your LinkedIn, so it binds to localhost by default.

| Endpoint | What it does |
|---|---|
| `GET /api/threads` · `POST /api/threads` | List conversations with their status · start a new one (optional `niche`) |
| `GET /api/threads/{id}` | Everything about one conversation: messages, topic, brief, draft, critique, approval, publish result, pending review |
| `POST /api/threads/{id}/messages` | `{text, dry_run}` → SSE stream of the turn |
| `POST /api/threads/{id}/resume` | `{answer, dry_run}` answers a review (`{"action": "approve"|"edit"|"revise"|"reject", "text"}`) or a publish confirmation (`{"confirm": true}`) → SSE |
| `GET /api/history` · `GET /api/doctor` | Post history · health checks |
| `GET /api/linkedin` · `POST /api/linkedin/connect` | Connection status · start OAuth (returns the URL to open) |
| `GET /api/settings` · `GET/PUT /api/voice` | Models and limits · your voice guide |

## Web UI (in progress)

```bash
uv run linkedin-poster serve                  # terminal 1: API on :8000
cd frontend && npm install && npm run dev     # terminal 2: http://localhost:5180
```

See [frontend/README.md](frontend/README.md).

## Visual debugging with LangGraph Studio

```bash
uv run langgraph dev        # opens Studio with the `linkedin_poster` graph
```

Send `{"messages": [{"role": "user", "content": "find a topic and draft a post"}]}` as input. Reviews and publish confirmations show up as interrupts that you resume from Studio.

## Working on single agents

```bash
uv run linkedin-poster dev scout [-n niche] [-i instructions] [--sources-only] [--research]
uv run linkedin-poster dev research -t "topic" [-a angle] [-u seed-url ...]
uv run linkedin-poster dev write -t "topic" | --reuse-brief [--revisions N]
uv run linkedin-poster -v <command>    # debug logging
```

`dev research` and `dev write` save the brief to `data/last_brief.json`, and `--reuse-brief` iterates on the writing without paying for research again.

## Development

```bash
uv run pytest                 # 151 tests, no network or API keys needed
uv run ruff check . && uv run ruff format --check .
```

The tests mock every external service: the LLM, RSS, Hacker News, search, and LinkedIn, including a real localhost OAuth callback. `tests/conftest.py` keeps them away from your real `data/` directory.

## Layout

```
app/
  main.py        CLI (chat, resume, threads, auth, history, doctor, ping, dev ...)
  config.py      settings from .env / environment
  graph/         state, builder (nodes + safety invariants), routing (dispatcher), checkpointer, studio entry
  agents/        one file per node: manager, topic_scout, researcher, writer, critic, human_review, publisher
  prompts/       markdown prompts per agent
  schemas/       Pydantic contracts between agents
  tools/         deterministic helpers: sources/ (RSS, HN, search, articles), linkedin/, post_rules
  llm/           Zen client (rate limit, backoff, fallback), structured output, usage/budgets
  db/            post history (SQLite)
config/          feeds.yaml, voice.md
data/            (gitignored) checkpoints.db, history.db, linkedin_token.json, caches
tests/           unit/, agents/, e2e/
```

Build history, design decisions and findings: [CHECKLIST.md](CHECKLIST.md).
