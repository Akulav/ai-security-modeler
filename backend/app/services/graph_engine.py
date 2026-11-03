"""Deterministic graph analysis: blast radius, single points of failure, cycles and hygiene.

This has no LLM in it. Its findings are facts about the graph, shown even when Ollama is
down, and handed to the LLM as ground truth so it explains rather than guesses.
"""
from collections import defaultdict
from dataclasses import dataclass, field

from ..catalog import ACCOUNTS, APP_GROUP, COMPUTERS, NETWORK_GEAR, PORTABLE_DEVICES, RELATIONS, SECOND_FACTORS

CRITICAL_WEIGHT = {"low": 1, "medium": 2, "high": 4, "critical": 8}
HIGH_VALUE_LEVELS = {"high", "critical"}
ACCOUNT_TYPES = ACCOUNTS
DATA_TYPES = {"folder", "database", "backup"}
MAX_REASONABLE_COPIES = 4
FACTOR_DEFENSE = {
    "provides_2fa_email": "email_2fa", "provides_2fa_sms": "sms_2fa",
    "provides_totp": "totp", "provides_hardware_key": "hardware_key", "stores_credentials_totp": "totp",
}


@dataclass(frozen=True)
class Dependency:
    """Normalised edge: `dependent` relies on `provider`, regardless of drawn direction."""
    edge_id: str
    provider: str
    dependent: str
    relation: str
    loss: str
    compromise: bool


@dataclass
class Model:
    nodes: dict[str, dict]
    dependencies: list[Dependency] = field(default_factory=list)
    by_dependent: dict[str, list[Dependency]] = field(default_factory=lambda: defaultdict(list))
    by_provider: dict[str, list[Dependency]] = field(default_factory=lambda: defaultdict(list))


def _second_factors(node: dict) -> set[str]:
    return set(node.get("defenses") or []) & SECOND_FACTORS


def _factor_loss(relation, dependent: dict, edges: list[dict]) -> str | None:
    """When an account has several second factors, any one gets you in, so losing one isn't a lockout.

    If it lists more factors than are drawn as links, the undrawn ones keep it alive even
    when every drawn provider is lost.
    """
    if not relation.id.startswith("provides_"):
        return None
    listed = len(_second_factors(dependent))
    if listed < 2:
        return None
    drawn = sum(1 for e in edges if e["target_id"] == dependent["id"] and e["relation"].startswith("provides_"))
    return "backup" if listed > drawn else "alternative"


def build_model(nodes: list[dict], edges: list[dict]) -> Model:
    # An Apps node is only a container. Its apps depend on the device it sits on, so it's
    # replaced by that device here and never appears in a finding or a blast radius.
    known = {node["id"] for node in nodes}
    groups = {node["id"] for node in nodes if node["type"] == APP_GROUP}
    host = {
        edge["source_id"]: edge["target_id"] for edge in edges
        if edge["source_id"] in groups and edge["target_id"] in known - groups
    }
    model = Model(nodes={node["id"]: node for node in nodes if node["id"] not in groups})
    for edge in edges:
        relation = RELATIONS.get(edge["relation"])
        source, target = host.get(edge["source_id"], edge["source_id"]), host.get(edge["target_id"], edge["target_id"])
        if relation is None or source == target or source not in model.nodes or target not in model.nodes:
            continue
        provider, dependent = (source, target) if relation.provider == "source" else (target, source)
        dependency = Dependency(
            edge_id=edge["id"], provider=provider, dependent=dependent, relation=relation.id,
            loss=edge.get("loss_mode") or _factor_loss(relation, model.nodes[dependent], edges) or relation.loss,
            compromise=relation.compromise,
        )
        model.dependencies.append(dependency)
        model.by_dependent[dependent].append(dependency)
        model.by_provider[provider].append(dependency)
    return model


