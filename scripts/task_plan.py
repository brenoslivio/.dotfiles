"""Daily focus queues keyed by source note, local date and Markdown block ID."""
from datetime import date
import json


ACTIONS = {"planAdd", "planRemove", "planOrder", "planCarry", "planDismiss"}


def read(path):
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {"version": 1, "sources": {}}
    except ValueError as exc:
        raise ValueError("Could not read task-plan.json: invalid JSON.") from exc
    try:
        if data["version"] != 1:
            raise ValueError
        for days in data["sources"].values():
            for day, entry in days.items():
                if date.fromisoformat(day).isoformat() != day:
                    raise ValueError
                for field in ("tasks", "dismissed"):
                    keys = entry[field]
                    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys) or len(set(keys)) != len(keys):
                        raise ValueError
    except (KeyError, AttributeError, ValueError, TypeError) as exc:
        raise ValueError("Unrecognized task-plan.json format.") from exc
    return data


def project(days, day, items):
    tasks = {item["key"]: item for item in items if item["depth"]}
    entry = days.get(day, {})
    planned = [k for k in entry.get("tasks", []) if k in tasks]
    seen = set(planned) | set(entry.get("dismissed", []))
    carry = []
    for earlier in sorted((d for d in days if d < day), reverse=True):
        past = days[earlier]
        seen.update(past["dismissed"])
        carry.extend(k for k in past["tasks"] if k not in seen and k in tasks and not tasks[k]["done"])
        seen.update(past["tasks"])
    return {"tasks": planned, "carry": carry}


def edit(entry, plan, req, items):
    action = req["action"]
    tasks, dismissed = entry["tasks"], entry["dismissed"]
    if action == "planOrder":
        opened = {item["key"] for item in items if item["depth"] and not item["done"]}
        order = [k for k in tasks if k in opened]
        new = req["order"]
        if order != req["before"] or sorted(order) != sorted(new):
            raise ValueError("The plan changed. Review its order and try again.")
        replacement = iter(new)
        tasks[:] = [next(replacement) if k in opened else k for k in tasks]
        return
    if action in ("planCarry", "planDismiss"):
        chosen = set(req["keys"])
        keys = [k for k in plan["carry"] if k in chosen]
    else:
        keys = [req["key"]]
    for key in keys:
        if action in ("planAdd", "planCarry"):
            if key not in tasks:
                tasks.append(key)
            if key in dismissed:
                dismissed.remove(key)
        elif action == "planDismiss" or key in tasks:
            if key in tasks:
                tasks.remove(key)
            if key not in dismissed:
                dismissed.append(key)
