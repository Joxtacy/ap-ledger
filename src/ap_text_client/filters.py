from __future__ import annotations


def item_ref_from_packet(item: dict | list) -> dict:
    """NetworkItem is sent as either a 4-tuple or object. Normalize to dict."""
    if isinstance(item, list):
        item_id, location_id, player, flags = item
        return {
            "item": item_id,
            "location": location_id,
            "player": player,
            "flags": flags,
        }
    return item


def is_sent_by_me(packet: dict, my_slot: int) -> bool:
    """PrintJSON type=ItemSend originating from my world. Self-sends count
    too — the location is still one I've checked, so the Sent panel should
    reflect it even when the receiver is also me."""
    if packet.get("type") not in ("ItemSend", "ItemCheat"):
        return False
    item = item_ref_from_packet(packet.get("item", {}))
    return item.get("player") == my_slot


def is_hint_for_me(packet: dict, my_slot: int) -> bool:
    if packet.get("type") != "Hint":
        return False
    item = item_ref_from_packet(packet.get("item", {}))
    return item.get("player") == my_slot or packet.get("receiving") == my_slot


def is_self_status(packet: dict, my_slot: int) -> bool:
    """Goal / Release / Collect message referring to me."""
    return (
        packet.get("type") in ("Goal", "Release", "Collect")
        and packet.get("slot") == my_slot
    )