def _fails(model: Model, node_id: str, failed: set[str]) -> bool:
    dependencies = model.by_dependent[node_id]
    if any(d.loss == "required" and d.provider in failed for d in dependencies):
        return True
    alternatives = [d for d in dependencies if d.loss in ("alternative", "backup")]
    # Only-backup nodes have an implied primary copy that isn't drawn, so they survive.
    if not any(d.loss == "alternative" for d in alternatives):
        return False
    return all(d.provider in failed for d in alternatives)


def loss_radius(model: Model, start: set[str] | str) -> set[str]:
    """Everything that becomes unavailable if `start` is lost, excluding `start` itself.

    Grows a failed set to a fixed point. It starts only from real losses, so a dependency
    cycle can't fail by itself, and it always terminates since the set only grows.
    """
    seeds = {start} if isinstance(start, str) else set(start)
    failed = set(seeds)
    changed = True
    while changed:
        changed = False
        for node_id in model.nodes:
            if node_id not in failed and _fails(model, node_id, failed):
                failed.add(node_id)
                changed = True
    # Added only now, so a device going offline doesn't take down what relies on it.
    offline = set()
    for node_id in model.nodes:
        links = [d for d in model.by_dependent[node_id] if d.loss == "network"]
        if links and all(d.provider in failed for d in links):
            offline.add(node_id)
    return (failed | offline) - seeds


def compromise_radius(model: Model, start: str) -> set[str]:
    """Everything an attacker reaches after taking over `start`, excluding `start` itself."""
    reached = {start}
    frontier = [start]
    while frontier:
        for dependency in model.by_provider[frontier.pop()]:
            if dependency.compromise and dependency.dependent not in reached:
                reached.add(dependency.dependent)
                frontier.append(dependency.dependent)
    return reached - {start}


def dependency_cycles(model: Model) -> list[list[str]]:
    """Strongly connected groups of availability dependencies (iterative Tarjan)."""
    successors: dict[str, list[str]] = defaultdict(list)
    for dependency in model.dependencies:
        if dependency.loss != "none":
            successors[dependency.dependent].append(dependency.provider)

    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[list[str]] = []
    counter = 0

    for root in model.nodes:
        if root in index:
            continue
        work = [(root, iter(successors[root]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node_id, remaining = work[-1]
            for successor in remaining:
                if successor not in index:
                    index[successor] = low[successor] = counter
                    counter += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(successors[successor])))
                    break
                if successor in on_stack:
                    low[node_id] = min(low[node_id], index[successor])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node_id])
                if low[node_id] == index[node_id]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node_id:
                            break
                    if len(component) > 1 or node_id in successors[node_id]:
                        components.append(component)
    return components


def _names(model: Model, ids) -> list[str]:
    return sorted(model.nodes[node_id]["name"] for node_id in ids)


def _join(names: list[str], limit: int = 5) -> str:
    if len(names) > limit:
        return f"{', '.join(names[:limit])} and {len(names) - limit} more"
    return ", ".join(names)


def _impact(model: Model, ids) -> int:
    return sum(CRITICAL_WEIGHT.get(model.nodes[i]["security_level"], 1) for i in ids)


def _severity_for(model: Model, ids) -> str:
    levels = {model.nodes[i]["security_level"] for i in ids}
    if "critical" in levels:
        return "critical"
    if "high" in levels or len(ids) >= 5:
        return "high"
    return "medium"


def _finding(kind: str, section: str, severity: str, title: str, detail: str, nodes: list[str]) -> dict:
    return {"kind": kind, "section": section, "severity": severity, "title": title, "detail": detail, "node_ids": nodes}


def _spof_findings(model: Model) -> list[dict]:
    findings = []
    for node_id, node in model.nodes.items():
        radius = loss_radius(model, node_id)
        if not radius or (len(radius) < 2 and not radius & _high_value(model)):
            continue
        names = _names(model, radius)
        findings.append((_impact(model, radius), _finding(
            "single_point_of_failure", "vulnerabilities", _severity_for(model, radius),
            f"Losing {node['name']} takes down {len(radius)} other node{'s' if len(radius) != 1 else ''}",
            f"If {node['name']} is lost or destroyed, you also lose access to: {_join(names)}.",
            [node_id, *sorted(radius)],
        )))
    findings.sort(key=lambda item: -item[0])
    return [finding for _, finding in findings]


