from app.catalog import relation_allowed
from app.seed import seed_payload
from app.services.graph_engine import analyze, build_model, compromise_radius, dependency_cycles, loss_radius


def node(node_id, node_type="online_account", level="medium", password="manager", **extra):
    return {"id": node_id, "type": node_type, "name": node_id, "security_level": level,
            "password_type": password, "status": "active", **extra}


def edge(source, target, relation, loss_mode=None):
    return {"id": f"{source}-{target}-{relation}", "source_id": source, "target_id": target,
            "relation": relation, "loss_mode": loss_mode}


def model(nodes, edges):
    return build_model([node(n) if isinstance(n, str) else n for n in nodes], edges)


def test_loss_cascades_through_stack_and_2fa():
    m = model(["phone", "ios", "authy", "github"], [
        edge("ios", "phone", "installed_on"),
        edge("authy", "ios", "runs_on"),
        edge("authy", "github", "provides_totp"),
    ])
    assert loss_radius(m, "phone") == {"ios", "authy", "github"}
    assert loss_radius(m, "github") == set()


def test_app_on_two_devices_survives_losing_one():
    m = model(["phone", "laptop", "bitwarden"], [
        edge("bitwarden", "phone", "runs_on"),
        edge("bitwarden", "laptop", "runs_on"),
    ])
    assert loss_radius(m, "phone") == set()
    assert loss_radius(m, {"phone", "laptop"}) == {"bitwarden"}


def test_backup_keeps_data_alive_when_primary_is_lost():
    m = model(["laptop", "usb", "docs"], [
        edge("docs", "laptop", "stored_on"),
        edge("docs", "usb", "backs_up_to"),
    ])
    assert loss_radius(m, "laptop") == set()
    assert loss_radius(m, "usb") == set()
    assert loss_radius(m, {"laptop", "usb"}) == {"docs"}


def test_data_with_only_a_backup_edge_has_implied_primary():
    m = model(["usb", "docs"], [edge("docs", "usb", "backs_up_to")])
    assert loss_radius(m, "usb") == set()


def test_alternative_override_removes_2fa_lockout():
    edges = [edge("key", "bank", "provides_hardware_key", "alternative"),
             edge("phone", "bank", "provides_totp", "alternative")]
    m = model(["key", "phone", "bank"], edges)
    assert loss_radius(m, "key") == set()
    assert loss_radius(m, {"key", "phone"}) == {"bank"}


def test_recovery_email_differs_between_loss_and_compromise():
    m = model(["mail", "bank"], [edge("mail", "bank", "can_reset_password")])
    assert loss_radius(m, "mail") == set()
    assert compromise_radius(m, "mail") == {"bank"}


def test_totp_differs_between_loss_and_compromise():
    m = model(["authy", "github"], [edge("authy", "github", "provides_totp")])
    assert loss_radius(m, "authy") == {"github"}
    assert compromise_radius(m, "authy") == set()


def test_compromise_travels_from_host_to_guest_only():
    m = model(["phone", "ios", "app"], [edge("ios", "phone", "installed_on"), edge("app", "ios", "runs_on")])
    assert compromise_radius(m, "phone") == {"ios", "app"}
    assert compromise_radius(m, "app") == set()


def test_cycle_is_detected_and_does_not_fail_on_its_own():
    m = model(["vault", "mail", "other"], [
        edge("vault", "mail", "stores_credentials"),
        edge("mail", "vault", "provides_2fa_email"),
        edge("other", "mail", "provides_totp"),
    ])
    assert [set(c) for c in dependency_cycles(m)] == [{"vault", "mail"}]
    assert loss_radius(m, "other") == {"mail", "vault"}
    assert loss_radius(m, "vault") == {"mail"}


def test_no_cycle_in_a_chain():
    m = model(["a", "b", "c"], [edge("a", "b", "grants_access"), edge("b", "c", "grants_access")])
    assert dependency_cycles(m) == []


def test_none_loss_edges_do_not_form_cycles():
    m = model(["a", "b"], [edge("a", "b", "can_reset_password"), edge("b", "a", "can_reset_password")])
    assert dependency_cycles(m) == []


