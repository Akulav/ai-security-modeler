"""Ready-made questions about the map. Each is answered instantly from the graph; the LLM adds advice.

Lists come from here rather than the model, so they're always complete and correct. "Not recorded"
is kept apart from "none": an account with nothing ticked may have 2FA that was never entered.
"""
from ..catalog import ACCOUNTS, COMPUTERS, DEFENSES, NETWORK_GEAR, OPERATING_SYSTEMS, SECOND_FACTORS
from .graph_engine import (DATA_TYPES, FACTOR_DEFENSE, SEVERITY_ORDER, Model, analyze, build_model, compromise_radius,
                           loss_radius)

LEVEL_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
PASSWORD_POINTS = {"passkey": 30, "manager": 30, "passphrase": 30, "memorized": 20, "pin_biometric": 20, "unknown": 10}
FACTOR_POINTS = {"hardware_key": 55, "totp": 40, "push_2fa": 40, "email_2fa": 20, "sms_2fa": 15}
PASSKEY_POINTS = 60
SEVERAL_FACTORS_POINTS = 10
RECOVERY_POINTS = 5
LEGACY_PENALTY = 10
BREACH_PENALTY = 25


def account_rows(model: Model) -> list[dict]:
    """One entry per account, weakest first, with what actually protects it."""
    rows = []
    for node_id, node in model.nodes.items():
        if node["type"] not in ACCOUNTS:
            continue
        ticked = set(node.get("defenses") or [])
        drawn = {FACTOR_DEFENSE[d.relation] for d in model.by_dependent[node_id] if d.relation in FACTOR_DEFENSE}
        factors = (ticked & SECOND_FACTORS) | drawn
        passkey = "passkey" in ticked or node["password_type"] == "passkey"
        recorded = bool(ticked or drawn or node["password_type"] != "unknown")
        score = PASSWORD_POINTS.get(node["password_type"], 0)
        score += max([FACTOR_POINTS[f] for f in factors] + ([PASSKEY_POINTS] if passkey else []) + [0])
        score += SEVERAL_FACTORS_POINTS if len(factors) >= 2 else 0
        score += RECOVERY_POINTS if "recovery_codes" in ticked else 0
        score -= LEGACY_PENALTY if node.get("status") == "legacy" else 0
        score -= BREACH_PENALTY if node.get("breaches") else 0
        rows.append({
            "id": node_id,
            "name": node["name"],
            "level": node["security_level"],
            "status": node.get("status", "active"),
            "password_type": node["password_type"],
            "factors": sorted(factors),
            "factor_labels": ", ".join(DEFENSES[f] for f in sorted(factors)) or "None",
            "passkey": passkey,
            "recorded": recorded,
            "breaches": [b.get("name") for b in node.get("breaches") or []],
            "score": max(0, min(100, score)),
        })
    rows.sort(key=lambda row: (row["score"], LEVEL_ORDER.get(row["level"], 9), row["name"].lower()))
    return rows


def _table(headline: str, columns: list[str], rows: list[tuple[str, list]]) -> dict:
    return {
        "headline": headline,
        "columns": columns,
        "rows": [{"node_id": node_id, "cells": [str(cell) for cell in cells]} for node_id, cells in rows],
    }