def _high_value(model: Model) -> set[str]:
    return {i for i, n in model.nodes.items() if n["security_level"] in HIGH_VALUE_LEVELS}


def _takeover_findings(model: Model) -> list[dict]:
    findings = []
    for node_id, node in model.nodes.items():
        radius = compromise_radius(model, node_id)
        valuable = radius & _high_value(model)
        if len(radius) < 3 and not valuable:
            continue
        findings.append((_impact(model, radius), _finding(
            "takeover_path", "vulnerabilities", _severity_for(model, radius),
            f"Compromising {node['name']} exposes {len(radius)} other node{'s' if len(radius) != 1 else ''}",
            f"An attacker controlling {node['name']} can reach: {_join(_names(model, radius))}.",
            [node_id, *sorted(radius)],
        )))
    findings.sort(key=lambda item: -item[0])
    return [finding for _, finding in findings]


def _dependent_factor_findings(model: Model) -> list[dict]:
    """Accounts whose password and every second factor fall to one takeover.

    Reported once per password holder, since a vault can affect dozens of accounts.
    """
    affected: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for node_id in model.nodes:
        incoming = model.by_dependent[node_id]
        drawn = [d for d in incoming if d.relation in FACTOR_DEFENSE]
        # A factor that's ticked but not drawn is taken to live outside the vault.
        listed = _second_factors(model.nodes[node_id])
        if not drawn or listed - {FACTOR_DEFENSE[d.relation] for d in drawn}:
            continue
        for holder in {d.provider for d in incoming if d.relation in ("stores_credentials", "stores_credentials_totp")}:
            reached = compromise_radius(model, holder) | {holder}
            if all(d.provider in reached for d in drawn):
                affected[holder].append((node_id, {d.provider for d in drawn}))

    findings = []
    for holder, accounts in affected.items():
        ids = [account for account, _ in accounts]
        factors = sorted({factor for _, providers in accounts for factor in providers} - {holder})
        findings.append(_finding(
            "dependent_second_factor", "vulnerabilities", _severity_for(model, ids),
            f"2FA on {len(ids)} account{'s' if len(ids) != 1 else ''} falls together with {model.nodes[holder]['name']}",
            f"An attacker controlling {model.nodes[holder]['name']} gets the password and the second factor for: "
            f"{_join(_names(model, ids))}. Give these accounts a factor kept outside it, such as a hardware key "
            "or a TOTP app on another device.",
            [holder, *factors, *ids],
        ))
    return findings


def _gear_findings(node_id: str, node: dict, defenses: set[str]) -> list[dict]:
    findings = []

    def add(kind: str, severity: str, title: str, detail: str) -> None:
        findings.append(_finding(kind, "recommendations", severity, f"{node['name']} {title}", detail, [node_id]))

    if node["password_type"] in ("default", "none"):
        add("weak_gear_password", "critical", "has no real password",
            "Factory passwords are public. Anyone on your network could take this over. Set a unique one.")
    if not defenses:
        add("gear_defenses_unknown", "low", "has no defenses recorded",
            "Tick what's turned on in its details, so the analysis can check it.")
        return findings
    # The rest compare against what was ticked, so they only apply once something has been.
    if node["type"] == "wifi" and not defenses & {"wpa2", "wpa3"}:
        add("wifi_unprotected", "high", "has no WPA2 or WPA3",
            "Without them, nearby devices can read this traffic. Use WPA3, or WPA2 if a device can't do WPA3.")
    if "wps_disabled" not in defenses and node["type"] in ("wifi", "router"):
        add("wps_on", "medium", "may have WPS on", "WPS PINs can be brute-forced. Turn it off.")
    if node["type"] == "router" and "remote_admin_disabled" not in defenses:
        add("remote_admin_on", "medium", "may allow remote admin", "Turn it off unless you need to manage it from outside.")
    return findings


