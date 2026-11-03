"""A fictional sample graph that demonstrates each feature. Addresses use reserved domains."""

NODES = [
    # id, type, name, level, extras. The frontend arranges these after loading.
    ("iphone", "smartphone", "iPhone 15", "high", {"os": "ios", "os_version": "18", "encryption": "encrypted", "password_type": "pin_biometric", "defenses": ["auto_updates", "biometric", "remote_wipe"]}),
    ("iphone_apps", "app_group", "iPhone 15 Apps", "medium", {}),
    ("authy", "application", "Authy", "high", {"parent_id": "iphone_apps", "password_type": "pin_biometric"}),
    ("bitwarden_app", "application", "Bitwarden App", "critical", {"parent_id": "iphone_apps", "password_type": "pin_biometric"}),
    ("vault", "password_manager", "Bitwarden Vault", "critical", {"password_type": "passphrase", "email": "alex@example.com", "defenses": ["password", "email_2fa"]}),
    ("laptop", "laptop", "ThinkPad Laptop", "high", {"os": "linux", "os_version": "Ubuntu 24.04", "encryption": "none", "password_type": "memorized", "ip_address": "192.168.1.20", "defenses": ["firewall"]}),
    ("nas", "nas_server", "Home NAS", "high", {"os": "linux", "ip_address": "192.168.1.30", "encryption": "encrypted", "password_type": "passphrase", "defenses": ["snapshots", "raid"]}),
    ("nas_admin", "local_server_account", "NAS Admin", "high", {"password_type": "reused", "defenses": ["password"]}),
    ("tv", "smart_tv", "Living Room TV", "low", {"os": "android_tv", "ip_address": "192.168.1.40"}),
    ("home_lan", "local_network", "Home Network", "medium", {"ip_address": "192.168.1.0/24"}),
    ("modem", "modem", "ISP Modem", "medium", {"password_type": "default"}),
    ("router", "router", "Home Router", "high", {"ip_address": "192.168.1.1", "password_type": "memorized", "defenses": ["changed_default_password", "firewall", "auto_updates"]}),
    ("wifi", "wifi", "Home WiFi", "high", {"ip_address": "192.168.1.0/24", "password_type": "passphrase", "defenses": ["wpa2", "strong_passphrase"]}),
    ("switch", "switch", "Office Switch", "medium", {}),
    ("usb", "usb_drive", "External USB Drive", "medium", {"encryption": "none"}),
    ("proton", "email_account", "ProtonMail Account", "critical", {"password_type": "manager", "email": "alex@example.net", "defenses": ["password", "totp"]}),
    ("yahoo", "email_account", "Old Yahoo Mail", "low", {"password_type": "reused", "email": "alex.old@example.org", "status": "legacy", "defenses": ["password"]}),
    ("bank", "financial_account", "Bank Account", "critical", {"password_type": "manager", "defenses": ["password", "sms_2fa", "email_2fa"]}),
    ("github", "online_account", "GitHub", "high", {"password_type": "manager", "defenses": ["password", "passkey", "totp"]}),
    ("instagram", "social_account", "Instagram", "low", {"password_type": "reused", "defenses": ["password"]}),
    ("steam", "gaming_account", "Steam", "low", {"password_type": "manager"}),
    ("amazon", "shopping_account", "Amazon", "medium", {"password_type": "manager"}),
    ("gdrive", "cloud_storage", "Google Drive", "high", {"password_type": "manager", "defenses": ["password", "passkey"]}),
    ("documents", "folder", "Important Documents", "critical", {}),
    ("photos", "folder", "Family Photos", "high", {}),
]

EDGES = [
    ("iphone_apps", "iphone", "installed_on"),
    ("authy", "iphone_apps", "runs_on"),
    ("bitwarden_app", "iphone_apps", "runs_on"),
    ("bitwarden_app", "vault", "grants_access"),
    ("vault", "proton", "stores_credentials"),
    ("vault", "bank", "stores_credentials"),
    ("vault", "github", "stores_credentials"),
    ("vault", "gdrive", "stores_credentials"),
    ("vault", "steam", "stores_credentials_totp"),
    ("vault", "amazon", "stores_credentials"),
    ("proton", "vault", "provides_2fa_email"),
    ("proton", "bank", "provides_2fa_email"),
    ("proton", "amazon", "provides_2fa_email"),
    ("proton", "gdrive", "can_reset_password"),
    ("authy", "github", "provides_totp"),
    ("authy", "proton", "provides_totp"),
    ("iphone", "bank", "provides_2fa_sms"),
    ("yahoo", "instagram", "can_reset_password"),
    ("documents", "laptop", "stored_on"),
    ("documents", "usb", "backs_up_to"),
    ("photos", "laptop", "stored_on"),
    ("usb", "home_lan", "located_in"),
    ("laptop", "home_lan", "located_in"),
    ("router", "modem", "uplink_to"),
    ("router", "home_lan", "located_in"),
    ("wifi", "router", "uplink_to"),
    ("switch", "router", "uplink_to"),
    ("laptop", "wifi", "connected_via"),
    ("iphone", "wifi", "connected_via"),
    ("tv", "wifi", "connected_via"),
    ("nas", "switch", "connected_via"),
    ("nas_admin", "nas", "account_on"),
]


def seed_payload() -> dict:
    nodes = [
        {"id": node_id, "type": node_type, "name": name, "security_level": level, **extras}
        for node_id, node_type, name, level, extras in NODES
    ]
    edges = [{"source_id": s, "target_id": t, "relation": r} for s, t, r in EDGES]
    return {"nodes": nodes, "edges": edges}