def kinds(nodes, edges):
    return {f["kind"] for f in analyze(nodes, edges)["findings"]}


def test_hygiene_findings():
    bank = node("bank", "financial_account", "critical", "reused")
    assert {"weak_password", "no_second_factor"} <= kinds([bank], [])


def test_sms_and_single_factor_flagged_on_high_value_account():
    found = kinds([node("phone", "smartphone"), node("bank", "financial_account", "critical")],
                  [edge("phone", "bank", "provides_2fa_sms")])
    assert {"sms_2fa", "single_second_factor"} <= found


def test_breach_finding():
    breached = node("mail", "email_account", breaches=[{"name": "Adobe"}])
    assert "breached_account" in kinds([breached], [])


def test_backups_in_same_location_flagged():
    nodes = [node("docs", "folder"), node("pc", "desktop"), node("usb", "usb_drive"), node("home", "local_network")]
    edges = [edge("docs", "pc", "stored_on"), edge("docs", "usb", "backs_up_to"),
             edge("pc", "home", "located_in"), edge("usb", "home", "located_in")]
    found = kinds(nodes, edges)
    assert "backup_same_location" in found
    assert "no_backup" not in found


def test_excess_redundancy_flagged():
    nodes = [node("docs", "folder"), *[node(f"d{i}", "usb_drive") for i in range(5)]]
    assert "excess_redundancy" in kinds(nodes, [edge("docs", f"d{i}", "backs_up_to") for i in range(5)])


def test_router_loss_reaches_gear_and_takes_devices_offline_without_cascading():
    m = model(["router", "switch", "pc", "app", "github"], [
        edge("switch", "router", "uplink_to"),
        edge("pc", "switch", "connected_via"),
        edge("app", "pc", "runs_on"),
        edge("app", "github", "provides_totp"),
    ])
    assert loss_radius(m, "router") == {"switch", "pc"}
    assert loss_radius(m, "pc") == {"app", "github"}


def test_device_with_two_network_links_stays_online_until_both_go():
    m = model(["wifi", "switch", "pc"], [edge("pc", "wifi", "connected_via"), edge("pc", "switch", "connected_via")])
    assert loss_radius(m, "wifi") == set()
    assert loss_radius(m, {"wifi", "switch"}) == {"pc"}


def test_several_listed_factors_mean_one_lost_provider_is_no_lockout():
    drawn_both = [edge("a", "bank", "provides_totp"), edge("b", "bank", "provides_hardware_key")]
    bank = node("bank", "financial_account", defenses=["totp", "hardware_key"])
    m = build_model([node("a"), node("b"), bank], drawn_both)
    assert loss_radius(m, "a") == set() and loss_radius(m, {"a", "b"}) == {"bank"}

    undrawn = node("bank", "financial_account", defenses=["totp", "sms_2fa"])
    m = build_model([node("a"), undrawn], [edge("a", "bank", "provides_totp")])
    assert loss_radius(m, "a") == set()


def test_one_listed_factor_stays_required_and_explicit_setting_wins():
    bank = node("bank", "financial_account", defenses=["totp"])
    assert loss_radius(build_model([node("a"), bank], [edge("a", "bank", "provides_totp")]), "a") == {"bank"}
    two = node("bank", "financial_account", defenses=["totp", "sms_2fa"])
    forced = [edge("a", "bank", "provides_totp", "required")]
    assert loss_radius(build_model([node("a"), two], forced), "a") == {"bank"}


def test_listed_defenses_feed_the_findings():
    assert "no_second_factor" not in kinds([node("b", "financial_account", "critical", defenses=["passkey"])], [])
    assert "sms_2fa" in kinds([node("b", "financial_account", "critical", defenses=["sms_2fa"])], [])
    assert "gear_defenses_unknown" in kinds([node("r", "router")], [])
    assert "wifi_unprotected" in kinds([node("w", "wifi", defenses=["guest_network"])], [])
    assert "wifi_unprotected" not in kinds([node("w", "wifi", defenses=["wpa3"])], [])
    assert "weak_gear_password" in kinds([node("r", "router", password="default")], [])


