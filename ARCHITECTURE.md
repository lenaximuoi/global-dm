# Architecture

## Goal

Global Life is an interactive, choice-driven narrative game. The player moves through a defined set of cities while balancing ambition, burnout, capital, creativity, and belonging.

The central design principle is simple: the language model writes the story, but application code owns durable game rules.

## Components

```text
world.json ──> app.py ──> engine.py ──> model backend
                  │          │
                  │          └── validated DMTurnResponse
                  v
             database.py ──> SQLite (life.db)
```

| Component | Responsibility |
| --- | --- |
| `world.json` | Canonical city data: themes, transition rules, signature items, and base attribute shifts. |
| `app.py` | CLI, backend selection, startup state, command handling, and presentation. |
| `engine.py` | Prompt construction, structured response schema, validation, and application of a turn. |
| `database.py` | SQLite schema and all durable state access. |
| `tests/` | Persistence, state-transition, and model-boundary tests without a live model call. |

## State and memory

SQLite intentionally separates memory into two layers:

1. **Authoritative state** - current city, visited cities, attributes, inventory, and durable relationship/decision flags.
2. **Recent context** - the 12 most recent player/narrator turns.

The model receives both layers, but only the first one defines what is true. This bounded transcript keeps prompts from growing without limit while preserving enough immediate context for natural conversation.

## Turn lifecycle

1. The player enters an action in the CLI.
2. `generate_turn` sends the system prompt, serialized SQLite state, and action to the selected backend.
3. The response is parsed into `DMTurnResponse` rather than accepted as free-form text.
4. `apply_turn` validates a requested city against `world.json`.
5. Application code applies the city’s base attribute shifts. The model cannot override these rules through narration.
6. Inventory, flags, attribute changes, and both transcript turns are written to SQLite.
7. Rich renders narrative separately from system updates.

## Backend boundary

The default backend is Ollama running locally through its OpenAI-compatible API. This keeps the demo free and private to the local machine after model download. The same engine can use the OpenAI API when `GLOBAL_LIFE_BACKEND=openai` is explicitly selected.

## Deliberate trade-offs

- SQLite is enough for one local player and makes saved state transparent. It is not a multi-user service.
- Generic JSON flags are flexible for a prototype; a production version would use typed tables for relationships, jobs, and milestones.
- The model may propose a city transition, but only the application validates it and calculates city effects.
- Recent history is capped instead of summarized. A future version should periodically generate a validated long-term life summary.
