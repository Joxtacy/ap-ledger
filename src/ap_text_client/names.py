from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


ARCHIPELAGO_GAME = "Archipelago"


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ap-text-client" / "datapackage"


@dataclass
class GameNames:
    item_id_to_name: dict[int, str] = field(default_factory=dict)
    location_id_to_name: dict[int, str] = field(default_factory=dict)
    checksum: str = ""

    @classmethod
    def from_game_data(cls, game_data: dict) -> "GameNames":
        return cls(
            item_id_to_name={
                v: k for k, v in game_data.get("item_name_to_id", {}).items()
            },
            location_id_to_name={
                v: k for k, v in game_data.get("location_name_to_id", {}).items()
            },
            checksum=game_data.get("checksum", ""),
        )


@dataclass
class Players:
    slot_to_alias: dict[int, str] = field(default_factory=dict)
    slot_to_game: dict[int, str] = field(default_factory=dict)
    my_slot: int = -1

    def alias(self, slot: int) -> str:
        if slot == 0:
            return "Server"
        return self.slot_to_alias.get(slot, f"Player #{slot}")

    def game(self, slot: int) -> str:
        return self.slot_to_game.get(slot, ARCHIPELAGO_GAME)


class Names:
    """Resolves item / location / player ids to human-readable strings.

    Item and location ids are scoped to the sender's *game*, so the caller must
    identify the item's source slot before looking up the name.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.games: dict[str, GameNames] = {}
        self.players = Players()

    def load_cached(self, game: str, checksum: str) -> bool:
        path = self._cache_path(game, checksum)
        if not path.is_file():
            return False
        try:
            game_data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        self.games[game] = GameNames.from_game_data(game_data)
        return True

    def store(self, game: str, game_data: dict) -> None:
        self.games[game] = GameNames.from_game_data(game_data)
        checksum = game_data.get("checksum", "")
        if checksum:
            path = self._cache_path(game, checksum)
            try:
                path.write_text(json.dumps(game_data))
            except OSError:
                pass

    def missing_games(self, checksums: dict[str, str]) -> list[str]:
        missing = []
        for game, checksum in checksums.items():
            cached = self.games.get(game)
            if cached and cached.checksum == checksum:
                continue
            if self.load_cached(game, checksum):
                continue
            missing.append(game)
        return missing

    def consume_slot_info(self, slot_info: dict) -> None:
        self.players.slot_to_game = {
            int(slot): info.get("game", ARCHIPELAGO_GAME)
            for slot, info in slot_info.items()
        }
        existing = dict(self.players.slot_to_alias)
        for slot, info in slot_info.items():
            existing.setdefault(int(slot), info.get("name", f"Player #{slot}"))
        self.players.slot_to_alias = existing

    def consume_players(self, players: list[dict]) -> None:
        for p in players:
            self.players.slot_to_alias[int(p["slot"])] = p.get("alias") or p.get(
                "name", f"Player #{p['slot']}"
            )

    def item_name(self, item_id: int, receiver_slot: int) -> str:
        """Item IDs live in the receiver's game namespace."""
        game = self.players.game(receiver_slot)
        name = self.games.get(game, GameNames()).item_id_to_name.get(item_id)
        if name:
            return name
        archi = self.games.get(ARCHIPELAGO_GAME)
        if archi and item_id in archi.item_id_to_name:
            return archi.item_id_to_name[item_id]
        return f"Item #{item_id}"

    def location_name(self, location_id: int, sender_slot: int) -> str:
        """Location IDs live in the sender's (placing) game namespace."""
        game = self.players.game(sender_slot)
        name = self.games.get(game, GameNames()).location_id_to_name.get(location_id)
        if name:
            return name
        archi = self.games.get(ARCHIPELAGO_GAME)
        if archi and location_id in archi.location_id_to_name:
            return archi.location_id_to_name[location_id]
        return f"Location #{location_id}"

    def _cache_path(self, game: str, checksum: str) -> Path:
        safe_game = "".join(c if c.isalnum() or c in "-_." else "_" for c in game)
        return self.cache_dir / f"{safe_game}-{checksum}.json"


def flag_prefix(flags: int) -> str:
    if flags & 0b100:
        return "!"  # trap
    if flags & 0b001:
        return "*"  # progression
    if flags & 0b010:
        return "+"  # useful
    return " "


from .events import HintStatus  # noqa: E402  (late import to avoid cycle w/ dataclasses)


HINT_STATUS_LABELS: dict[HintStatus, str] = {
    HintStatus.UNSPECIFIED: "-",
    HintStatus.NO_PRIORITY: "no priority",
    HintStatus.AVOID: "avoid",
    HintStatus.PRIORITY: "priority",
    HintStatus.FOUND: "found",
}


HINT_STATUS_COLORS: dict[HintStatus, str] = {
    HintStatus.UNSPECIFIED: "white",
    HintStatus.NO_PRIORITY: "slate_blue1",
    HintStatus.AVOID: "salmon1",
    HintStatus.PRIORITY: "plum2",
    HintStatus.FOUND: "green",
}


def hint_status_label(status: HintStatus) -> str:
    return HINT_STATUS_LABELS.get(status, "-")


def hint_status_color(status: HintStatus) -> str:
    return HINT_STATUS_COLORS.get(status, "white")