def _hygiene_findings(model: Model) -> list[dict]:
    findings = []
    for node_id, node in model.nodes.items():
        is_account = node["type"] in ACCOUNT_TYPES
        high_value = node["security_level"] in HIGH_VALUE_LEVELS
        incoming = model.by_dependent[node_id]

        if node.get("breaches"):
            names = [b.get("name", "unknown") for b in node["breaches"]]
            findings.append(_finding(
                "breached_account", "vulnerabilities", "critical" if high_value else "high",
                f"{node['name']} appears in {len(names)} known breach{'es' if len(names) != 1 else ''}",
                f"Reported breaches: {_join(names)}. Change this password and any place it was reused.",
                [node_id],
            ))
        if is_account and node["password_type"] in ("reused", "none"):
            findings.append(_finding(
                "weak_password", "recommendations", "critical" if high_value else "high",
                f"{node['name']} has a {'reused' if node['password_type'] == 'reused' else 'missing'} password",
                "Use a unique password generated by a password manager, or a passkey where supported.",
                [node_id],
            ))
        defenses = set(node.get("defenses") or [])
        if is_account and high_value and not any(d.relation in FACTOR_DEFENSE for d in incoming) \
                and node["password_type"] != "passkey" and not defenses & (SECOND_FACTORS | {"passkey"}):
            findings.append(_finding(
                "no_second_factor", "recommendations", "high",
                f"{node['name']} has no second factor mapped",
                "This high-value account shows no 2FA link. Add a hardware key or TOTP, then map it here.",
                [node_id],
            ))
        sms = [d for d in incoming if d.relation == "provides_2fa_sms"]
        if (sms or "sms_2fa" in defenses) and high_value:
            findings.append(_finding(
                "sms_2fa", "recommendations", "high",
                f"{node['name']} relies on SMS 2FA",
                "SMS codes can be intercepted through SIM swapping. Upgrade to a hardware key or TOTP.",
                [node_id, *[d.provider for d in sms]],
            ))
        required_factors = [d for d in incoming if d.relation.startswith("provides_") and d.loss == "required"]
        if node["type"] in NETWORK_GEAR:
            findings.extend(_gear_findings(node_id, node, defenses))
        if high_value and len(required_factors) == 1:
            provider = model.nodes[required_factors[0].provider]["name"]
            findings.append(_finding(
                "single_second_factor", "recommendations", "medium",
                f"{node['name']} has only one 2FA path, through {provider}",
                f"Register a second factor, or store recovery codes offline, so losing {provider} isn't a lockout. "
                "Once you have, mark this link as 'alternative'.",
                [node_id, required_factors[0].provider],
            ))
        if node["type"] in PORTABLE_DEVICES and node.get("encryption") == "none":
            findings.append(_finding(
                "unencrypted_device", "recommendations", "critical" if high_value else "high",
                f"{node['name']} isn't encrypted",
                "This can be lost or stolen, and anyone holding it could read everything on it. Turn on full-disk encryption.",
                [node_id],
            ))
        if node["type"] in COMPUTERS and node["password_type"] == "none":
            findings.append(_finding(
                "no_device_lock", "recommendations", "high",
                f"{node['name']} has no device lock",
                "Anyone with physical access can use it, and every app and session on it. Set a PIN or passphrase.",
                [node_id],
            ))
        if node["type"] in COMPUTERS and not node.get("os"):
            findings.append(_finding(
                "os_not_set", "recommendations", "low",
                f"{node['name']} has no operating system set",
                "Set its OS and version so the analysis can check whether it's still supported.",
                [node_id],
            ))
        if node.get("status") == "legacy" and is_account:
            findings.append(_finding(
                "legacy_account", "recommendations", "medium",
                f"{node['name']} is marked legacy",
                "Unused accounts still get breached. Move anything still tied to it, then delete the account.",
                [node_id],
            ))
    return findings


