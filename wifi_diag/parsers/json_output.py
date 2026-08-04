import json


def load_json_object(output):
    """Return the JSON object in output, or None when there is not one.

    Both speed test clients emit a single result object, but either may be
    preceded by a progress or banner line that makes the whole stream invalid
    JSON, so fall back to the last line that parses on its own.
    """
    if not output:
        return None
    data = _loads(output)
    if isinstance(data, dict):
        return data
    for line in reversed(output.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            data = _loads(line)
            if isinstance(data, dict):
                return data
    return None


def _loads(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None
