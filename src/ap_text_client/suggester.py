from __future__ import annotations

from textual.suggester import Suggester

from .names import Names


class CommandSuggester(Suggester):
    """Inline autocomplete for Archipelago server commands.

    Completes these token positions against the live DataPackage / player table:

    ======================================  ==========================
    ``!hint <item>``                         my-game item names
    ``!hint_location <location>``            my-game location names
    ``!getitem <item>``                      my-game item names
    ``!send <player> <item>``                player aliases, then that player's items
    ======================================  ==========================

    Everything else returns no suggestion.
    """

    def __init__(self, names: Names) -> None:
        super().__init__(case_sensitive=False)
        self.names = names

    async def get_suggestion(self, value: str) -> str | None:
        if not value or not value.startswith("!"):
            return None
        lower = value.lower()
        if lower.startswith("!hint_location "):
            return self._match_location(value, len("!hint_location "))
        if lower.startswith("!hint "):
            return self._match_item(value, len("!hint "))
        if lower.startswith("!getitem "):
            return self._match_item(value, len("!getitem "))
        if lower.startswith("!send "):
            return self._match_send(value)
        return None

    def _match_item(self, value: str, cmd_len: int) -> str | None:
        partial = value[cmd_len:]
        if not partial:
            return None
        names = self._my_item_names()
        completion = _best_prefix(partial, names)
        return value[:cmd_len] + completion if completion else None

    def _match_location(self, value: str, cmd_len: int) -> str | None:
        partial = value[cmd_len:]
        if not partial:
            return None
        names = self._my_location_names()
        completion = _best_prefix(partial, names)
        return value[:cmd_len] + completion if completion else None

    def _match_send(self, value: str) -> str | None:
        prefix_len = len("!send ")
        rest = value[prefix_len:]
        if " " not in rest:
            if not rest:
                return None
            completion = _best_prefix(rest, self.names.players.slot_to_alias.values())
            return value[:prefix_len] + completion if completion else None

        player, remainder = rest.split(" ", 1)
        target_slot = next(
            (slot for slot, alias in self.names.players.slot_to_alias.items() if alias == player),
            None,
        )
        if target_slot is None or not remainder:
            return None
        game_store = self.names.games.get(self.names.players.game(target_slot))
        if not game_store:
            return None
        completion = _best_prefix(remainder, game_store.item_id_to_name.values())
        return value[:prefix_len] + player + " " + completion if completion else None

    def _my_item_names(self):
        game = self.names.players.game(self.names.players.my_slot)
        store = self.names.games.get(game)
        return store.item_id_to_name.values() if store else []

    def _my_location_names(self):
        game = self.names.players.game(self.names.players.my_slot)
        store = self.names.games.get(game)
        return store.location_id_to_name.values() if store else []


def _best_prefix(partial: str, candidates) -> str | None:
    """Return the shortest candidate that starts with ``partial`` (case-insensitive)."""
    plow = partial.lower()
    best: str | None = None
    for name in candidates:
        if name.lower().startswith(plow) and len(name) > len(partial):
            if best is None or len(name) < len(best):
                best = name
    return best
