"""Structured-output boundary between OpenAI and the persistent game state."""

from __future__ import annotations

import json
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from database import GameDatabase


class InventoryChange(BaseModel):
    action: Literal["add", "remove"]
    item_name: str = Field(min_length=1, max_length=100)


class QuestFlagChange(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    value: Any


class AttributeChange(BaseModel):
    attribute: Literal["ambition", "burnout", "capital", "creativity", "belonging"]
    delta: int = Field(ge=-20, le=20)


class DMTurnResponse(BaseModel):
    """The only shape the model may use to advance one life-story turn."""

    narrative: str = Field(min_length=1, max_length=2_500)
    inventory_changes: list[InventoryChange] = Field(default_factory=list)
    quest_flag_changes: list[QuestFlagChange] = Field(default_factory=list)
    city_id: str | None = None
    attribute_changes: list[AttributeChange] = Field(default_factory=list)


def generate_turn(
    client: OpenAI,
    database: GameDatabase,
    system_prompt: str,
    user_action: str,
    *,
    model: str = "gpt-4o-mini",
) -> DMTurnResponse:
    """Ask the model for one validated game turn without mutating the save.

    Keeping mutation out of this function makes it easy to retry failed model
    calls and ensures the application has one explicit write path.
    """
    state = json.dumps(database.state(), ensure_ascii=False, indent=2)
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": (
                    "Authoritative current game state follows. Do not invent items, "
                    "completed quests, or past events that contradict it.\n" + state
                ),
            },
            {"role": "user", "content": user_action},
        ],
        response_format=DMTurnResponse,
    )
    message = completion.choices[0].message
    if message.refusal:
        raise RuntimeError(f"The narrator declined the request: {message.refusal}")
    if message.parsed is None:
        raise RuntimeError("The narrator returned no structured response.")
    return message.parsed


def apply_turn(
    database: GameDatabase, response: DMTurnResponse, cities: dict[str, Any]
) -> list[str]:
    """Persist one accepted response and return human-readable state updates."""
    updates: list[str] = []
    with database.connection:
        if response.city_id:
            if response.city_id not in cities:
                raise ValueError(f"Unknown city returned by model: {response.city_id}")
            if database.move_to_city(response.city_id):
                city = cities[response.city_id]
                updates.append(f"Arrived: {city['name']}")
                for attribute, delta in database.adjust_attributes(
                    city["base_attribute_shifts"]
                ).items():
                    updates.append(f"{attribute.title()}: {delta:+d}")
        requested_changes: dict[str, int] = {}
        for change in response.attribute_changes:
            requested_changes[change.attribute] = (
                requested_changes.get(change.attribute, 0) + change.delta
            )
        for attribute, delta in database.adjust_attributes(requested_changes).items():
            updates.append(f"{attribute.title()}: {delta:+d}")
        for change in response.inventory_changes:
            changed = (
                database.add_item(change.item_name)
                if change.action == "add"
                else database.remove_item(change.item_name)
            )
            if changed:
                verb = "Added" if change.action == "add" else "Removed"
                updates.append(f"Item {verb}: {change.item_name}")
        for change in response.quest_flag_changes:
            database.set_flag(change.key, change.value)
            updates.append(f"Quest Updated: {change.key} = {change.value}")
        database.add_turn("assistant", response.narrative)
    return updates