def _location_of(model: Model, node_id: str) -> str | None:
    for dependency in model.by_dependent[node_id]:
        if dependency.relation == "located_in":
            return dependency.provider
    return None


def _data_findings(model: Model) -> list[dict]:
    findings = []
    for node_id, node in model.nodes.items():
        if node["type"] not in DATA_TYPES:
            continue
        copies = [d for d in model.by_dependent[node_id] if d.relation in ("stored_on", "backs_up_to", "syncs_to")]
        backups = [d for d in copies if d.relation != "stored_on"]
        if not backups and node["type"] != "backup":
            findings.append(_finding(
                "no_backup", "recommendations", _severity_for(model, [node_id]),
                f"{node['name']} has no backup mapped",
                "Add at least one backup, ideally offsite (the 3-2-1 rule).",
                [node_id],
            ))
        if len(copies) >= 2:
            locations = {_location_of(model, d.provider) for d in copies}
            if len(locations) == 1 and None not in locations:
                location = model.nodes[next(iter(locations))]["name"]
                findings.append(_finding(
                    "backup_same_location", "topology", "high",
                    f"All copies of {node['name']} are in {location}",
                    "A fire, theft or ransomware event there destroys every copy. Move one copy elsewhere.",
                    [node_id, *[d.provider for d in copies]],
                ))
        if len(copies) > MAX_REASONABLE_COPIES:
            findings.append(_finding(
                "excess_redundancy", "topology", "low",
                f"{node['name']} has {len(copies)} copies",
                "Every copy is one more place to secure. Three well-separated copies are usually enough.",
                [node_id, *[d.provider for d in copies]],
            ))
    return findings


def _topology_findings(model: Model) -> list[dict]:
    findings = []
    for component in dependency_cycles(model):
        names = _names(model, component)
        findings.append(_finding(
            "circular_dependency", "topology", _severity_for(model, component),
            f"Circular dependency between {_join(names)}",
            "These nodes rely on each other, so if they're all locked at once none can restore the rest. "
            "Keep an offline way in, such as printed recovery codes, to break the loop.",
            component,
        ))
    connected = {d.provider for d in model.dependencies} | {d.dependent for d in model.dependencies}
    orphans = [i for i in model.nodes if i not in connected]
    if orphans and len(model.nodes) > 1:
        findings.append(_finding(
            "unconnected_nodes", "topology", "low",
            f"{len(orphans)} node{'s are' if len(orphans) != 1 else ' is'} not connected",
            f"The analysis can't reason about: {_join(_names(model, orphans))}. Map their dependencies.",
            orphans,
        ))
    return findings


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def analyze(nodes: list[dict], edges: list[dict]) -> dict:
    model = build_model(nodes, edges)
    findings = [
        *_spof_findings(model), *_takeover_findings(model), *_dependent_factor_findings(model), *_hygiene_findings(model),
        *_data_findings(model), *_topology_findings(model),
    ]
    findings.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])
    return {
        "findings": findings,
        "summary": {
            "nodes": len(nodes), "edges": len(edges),
            "critical": sum(f["severity"] == "critical" for f in findings),
            "high": sum(f["severity"] == "high" for f in findings),
        },
    }


def blast_radius(nodes: list[dict], edges: list[dict], node_id: str) -> dict:
    model = build_model(nodes, edges)
    return {
        "node_id": node_id,
        "loss": sorted(loss_radius(model, node_id)),
        "compromise": sorted(compromise_radius(model, node_id)),
        "depends_on": sorted({d.provider for d in model.by_dependent[node_id]}),
        "dependents": sorted({d.dependent for d in model.by_provider[node_id]}),
    }
