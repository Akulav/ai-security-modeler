"""Brings graphs made by earlier versions up to date. Everything here is safe to run repeatedly."""
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from .catalog import COMPUTERS, DEFENSE_OPTIONS, FIELD_DEFAULTS, LEGACY_OS_TYPE, NODE_FIELDS, OPERATING_SYSTEMS, OS_OPTIONS
from .models import Edge, Node

COMBINED = "stores_credentials_totp"
EMAIL_ACCESS_RELATIONS = ("can_reset_password", "recovery_for", "sso_for")
NEW_NODE_COLUMNS = {
    "os": "VARCHAR(20)",
    "os_version": "VARCHAR(64)",
    "encryption": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
    "defenses": "JSON",
    "parent_id": "VARCHAR(32) REFERENCES nodes(id) ON DELETE CASCADE",
}
_OS_NAME_HINTS = {
    "windows": "windows", "ubuntu": "linux", "debian": "linux", "fedora": "linux", "arch": "linux",
    "mint": "linux", "linux": "linux", "macos": "macos", "mac os": "macos", "ipados": "ipados",
    "ios": "ios", "android": "android", "chrome": "chromeos",
}


def add_missing_columns(engine) -> None:
    existing = {column["name"] for column in inspect(engine).get_columns("nodes")}
    missing = {name: definition for name, definition in NEW_NODE_COLUMNS.items() if name not in existing}
    if not missing:
        return
    # This is the user's only copy of their map, so keep the old version before changing it.
    database = engine.url.database
    if database and Path(database).exists():
        # Timestamped, so a later upgrade can't overwrite an earlier backup.
        shutil.copy2(database, f"{database}.before-upgrade-{datetime.now():%Y%m%d-%H%M%S}.bak")
    with engine.begin() as connection:
        for name, definition in missing.items():
            connection.execute(text(f"ALTER TABLE nodes ADD COLUMN {name} {definition}"))


def apply_type_rules(node: Node) -> None:
    """Blanks fields the node's type doesn't have, so a USB drive can't hold an IP address."""
    fields = NODE_FIELDS.get(node.type, [])
    for field, default in FIELD_DEFAULTS.items():
        if field not in fields:
            setattr(node, field, default)
    if node.os and node.os not in OS_OPTIONS.get(node.type, []):
        node.os = None
    options = DEFENSE_OPTIONS.get(node.type, [])
    node.defenses = [defense for defense in node.defenses or [] if defense in options]


def apply_type_rules_to_all(db: Session) -> None:
    for node in db.scalars(select(Node)):
        apply_type_rules(node)
    db.commit()


def merge_password_totp_edges(db: Session) -> None:
    """Replaces a "stores credentials" and a "provides TOTP" link on the same pair with one link."""
    parts = ("stores_credentials", "provides_totp", COMBINED)
    pairs: dict[tuple[str, str], list[Edge]] = defaultdict(list)
    for edge in db.scalars(select(Edge).where(Edge.relation.in_(parts))):
        pairs[(edge.source_id, edge.target_id)].append(edge)
    for edges in pairs.values():
        relations = {edge.relation for edge in edges}
        if COMBINED not in relations and len(relations) < 2:
            continue
        # Settings on the existing combined link, then on the password link, take priority.
        edges.sort(key=lambda edge: parts.index(edge.relation), reverse=True)
        keep, *others = edges
        keep.relation = COMBINED
        keep.loss_mode = next((edge.loss_mode for edge in edges if edge.loss_mode), None)
        keep.notes = "\n".join(edge.notes for edge in edges if edge.notes)
        for edge in others:
            db.delete(edge)
    db.commit()


def link_email_to_accounts(db: Session, node: Node) -> None:
    """Connects an email node to accounts registered with its address, from either side.

    Password managers are left out: their email can't reset a master password, so a link would
    report a takeover path that doesn't exist. Two nodes for one mailbox aren't linked either.
    """
    if not node.email:
        return
    matches = [
        other for other in db.scalars(select(Node).where(func.lower(Node.email) == node.email.lower()))
        if other.id != node.id
    ]
    if node.type == "email_account":
        pairs = [(node, other) for other in matches if other.type != "email_account"]
    else:
        pairs = [(other, node) for other in matches if other.type == "email_account"]
    for mailbox, account in pairs:
        if account.type == "password_manager":
            continue
        linked = db.scalar(select(Edge).where(
            Edge.source_id == mailbox.id, Edge.target_id == account.id, Edge.relation.in_(EMAIL_ACCESS_RELATIONS),
        ))
        if not linked:
            db.add(Edge(source_id=mailbox.id, target_id=account.id, relation="can_reset_password"))
    db.commit()


def _guess_os(name: str, device_type: str) -> str:
    lowered = name.lower()
    for hint, os_id in _OS_NAME_HINTS.items():
        if hint in lowered and os_id in OS_OPTIONS[device_type]:
            return os_id
    return "other"


def fold_os_nodes(db: Session) -> None:
    """Turns each old OS node on a device into that device's OS field.

    Whatever ran on the OS now runs on the device, so nothing about the dependencies is lost.
    An OS node with no device has nowhere to go, and stays for the user to deal with.
    """
    nodes = {node.id: node for node in db.scalars(select(Node))}
    edges = list(db.scalars(select(Edge)))
    for node in [n for n in nodes.values() if n.type == LEGACY_OS_TYPE]:
        device = next(
            (nodes[e.target_id] for e in edges
             if e.source_id == node.id and nodes[e.target_id].type in COMPUTERS),
            None,
        )
        if device is None:
            continue
        if not device.os:
            device.os = _guess_os(node.name, device.type)
            label = OPERATING_SYSTEMS[device.os]
            # The card shows "OS version", so "Windows 11" keeps only the "11".
            version = node.name[len(label):] if node.name.lower().startswith(label.lower()) else node.name
            device.os_version = version.strip()[:64] or None
        for edge in edges:
            if edge.source_id == device.id or edge.target_id == device.id:
                if node.id in (edge.source_id, edge.target_id):
                    db.delete(edge)
                continue
            if edge.source_id == node.id:
                edge.source_id = device.id
            if edge.target_id == node.id:
                edge.target_id = device.id
        db.flush()
        db.delete(node)
    db.commit()
