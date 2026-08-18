"""Command-line entry point for a global, choice-driven life story."""

from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from database import GameDatabase
from engine import apply_turn, generate_turn


ROOT = Path(__file__).parent
WORLD = json.loads((ROOT / "world.json").read_text())
CITIES = WORLD["cities"]
START_CITY_ID = next(city_id for city_id, city in CITIES.items() if city["is_start"])
INITIAL_ATTRIBUTES = {
    "ambition": 50,
    "burnout": 20,
    "capital": 30,
    "creativity": 40,
    "belonging": 40,
}
SYSTEM_PROMPT = f"""You are the narrator of a choice-driven life story about a protagonist navigating
ambition, belonging, work, love, and identity across global cities. This JSON is canonical world data:
{json.dumps(WORLD, ensure_ascii=False)}

Write vivid but concise second-person prose (one to three short paragraphs). Respect agency: show
consequences but never make choices for the player. Use the current city, its theme, and the relevant
sequence rule for the previous city. A city_id must be one of the JSON keys and only be set after the
player explicitly makes and completes a meaningful move. When a city_id is set, do not include that
city's base attribute shifts in attribute_changes: the application applies them deterministically.
Use small attribute_changes only for important personal consequences. Treat inventory as personal
objects, quest flags as durable relationships, commitments, and decisions. Keep the tone specific,
emotionally honest, and contemporary."""


def status_line(database: GameDatabase) -> str:
    state = database.player_state()
    city_name = CITIES[state["current_city"]]["name"]
    attributes = " | ".join(
        f"{name.title()}: {value}" for name, value in state["attributes"].items()
    )
    return f"[cyan]{city_name}[/cyan]  [dim]{attributes}[/dim]"


def main() -> None:
    console = Console()
    database = GameDatabase(ROOT / "life.db")
    database.initialize_life(START_CITY_ID, INITIAL_ATTRIBUTES)
    backend_choice = os.environ.get("GLOBAL_LIFE_BACKEND", "ollama")
    if backend_choice == "ollama":
        ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        model = ollama_model
        backend = f"Ollama local model: {model}"
    elif backend_choice == "openai" and os.environ.get("OPENAI_API_KEY"):
        client = OpenAI()
        model = "gpt-4o-mini"
        backend = "OpenAI API"
    else:
        console.print(
            "[bold red]No model backend is configured.[/bold red] "
            "Use Ollama (the default) or set GLOBAL_LIFE_BACKEND=openai and OPENAI_API_KEY."
        )
        return
    start_city = CITIES[START_CITY_ID]
    opening = (
        f"You begin in {start_city['name']}. {start_city['theme']}\n\n"
        "Your life is still open-ended. What do you choose to do first?"
    )
    console.print(Panel(opening, title="Global Life", border_style="cyan"))
    console.print(f"[dim]{backend}[/dim]")
    console.print("[dim]Type /status, /cities, /inventory, /journal, or /quit.[/dim]")

    try:
        while True:
            action = Prompt.ask("[bold yellow]What do you do?[/bold yellow]").strip()
            if not action:
                continue
            if action == "/quit":
                break
            if action == "/inventory":
                items = database.inventory()
                console.print(f"[green]Inventory:[/green] {', '.join(items) if items else 'empty'}")
                continue
            if action == "/status":
                console.print(status_line(database))
                continue
            if action == "/cities":
                current_city = database.player_state()["current_city"]
                for city_id, city in CITIES.items():
                    marker = "[bold green]*[/bold green]" if city_id == current_city else " "
                    console.print(f"{marker} [cyan]{city['name']}[/cyan] - {city['theme']}")
                continue
            if action == "/journal":
                for turn in database.history():
                    console.print(f"[dim]{turn['role'].title()}:[/dim] {turn['content']}")
                continue

            try:
                turn = generate_turn(client, database, SYSTEM_PROMPT, action, model=model)
                database.add_turn("user", action)
                updates = apply_turn(database, turn, CITIES)
            except Exception as error:
                console.print(f"[bold red]The story pauses:[/bold red] {error}")
                continue

            console.print(Panel(turn.narrative, title="Your Story", border_style="magenta"))
            for update in updates:
                console.print(f"[bold green]{update}[/bold green]")
            console.print(status_line(database))
    finally:
        database.close()


if __name__ == "__main__":
    main()