def _count(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _recent_breaches(model, accounts, _findings) -> dict:
    hit = [a for a in accounts if a["breaches"]]
    headline = f"{_count(len(hit), 'account')} with recorded HaveIBeenPwned breaches."
    return _table(headline, ["Account", "Recorded breaches"], [(a["id"], [a["name"], ", ".join(a["breaches"])]) for a in hit])


def _least_protected(model, accounts, _findings) -> dict:
    # Worst first among those recorded: an unrecorded account's low score only means it's unknown.
    known = [a for a in accounts if a["recorded"]][:10]
    return _table(
        f"The {len(known)} lowest-scoring accounts out of {len(accounts)}.",
        ["Account", "Score", "Importance", "2FA"],
        [(a["id"], [a["name"], f"{a['score']}/100", a["level"], a["factor_labels"]]) for a in known],
    )


def _no_2fa(model, accounts, _findings) -> dict:
    rows = [a for a in accounts if not a["factors"] and not a["passkey"]]
    known = [a for a in rows if a["recorded"]]
    unknown = [a for a in rows if not a["recorded"]]
    return _table(
        f"{_count(len(known), 'account')} with no 2FA, plus {len(unknown)} with nothing recorded yet.",
        ["Account", "Importance", "State"],
        [(a["id"], [a["name"], a["level"], "No 2FA" if a["recorded"] else "Not recorded"]) for a in [*known, *unknown]],
    )


def _totp_candidates(model, accounts, _findings) -> dict:
    rows = [a for a in accounts if not a["passkey"] and not {"totp", "hardware_key"} & set(a["factors"])]
    return _table(
        f"{_count(len(rows), 'account')} without TOTP, a hardware key or a passkey.",
        ["Account", "Importance", "Has now"],
        [(a["id"], [a["name"], a["level"], a["factor_labels"]]) for a in rows],
    )


def _weak_2fa(model, accounts, _findings) -> dict:
    rows = [a for a in accounts if a["factors"] and set(a["factors"]) <= {"sms_2fa", "email_2fa"} and not a["passkey"]]
    return _table(
        f"{_count(len(rows), 'account')} relying only on SMS or email codes.",
        ["Account", "Importance", "2FA"],
        [(a["id"], [a["name"], a["level"], a["factor_labels"]]) for a in rows],
    )


def _passkey_candidates(model, accounts, _findings) -> dict:
    rows = [a for a in accounts if not a["passkey"] and a["status"] != "legacy"]
    return _table(
        f"{_count(len(rows), 'active account')} without a passkey.",
        ["Account", "Importance"],
        [(a["id"], [a["name"], a["level"]]) for a in rows],
    )


def _weak_passwords(model, accounts, _findings) -> dict:
    gear = [(i, n) for i, n in model.nodes.items() if n["type"] in NETWORK_GEAR and n["password_type"] == "default"]
    rows = [(a["id"], [a["name"], a["level"], a["password_type"]]) for a in accounts if a["password_type"] in ("reused", "none")]
    rows += [(i, [n["name"], n["security_level"], "default"]) for i, n in gear]
    return _table(f"{_count(len(rows), 'node')} with a reused, missing or default password.", ["Node", "Importance", "Password"], rows)


def _delete_list(model, accounts, _findings) -> dict:
    rows = [a for a in accounts if a["status"] == "legacy"]
    return _table(
        f"{_count(len(rows), 'account')} marked legacy.",
        ["Account", "Importance", "Relies on it"],
        [(a["id"], [a["name"], a["level"], len(model.by_provider[a["id"]])]) for a in rows],
    )


def _radius_table(model: Model, radius, headline: str, column: str) -> dict:
    sized = sorted(((len(radius(model, node_id)), node_id) for node_id in model.nodes), reverse=True)
    rows = [(i, [model.nodes[i]["name"], size]) for size, i in sized[:10] if size > 0]
    return _table(headline, ["Node", column], rows)


def _spof(model, _accounts, _findings) -> dict:
    return _radius_table(model, loss_radius, "What takes the most down with it if lost.", "Other nodes lost")


def _takeover(model, _accounts, _findings) -> dict:
    return _radius_table(model, compromise_radius, "What exposes the most if hacked.", "Other nodes exposed")


def _devices(model, _accounts, _findings) -> dict:
    rows = []
    for node_id, node in model.nodes.items():
        if node["type"] not in COMPUTERS:
            continue
        os_name = OPERATING_SYSTEMS.get(node.get("os"), "Not set")
        rows.append((node_id, [
            node["name"], f"{os_name} {node.get('os_version') or ''}".strip(), node.get("encryption", "unknown"), node["password_type"],
        ]))
    return _table(f"{_count(len(rows), 'device')}.", ["Device", "OS", "Encryption", "Lock"], rows)


def _network(model, _accounts, _findings) -> dict:
    rows = [
        (i, [n["name"], n["password_type"], ", ".join(DEFENSES.get(d, d) for d in n.get("defenses") or []) or "None recorded"])
        for i, n in model.nodes.items() if n["type"] in NETWORK_GEAR
    ]
    return _table(f"{_count(len(rows), 'piece')} of network gear.", ["Gear", "Admin password", "Defenses"], rows)


def _backups(model, _accounts, _findings) -> dict:
    rows = []
    for node_id, node in model.nodes.items():
        if node["type"] in DATA_TYPES:
            copies = [d for d in model.by_dependent[node_id] if d.relation in ("stored_on", "backs_up_to", "syncs_to")]
            rows.append((node_id, [node["name"], node["security_level"], len(copies), node.get("encryption", "unknown")]))
    return _table(f"{_count(len(rows), 'data node')}.", ["Data", "Importance", "Copies mapped", "Encryption"], rows)


def _priorities(_model, _accounts, findings) -> dict:
    top = sorted(findings, key=lambda f: SEVERITY_ORDER[f["severity"]])[:10]
    return _table(
        f"The {len(top)} most severe calculated findings.",
        ["Severity", "Finding"],
        [(f["node_ids"][0] if f["node_ids"] else None, [f["severity"], f["title"]]) for f in top],
    )


# id, label, whether web research helps, what the LLM should do with the list, builder.
QUESTIONS = [
    ("priorities", "What should I fix first?", False, "Turn these into an ordered action plan. Explain why the first three come first.", _priorities),
    ("recent_breaches", "Find recent breaches at my services", True, "Search for security incidents at the services in ALL_ACCOUNTS during the last 12 months. Report only incidents your search results support, naming the source. Say plainly if you found none. If a breach is confirmed, say what to do.", _recent_breaches),
    ("least_protected", "Which accounts are least protected?", False, "Explain which of these matter most, weighing score against importance, and the single best upgrade for each of the top five.", _least_protected),
    ("no_2fa", "Which accounts don't use 2FA?", False, "Say which to fix first and how. Remind the user to record the ones marked 'Not recorded', as they may already have 2FA.", _no_2fa),
    ("totp_candidates", "Which don't use TOTP but could?", True, "Check which of these services actually support TOTP. List those that do, and those that don't, naming your source. Say when you couldn't confirm one. Never assume support.", _totp_candidates),
    ("weak_2fa", "Which rely on weak SMS or email 2FA?", True, "Explain the risk for these accounts, and check what stronger factor each service offers.", _weak_2fa),
    ("passkey_candidates", "Which could move to passkeys?", True, "Check which of these services support passkeys. Start with the most important. Say when you couldn't confirm one.", _passkey_candidates),
    ("weak_passwords", "Which passwords are reused or default?", False, "Say which to change first and why. A reused password puts every other site using it at risk.", _weak_passwords),
    ("delete_list", "Which accounts should I delete?", False, "Say which are safe to delete and what to move first, using the number that rely on each.", _delete_list),
    ("spof", "What are my biggest single points of failure?", False, "Explain the top three as real scenarios and how to add redundancy.", _spof),
    ("takeover", "What would hurt most if hacked?", False, "Explain the top three as attack paths and what would break each chain.", _takeover),
    ("devices", "Are my devices up to date and secure?", True, "Check whether each OS version is still supported. Flag anything unencrypted, unlocked or with its OS not set.", _devices),
    ("network", "How can I harden my network?", False, "Give concrete settings to change on this gear, most important first.", _network),
    ("backups", "Are my backups good enough?", False, "Assess these against the 3-2-1 rule, and say what's missing.", _backups),
]
BY_ID = {question[0]: question for question in QUESTIONS}


def question_facts(question_id: str, nodes: list[dict], edges: list[dict]) -> dict:
    model = build_model(nodes, edges)
    accounts = account_rows(model)
    findings = analyze(nodes, edges)["findings"]
    return BY_ID[question_id][4](model, accounts, findings)


def custom_facts(nodes: list[dict], edges: list[dict]) -> dict:
    """A custom question could be about anything, so the model gets a compact summary of everything."""
    model = build_model(nodes, edges)
    return _table(
        "Your map, summarised.",
        ["Node", "Type", "Importance", "Defenses"],
        [
            (i, [n["name"], n["type"], n["security_level"], ",".join(n.get("defenses") or [])])
            for i, n in model.nodes.items()
        ],
    )
