"""Rules that keep a graph consistent: run at start and after edits or an import. Safe to run repeatedly."""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .catalog import DEFENSE_OPTIONS, FIELD_DEFAULTS, NODE_FIELDS, OS_OPTIONS
from .models import Edge, Node

COMBINED = "stores_credentials_totp"
EMAIL_ACCESS_RELATIONS = ("can_reset_password", "recovery_for", "sso_for")


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

