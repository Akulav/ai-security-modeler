"""Privacy helpers for anything that leaves the database towards the LLM or the web."""
import re

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
IPV4_RE = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}\b")
IPV6_RE = re.compile(r"\b[0-9a-fA-F]{0,4}(:[0-9a-fA-F]{0,4}){2,7}\b")


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    _, domain = email.rsplit("@", 1)
    return f"***@{domain}"


def mask_text(text: str) -> str:
    text = EMAIL_RE.sub(lambda m: mask_email(m.group(0)) or "***", text)
    text = IPV4_RE.sub("[ip]", text)
    return IPV6_RE.sub("[ip]", text)


def graph_for_llm(nodes: list[dict], edges: list[dict]) -> dict:
    """The graph as the LLM sees it: full structure, no full addresses.

    Addresses aren't needed to reason about dependencies, and the model can issue web
    searches, so what it never sees it can't leak. Free text and names are masked too.
    """
    return {
        "nodes": [
            {
                "id": node["id"],
                "type": node["type"],
                "name": mask_text(node["name"]),
                "email_domain": mask_email(node.get("email")),
                "has_ip_address": bool(node.get("ip_address")),
                "security_level": node["security_level"],
                "password_type": node["password_type"],
                "status": node["status"],
                "os": node.get("os"),
                "os_version": mask_text(node.get("os_version") or "") or None,
                "encryption": node.get("encryption"),
                "defenses": node.get("defenses") or [],
                "inside_apps_node": node.get("parent_id"),
                "notes": mask_text(node.get("notes") or ""),
                "breaches": [b.get("name") for b in node.get("breaches") or []],
            }
            for node in nodes
        ],
        "edges": [
            {
                "source": edge["source_id"],
                "target": edge["target_id"],
                "relation": edge["relation"],
                "loss_mode": edge.get("loss_mode"),
            }
            for edge in edges
        ],
    }


def unsafe_search_reason(query: str, secrets: list[str]) -> str | None:
    """Why a model-written web query must not be sent, or None when it's safe.

    `secrets` holds the user's real addresses, as a backstop to pattern matching.
    """
    if EMAIL_RE.search(query):
        return "contains an email address"
    if IPV4_RE.search(query) or IPV6_RE.search(query):
        return "contains an IP address"
    lowered = query.lower()
    if any(secret and secret.lower() in lowered for secret in secrets):
        return "contains personal details from your graph"
    return None
