"""Edit individual project and task bullets in the note without rewriting surrounding Markdown."""
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
import re
from uuid import uuid4

from panel_tasks import BLOCK, entries, section_body, task_label

CHECK = re.compile(r"^\[([ xX])\][ \t]+")
ACTIONS = {"project", "add", "rename", "toggle", "move", "delete", "transfer", "reorder"}


def digest(value):
    return sha256(value.encode()).hexdigest()[:24]


@dataclass
class Item:
    index: int
    indent: str
    title: str
    done: bool
    key: str
    parent: str
    project: str
    depth: int
    rev: str
    owned: list = field(default_factory=list)
    children: list = field(default_factory=list)
    tree_rev: str = ""

    def display(self):
        return {k: getattr(self, k) for k in ("key", "parent", "project", "depth", "title", "done", "rev", "tree_rev")}


def tree(lines):
    if not any(re.fullmatch(r"##\s+Tasks\s*", line) for line in lines):
        return []
    section, body = section_body(lines)
    stack, rows = [], []
    bullets = {i: (indent, text) for i, indent, text in entries(lines)}
    names = Counter(text for _, text in bullets.values())
    snapshot = digest(body)
    block_counts = Counter(m[1] for line in lines if (m := BLOCK.search(line)))
    for i in section:
        if i not in bullets:
            if lines[i].strip() and stack:
                depth = len(lines[i].expandtabs()) - len(lines[i].expandtabs().lstrip(" "))
                for ancestor in stack:
                    if depth > len(ancestor.indent.expandtabs()):
                        ancestor.owned.append(i)
            continue
        indent, text = bullets[i]
        while stack and len(stack[-1].indent.expandtabs()) >= len(indent.expandtabs()):
            stack.pop()
        if indent and not stack:
            raise ValueError("An indented task has no project. Add a project bullet above it in Obsidian.")
        match = BLOCK.search(text)
        if match and block_counts[match[1]] != 1:
            raise ValueError(f"The note contains duplicate block ID ^{match[1]}. Give each bullet its own ID in Obsidian.")
        # A legacy row has no durable identity. Never redirect stale edits to an identical sibling.
        parent = stack[-1].key if stack else ""
        key = match[1] if match else ":" + digest(parent + "\n" + text)
        if not match and names[text] > 1:
            key += ":" + snapshot + ":" + str(i - section.start)
        title = task_label(text)
        check = CHECK.match(title) if indent else None
        node = Item(i, indent, title[check.end():] if check else title, bool(check and check[1].lower() == "x"),
                    key, stack[-1].key if stack else "", stack[0].key if stack else key,
                    len(stack), digest(lines[i].rstrip("\r\n")), [i])
        for ancestor in stack:
            ancestor.owned.append(i)
            ancestor.children.append(node)
        stack.append(node)
        rows.append(node)
    for row in rows:
        # Interior blank lines belong with multiline descriptions when a subtree moves.
        row.owned = sorted(set(row.owned) | {i for i in range(row.index, row.owned[-1])
                                             if not lines[i].strip()})
        row.tree_rev = digest("".join(lines[i] for i in row.owned))
    return rows


def target(rows, ref, subtree=False):
    row = next((item for item in rows if item.key == ref["key"]), None)
    if not row:
        raise ValueError(f'“{ref.get("title", "Item")}” moved or changed. Select its current row to retry.')
    if row.rev != ref["rev"] or (subtree and row.tree_rev != ref["tree_rev"]):
        raise ValueError(f'The note now contains “{row.title}” with {len(row.children)} nested items. Review the current row before retrying.')
    return row


def attach(lines, node):
    if not node.key.startswith(":"):
        return node.key
    block = ("task-" if node.depth else "project-") + uuid4().hex[:12]
    line = lines[node.index]
    content = line.rstrip()
    lines[node.index] = content + " ^" + block + line[len(content):]
    return block


def child_indent(parent):
    if parent.children:
        return parent.children[0].indent
    return parent.indent + ("\t" if "\t" in parent.indent else "  ")


