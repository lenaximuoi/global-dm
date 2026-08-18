# Global Life

Global Life is a small AI-powered, choice-driven life story. The player navigates work, identity, relationships, and belonging across a fixed set of global cities.

The project deliberately separates creative narration from durable game rules: a model writes the story, while Python and SQLite own city validation, attribute changes, and saved progress.

## Features

- City world model in `world.json`, including themes, transition rules, and baseline attribute shifts.
- Natural-language terminal interaction powered by a local Ollama model by default.
- Persistent progress in SQLite: city, attributes, visited cities, inventory, decisions, and recent history.
- Structured model output through Pydantic, so narration and state changes are handled separately.
- Deterministic validation and city effects in application code.

## Quick start: free local mode

Prerequisites: Python 3.11+ and [Ollama](https://ollama.com) running locally.

```bash
git clone <your-repository-url>
cd global-dm
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
ollama pull llama3.2
python app.py
```

The first model download is about 2 GB. After that, the game runs locally and does not need an API key. Confirm that Ollama is available with `ollama list`.

Try `/cities`, `/status`, `/inventory`, `/journal`, or `/quit`. For example:

```text
I decide to return home to Saigon to see my family.
```

## Optional OpenAI backend

```bash
export OPENAI_API_KEY="your-key"
GLOBAL_LIFE_BACKEND=openai python app.py
```

## Test

```bash
python -m unittest discover -s tests -v
```

The test suite is deterministic and does not call either model backend.

## Project structure

```text
app.py             CLI and backend selection
engine.py          structured model boundary and state application
database.py        SQLite persistence layer
world.json         canonical world data
tests/             deterministic unit tests
docs/              architecture notes
```

## Design notes

See [Architecture](ARCHITECTURE.md) for the component boundaries and trade-offs.

## Next steps

With another day, I would add a validated long-term life summary, typed relationship/job/milestone entities, travel time and costs, database migrations, streaming output, and scenario-based evaluations for long-horizon consistency.