def _vault_scenario(bank_defenses=None, extra_nodes=(), extra_edges=()):
    nodes = [node("vault", "password_manager"), node("mail", "email_account"),
             node("bank", "financial_account", "critical", defenses=bank_defenses or []), *extra_nodes]
    edges = [edge("vault", "mail", "stores_credentials"), edge("vault", "bank", "stores_credentials"),
             edge("mail", "bank", "provides_2fa_email"), *extra_edges]
    return [f for f in analyze(nodes, edges)["findings"] if f["kind"] == "dependent_second_factor"]


def test_2fa_through_an_email_in_the_same_vault_is_flagged_once():
    findings = _vault_scenario()
    assert len(findings) == 1
    assert findings[0]["severity"] == "critical" and "bank" in findings[0]["detail"]
    assert set(findings[0]["node_ids"]) == {"vault", "mail", "bank"}


def test_vault_supplying_its_own_totp_is_flagged():
    nodes = [node("vault", "password_manager"), node("site")]
    edges = [edge("vault", "site", "stores_credentials"), edge("vault", "site", "provides_totp")]
    assert "dependent_second_factor" in kinds(nodes, edges)


def test_combined_link_counts_as_password_and_second_factor():
    nodes = [node("vault", "password_manager"), node("site", "online_account", "high")]
    edges = [edge("vault", "site", "stores_credentials_totp")]
    found = kinds(nodes, edges)
    assert "dependent_second_factor" in found and "no_second_factor" not in found
    m = build_model(nodes, edges)
    assert loss_radius(m, "vault") == {"site"} and compromise_radius(m, "vault") == {"site"}


def test_a_factor_outside_the_vault_clears_the_finding():
    assert _vault_scenario(extra_nodes=[node("key", "hardware_key")],
                           extra_edges=[edge("key", "bank", "provides_hardware_key")]) == []
    assert _vault_scenario(bank_defenses=["email_2fa", "hardware_key"]) == []
    assert _vault_scenario(bank_defenses=["email_2fa"]) != []


def test_no_finding_when_the_factor_email_is_not_in_the_vault():
    nodes = [node("vault", "password_manager"), node("mail", "email_account"), node("bank", "financial_account")]
    edges = [edge("vault", "bank", "stores_credentials"), edge("mail", "bank", "provides_2fa_email")]
    assert "dependent_second_factor" not in kinds(nodes, edges)


def test_apps_container_never_appears_in_results():
    nodes = [node("phone", "smartphone"), node("apps", "app_group"), node("authy", "application")]
    edges = [edge("apps", "phone", "installed_on"), edge("authy", "apps", "runs_on")]
    m = build_model(nodes, edges)
    assert "apps" not in m.nodes and loss_radius(m, "phone") == {"authy"}


def test_unencrypted_portable_device_flagged_but_not_a_desktop():
    assert "unencrypted_device" in kinds([node("u", "usb_drive", encryption="none")], [])
    assert "unencrypted_device" not in kinds([node("d", "desktop", encryption="none", os="linux")], [])


def test_sample_graph_passes_the_relationship_rules():
    seed = seed_payload()
    types = {n["id"]: n["type"] for n in seed["nodes"]}
    for e in seed["edges"]:
        assert relation_allowed(e["relation"], types[e["source_id"]], types[e["target_id"]]), e


def test_sample_graph_shows_each_headline_scenario():
    seed = seed_payload()
    nodes = [{"status": "active", "password_type": "unknown", **n} for n in seed["nodes"]]
    edges = [{"id": str(i), **e} for i, e in enumerate(seed["edges"])]
    m = build_model(nodes, edges)
    assert {"proton", "bank", "github"} <= loss_radius(m, "iphone")
    found = kinds(nodes, edges)
    assert {"dependent_second_factor", "single_point_of_failure", "takeover_path", "circular_dependency",
            "backup_same_location", "legacy_account", "no_backup"} <= found