def edit(lines, req):
    action = req["action"]
    newline = next(("\r\n" if line.endswith("\r\n") else "\n" for line in lines if line.endswith("\n")), "\n")
    terminated = not lines or lines[-1].endswith(("\n", "\r"))
    if action == "project" and not any(re.fullmatch(r"##\s+Tasks\s*", line) for line in lines):
        if lines and lines[-1].strip():
            lines.append(newline)
        lines.append("## Tasks" + newline)
    rows = tree(lines)
    section, _ = section_body(lines)
    new_key = ""
    if action in {"project", "add"}:
        prefix = "project-" if action == "project" else "task-"
        new_key = prefix + (digest(req["operation"]) if req.get("operation") else uuid4().hex[:12])
        existing = next((r for r in rows if r.key == new_key), None)
        if existing:
            return {"key": existing.key, "parent": existing.parent, "removed": [], "completed": []}
    title = req.get("title", "").strip()
    if action in {"project", "add", "rename"} and (
            not title or "\n" in title or "\r" in title or BLOCK.search(title) or CHECK.match(title)):
        raise ValueError("Enter a single-line title without a leading checkbox or trailing block ID.")
    removed, completed = [], []
    key = parent_key = ""
    if action == "project":
        key = new_key
        lines.insert(section.stop, f"- {title} ^{key}{newline}")
    else:
        row = target(rows, req["target"], action in {"move", "delete", "transfer"})
        if action == "reorder":
            projects = [p for p in rows if not p.depth]
            if [p.key for p in projects] != req["order"]:
                raise ValueError("The project order changed. Drag the project again.")
            dest = target(rows, req["destination"])
            if row.depth or dest.depth or row is dest:
                raise ValueError("Choose a different project.")
            ordered = [p for p in projects if p is not row]
            position = ordered.index(dest) + int(req["after"])
            ordered.insert(position, row)
            # Keep the separators between project slots and all text within each subtree.
            blocks = [lines[p.index:p.owned[-1] + 1] for p in ordered]
            for slot, block in reversed(list(zip(projects, blocks))):
                lines[slot.index:slot.owned[-1] + 1] = block
        elif action == "add":
            parent_key = attach(lines, row)
            key = new_key
            lines.insert(row.owned[-1] + 1, f"{child_indent(row)}- [ ] {title} ^{key}{newline}")
        elif action in {"toggle", "rename"}:
            if action == "toggle" and not row.depth:
                raise ValueError("Select a task to mark complete.")
            key = attach(lines, row)
            line = lines[row.index]
            prefix = re.match(r"^([ \t]*-[ \t]+)", line)[0]
            body = line[len(prefix):]
            mark = CHECK.match(body)
            checkbox = mark[0] if mark else ""
            if action == "toggle":
                checkbox = "[ ] " if row.done else "[x] "
                if not row.done:
                    completed = [key]
            suffix = re.search(r"[ \t]+\^[A-Za-z0-9-]+\s*$", body)[0]
            lines[row.index] = prefix + checkbox + (title if action == "rename" else row.title) + suffix
        elif action in {"move", "transfer", "delete"}:
            relocating = action in {"move", "transfer"}
            owned = row.owned
            nodes = [row, *row.children]
            if relocating:
                if "newProject" in req:
                    edit(lines, {"action": "project", "title": req["newProject"]})
                    dest = tree(lines)[-1]
                else:
                    dest = target(rows, req["destination"])
                if dest.depth or dest.key == row.project:
                    raise ValueError("Choose a different destination project.")
                if (action == "move") != bool(row.depth):
                    raise ValueError("Choose a task to move or a project to transfer.")
                parent_key = attach(lines, dest)
                if action == "move":
                    key = attach(lines, row)
                new_indent = child_indent(dest)
                direct = [n for n in row.children if n.parent == row.key] if action == "transfer" else [row]
                moved = []
                for child in direct:
                    for i in child.owned:
                        line = lines[i]
                        if not line.strip():
                            moved.append(line)
                            continue
                        whitespace = re.match(r"^[ \t]*", line)[0]
                        delta = len(whitespace.expandtabs()) - len(child.indent.expandtabs())
                        relative = whitespace[len(child.indent):] if whitespace.startswith(child.indent) else " " * max(0, delta)
                        moved.append(new_indent + relative + line[len(whitespace):])
                if action == "transfer":
                    # Keep project-level indented descriptions with the receiving project.
                    child_lines = {i for child in direct for i in child.owned}
                    moved = [lines[i] for i in owned[1:] if i not in child_lines] + moved
                insertion = dest.owned[-1] + 1 - sum(i <= dest.owned[-1] for i in owned)
            if not relocating or action == "transfer":
                removed = [n.key for n in (nodes if not relocating else [row]) if not n.key.startswith(":")]
            for i in reversed(owned):
                del lines[i]
            if relocating:
                lines[insertion:insertion] = moved
        else:
            raise ValueError("Unknown project or task action.")
    # An insertion at EOF or a move can relocate the original unterminated line.
    for i, line in enumerate(lines):
        if not line.endswith(("\n", "\r")) and (i < len(lines) - 1 or terminated):
            lines[i] += newline
    if not terminated:
        lines[-1] = lines[-1].rstrip("\r\n")
    if action == "reorder":
        key = [p.key for p in tree(lines) if not p.depth][position]
    return {"key": key, "parent": parent_key, "removed": removed, "completed": completed}
