import json


def detect_cast_events(prev, curr):
    """Compare two consecutive readings for one device and return events.

    Returns an empty list when there is no previous reading, so an agent
    restart does not emit a burst of false events.
    """
    if prev is None:
        return []

    events = []

    was_reachable = bool(prev.get("reachable"))
    is_reachable = bool(curr.get("reachable"))

    if was_reachable and not is_reachable:
        events.append(_event("offline", {}))
    elif not was_reachable and is_reachable:
        events.append(_event("online", {}))

    # An unreachable device reports no BSSID, which mimics a genuine switch.
    if was_reachable and is_reachable:
        events.extend(_association_events(prev, curr))

    prev_uptime = prev.get("uptime_secs")
    curr_uptime = curr.get("uptime_secs")
    if prev_uptime is not None and curr_uptime is not None and curr_uptime < prev_uptime:
        events.append(
            _event("reboot", {"from_uptime": prev_uptime, "to_uptime": curr_uptime})
        )

    return events


def _association_events(prev, curr):
    prev_bssid = prev.get("bssid")
    curr_bssid = curr.get("bssid")

    # An unknown BSSID is not a distinct value, so it is never a transition.
    if not prev_bssid or not curr_bssid or prev_bssid == curr_bssid:
        return []

    events = [_event("bssid_switch", {"from": prev_bssid, "to": curr_bssid})]

    prev_band = prev.get("band")
    curr_band = curr.get("band")
    # Never claim a band change unless both sides are actually known.
    if prev_band and curr_band and prev_band != curr_band:
        events.append(_event("band_switch", {"from": prev_band, "to": curr_band}))

    return events


def _event(event_type, detail):
    return {"event_type": event_type, "detail": json.dumps(detail)}
