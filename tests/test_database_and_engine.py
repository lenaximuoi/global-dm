import tempfile
import unittest
from pathlib import Path

from database import GameDatabase
from engine import (
    AttributeChange,
    DMTurnResponse,
    InventoryChange,
    QuestFlagChange,
    apply_turn,
    generate_turn,
)


CITIES = {
    "san_francisco": {"name": "San Francisco", "base_attribute_shifts": {"ambition": 20}},
    "saigon": {"name": "Saigon", "base_attribute_shifts": {"belonging": 30, "burnout": -20}},
}


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.arguments = None

    def parse(self, **kwargs):
        self.arguments = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        completions = FakeCompletions(response)
        self.beta = type("Beta", (), {"chat": type("Chat", (), {"completions": completions})()})()
        self.completions = completions


class GameDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = GameDatabase(Path(self.directory.name) / "save.db")
        self.database.initialize_life("san_francisco", {"ambition": 50, "burnout": 20})

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def test_database_state_round_trip(self):
        self.database.add_item("Rusty Key")
        self.database.set_flag("letter_read", True)
        self.database.add_turn("user", "I read the letter.")

        state = self.database.state()
        self.assertEqual(state["inventory"], ["Rusty Key"])
        self.assertTrue(state["quest_flags"]["letter_read"])
        self.assertEqual(
            state["recent_history"], [{"role": "user", "content": "I read the letter."}]
        )

    def test_apply_turn_persists_only_structured_updates(self):
        turn = DMTurnResponse(
            narrative="The key is cold in your hand.",
            inventory_changes=[InventoryChange(action="add", item_name="Rusty Key")],
            quest_flag_changes=[QuestFlagChange(key="letter_read", value=True)],
        )

        updates = apply_turn(self.database, turn, CITIES)

        self.assertEqual(updates, ["Item Added: Rusty Key", "Quest Updated: letter_read = True"])
        self.assertEqual(self.database.inventory(), ["Rusty Key"])
        self.assertTrue(self.database.flags()["letter_read"])
        self.assertEqual(
            self.database.history(), [{"role": "assistant", "content": turn.narrative}],
        )

    def test_city_move_applies_world_shifts_and_tracks_visits(self):
        turn = DMTurnResponse(
            narrative="You land before the familiar humidity of Saigon.",
            city_id="saigon",
            attribute_changes=[AttributeChange(attribute="creativity", delta=5)],
        )

        updates = apply_turn(self.database, turn, CITIES)

        self.assertEqual(self.database.player_state()["current_city"], "saigon")
        self.assertEqual(self.database.player_state()["visited_cities"], ["san_francisco", "saigon"])
        self.assertEqual(self.database.player_state()["attributes"], {"ambition": 50, "burnout": 0, "belonging": 30, "creativity": 5})
        self.assertIn("Arrived: Saigon", updates)

    def test_generate_turn_passes_state_to_structured_parse(self):
        parsed = DMTurnResponse(narrative="Rain rattles the windows.")
        message = type("Message", (), {"refusal": None, "parsed": parsed})()
        response = type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()
        client = FakeClient(response)
        self.database.add_item("Rusty Key")

        result = generate_turn(client, self.database, "Be a careful DM.", "I inspect the key.")

        self.assertIs(result, parsed)
        self.assertIs(client.completions.arguments["response_format"], DMTurnResponse)
        messages = client.completions.arguments["messages"]
        self.assertIn("Rusty Key", messages[1]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "I inspect the key."})
