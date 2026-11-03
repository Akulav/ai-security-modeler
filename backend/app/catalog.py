"""The vocabulary of the model: node types, their fields, relationships and failure semantics.

Every relationship answers three questions, which drive all blast-radius maths:

provider    Which end does the other rely on? "source" means the target relies on the
            source ("Authy provides TOTP for GitHub"); "target" means the source relies
            on the target ("Bitwarden runs on iPhone").
loss        What happens to the dependent when the provider is LOST?
              required    - the dependent fails.
              alternative - the dependent fails only when all its alternatives have failed
                            (an app on two devices, data with several copies).
              backup      - an alternative that is a copy. On its own it can't cause a
                            failure, because a primary copy is implied.
              network     - the dependent goes offline once all its network links are lost, but
                            nothing relying on it fails as a result: a laptop off WiFi still
                            runs its authenticator app.
              none        - no effect on availability.
compromise  Does an attacker controlling the provider also gain the dependent?

Loss and compromise differ on purpose. A TOTP app lost locks you out, but a stolen TOTP
seed alone doesn't log anyone in. A recovery email lost is harmless, but a recovery email
hijacked hands over the account.

Each relationship also states which node types it makes sense between, so nonsense such as
"USB drive provides SMS 2FA" can't be drawn.
"""
from dataclasses import asdict, dataclass

APP_GROUP = "app_group"
# Replaced by the OS field on devices. Still accepted so older files can be imported and upgraded.
LEGACY_OS_TYPE = "os"

NODE_CATEGORIES: dict[str, dict] = {
    "hardware": {"label": "Hardware", "types": {
        "desktop": "Desktop PC", "laptop": "Laptop", "tablet": "iPad / Tablet",
        "smartphone": "Smartphone", "smart_tv": "Smart TV", "usb_drive": "USB Drive", "nas_server": "NAS / Server",
        "hardware_key": "Hardware Security Key",
    }},
    "network": {"label": "Network", "types": {
        "modem": "Modem / ISP", "router": "Router", "firewall": "Firewall", "switch": "Switch", "wifi": "WiFi Network",
    }},
    "location": {"label": "Locations", "types": {
        "cloud": "Cloud Infrastructure", "local_network": "Local Network", "offsite": "Offsite",
    }},
    "software": {"label": "Software", "types": {
        "application": "Application", APP_GROUP: "Apps",
    }},
    "identity": {"label": "Digital Identity", "types": {
        "password_manager": "Password Manager",
        "email_account": "Email Account", "financial_account": "Financial Account",
        "social_account": "Social Media", "cloud_storage": "Cloud Storage",
        "infrastructure_account": "Infrastructure Account",
        "entertainment_account": "Entertainment Account",
        "local_server_account": "Local Server Account", "work_account": "Work Account",
        "vpn_account": "VPN Account", "gaming_account": "Gaming Account",
        "shopping_account": "Shopping Account", "government_account": "Government Account",
        "online_account": "Other Online Account",
    }},
    "data": {"label": "Data", "types": {
        "folder": "Important Folder", "database": "Database", "backup": "Backup File",
    }},
}

NODE_TYPES: dict[str, str] = {
    type_id: category_id
    for category_id, category in NODE_CATEGORIES.items()
    for type_id in category["types"]
}
ACCEPTED_NODE_TYPES = {*NODE_TYPES, LEGACY_OS_TYPE}

COMPUTERS = {"desktop", "laptop", "tablet", "smartphone", "nas_server", "smart_tv"}
NETWORK_GEAR = {t for t, c in NODE_TYPES.items() if c == "network"}
STORAGE_DEVICES = {"usb_drive", "nas_server", "desktop", "laptop"}
PORTABLE_DEVICES = {"laptop", "tablet", "smartphone", "usb_drive"}
HARDWARE = {t for t, c in NODE_TYPES.items() if c == "hardware"}
LOCATIONS = {t for t, c in NODE_TYPES.items() if c == "location"}
ACCOUNTS = {t for t, c in NODE_TYPES.items() if c == "identity"}
DATA = {t for t, c in NODE_TYPES.items() if c == "data"}
# Things you log in to, and so can protect with a factor.
LOGINS = ACCOUNTS | {"application"}
ANY = set(NODE_TYPES) - {APP_GROUP}

# Which optional fields each type has. Name, security level and notes apply to everything.
_DEVICE_FIELDS = ["ip_address", "os", "os_version", "encryption", "password_type", "status"]
NODE_FIELDS: dict[str, list[str]] = {
    **{t: _DEVICE_FIELDS for t in COMPUTERS},
    "smart_tv": ["ip_address", "os", "os_version", "password_type", "status"],
    **{t: ["ip_address", "password_type", "status"] for t in NETWORK_GEAR},
    "wifi": ["ip_address", "password_type", "status"],
    "usb_drive": ["encryption", "status"],
    "hardware_key": ["status"],
    "local_network": ["ip_address"],
    "cloud": [],
    "offsite": [],
    "application": ["password_type", "status"],
    APP_GROUP: [],
    **{t: ["email", "password_type", "status"] for t in ACCOUNTS},
    "local_server_account": ["password_type", "status"],
    **{t: ["encryption"] for t in DATA},
    LEGACY_OS_TYPE: [],
}
FIELD_DEFAULTS = {
    "ip_address": None, "email": None, "os": None, "os_version": None,
    "encryption": "unknown", "password_type": "unknown", "status": "active",
}
IP_LABELS = {"local_network": "Subnet", "wifi": "Subnet", "modem": "Public or LAN IP"}

DEFENSES = {
    "password": "Password", "passkey": "Passkey", "totp": "TOTP", "sms_2fa": "SMS 2FA", "email_2fa": "Email 2FA",
    "hardware_key": "Hardware key", "push_2fa": "Push 2FA", "biometric": "Biometric",
    "recovery_codes": "Recovery codes", "sso": "SSO",
    "firewall": "Firewall", "antivirus": "Antivirus / EDR", "auto_updates": "Auto updates", "secure_boot": "Secure boot",
    "remote_wipe": "Remote wipe", "vpn": "VPN", "snapshots": "Snapshots", "raid": "RAID",
    "isolated_network": "Isolated network", "mic_disabled": "Mic / camera off", "tracking_off": "Tracking off",
    "changed_default_password": "Default password changed", "wps_disabled": "WPS off", "upnp_disabled": "UPnP off",
    "remote_admin_disabled": "Remote admin off", "dns_filtering": "DNS filtering", "guest_network": "Guest network",
    "vlans": "VLANs", "port_security": "Port security", "mac_filtering": "MAC filtering", "wpa3": "WPA3", "wpa2": "WPA2",
    "strong_passphrase": "Strong passphrase", "hidden_ssid": "Hidden SSID", "ids_ips": "IDS / IPS",
    "geo_blocking": "Geo blocking", "logging": "Logging", "bridge_mode": "Bridge mode",
}
# Any one of these is enough to pass the second login step, so registering several adds redundancy.
SECOND_FACTORS = {"totp", "sms_2fa", "email_2fa", "hardware_key", "push_2fa"}
_LOGIN_DEFENSES = ["password", "passkey", "totp", "sms_2fa", "email_2fa", "hardware_key", "push_2fa", "biometric", "recovery_codes", "sso"]
_COMPUTER_DEFENSES = ["firewall", "antivirus", "auto_updates", "secure_boot", "remote_wipe", "vpn", "biometric"]
DEFENSE_OPTIONS: dict[str, list[str]] = {
    **{t: _LOGIN_DEFENSES for t in ACCOUNTS},
    "application": _LOGIN_DEFENSES,
    **{t: _COMPUTER_DEFENSES for t in COMPUTERS},
    "nas_server": ["firewall", "antivirus", "auto_updates", "secure_boot", "vpn", "snapshots", "raid"],
    "smart_tv": ["auto_updates", "isolated_network", "mic_disabled", "tracking_off"],
    "modem": ["changed_default_password", "bridge_mode", "auto_updates"],
    "router": ["changed_default_password", "firewall", "auto_updates", "wps_disabled", "upnp_disabled",
               "remote_admin_disabled", "dns_filtering", "guest_network", "vlans", "vpn"],
    "firewall": ["changed_default_password", "auto_updates", "ids_ips", "geo_blocking", "logging", "vlans", "vpn"],
    "switch": ["changed_default_password", "auto_updates", "vlans", "port_security", "mac_filtering"],
    "wifi": ["wpa3", "wpa2", "strong_passphrase", "wps_disabled", "guest_network", "vlans", "mac_filtering", "hidden_ssid"],
}

OPERATING_SYSTEMS = {
    "windows": "Windows", "linux": "Linux", "macos": "macOS", "chromeos": "ChromeOS",
    "ios": "iOS", "ipados": "iPadOS", "android": "Android",
    "android_tv": "Android TV", "tvos": "tvOS", "webos": "webOS", "tizen": "Tizen", "other": "Other",
}
OS_OPTIONS: dict[str, list[str]] = {
    "desktop": ["windows", "linux", "macos", "chromeos", "other"],
    "laptop": ["windows", "linux", "macos", "chromeos", "other"],
    "tablet": ["ipados", "android", "windows", "other"],
    "smartphone": ["ios", "android", "other"],
    "nas_server": ["linux", "windows", "other"],
    "smart_tv": ["android_tv", "tvos", "webos", "tizen", "other"],
}

SECURITY_LEVELS = ["low", "medium", "high", "critical"]
DEFAULT_LEVELS: dict[str, str] = {
    "password_manager": "critical", "financial_account": "critical", "email_account": "high", "cloud_storage": "high",
    "hardware_key": "high", "smartphone": "high", "laptop": "high", "desktop": "high",
    "tablet": "high", "nas_server": "high", "folder": "high", "database": "high",
    "router": "high", "firewall": "high", "wifi": "high", "local_server_account": "high", "work_account": "high",
    "government_account": "high", "infrastructure_account": "high", "smart_tv": "low", "gaming_account": "low", "entertainment_account": "low", "shopping_account": "low",
}
PASSWORD_TYPES = {
    "unknown": "Unknown",
    "none": "No password",
    "default": "Factory default",
    "reused": "Reused password",
    "memorized": "Memorized unique",
    "manager": "Password manager generated",
    "passphrase": "Long passphrase",
    "passkey": "Passkey",
    "pin_biometric": "PIN / biometric",
}
_ACCOUNT_PASSWORDS = ["unknown", "reused", "memorized", "manager", "passphrase", "passkey", "none"]
_DEVICE_LOCKS = ["unknown", "pin_biometric", "memorized", "passphrase", "none"]
PASSWORD_OPTIONS: dict[str, list[str]] = {
    **{t: _ACCOUNT_PASSWORDS for t in ACCOUNTS},
    # A vault can't have its own master password generated by a password manager.
    "password_manager": ["unknown", "passphrase", "memorized", "passkey", "reused", "none"],
    **{t: _DEVICE_LOCKS for t in COMPUTERS},
    "application": _DEVICE_LOCKS,
    **{t: ["unknown", "default", "memorized", "manager", "passphrase", "reused", "none"] for t in NETWORK_GEAR},
}
PASSWORD_LABELS = {
    **{t: "Device lock" for t in COMPUTERS},
    "application": "App lock",
    "password_manager": "Master password",
    **{t: "Admin password" for t in NETWORK_GEAR},
    "wifi": "WiFi password",
}
ENCRYPTION_TYPES = {"unknown": "Unknown", "none": "Not encrypted", "encrypted": "Encrypted"}
NODE_STATUSES = ["active", "legacy"]
LOSS_MODES = ["required", "alternative", "backup", "network", "none"]


@dataclass(frozen=True)
class Relation:
    id: str
    label: str
    category: str
    provider: str
    loss: str
    compromise: bool
    sources: frozenset[str]
    targets: frozenset[str]


def _relation(id, label, category, provider, loss, compromise, sources, targets) -> Relation:
    return Relation(id, label, category, provider, loss, compromise, frozenset(sources), frozenset(targets))


_COPY_TARGETS = STORAGE_DEVICES | {"cloud_storage", "cloud", "offsite", "backup"}
_RELATIONS = [
    _relation("provides_2fa_email", "provides 2FA via email for", "auth", "source", "required", False, {"email_account"}, LOGINS),
    _relation("provides_2fa_sms", "provides 2FA via SMS for", "auth", "source", "required", False, {"smartphone", "tablet"}, LOGINS),
    _relation("provides_totp", "provides TOTP for", "auth", "source", "required", False, {"application", "hardware_key", "password_manager"}, LOGINS),
    _relation("provides_hardware_key", "provides hardware key for", "auth", "source", "required", False, {"hardware_key"}, LOGINS | COMPUTERS),
    _relation("can_reset_password", "can reset password of", "auth", "source", "none", True, ACCOUNTS, LOGINS),
    _relation("recovery_for", "is recovery method for", "auth", "source", "none", True, ACCOUNTS | COMPUTERS | DATA | {"application", "hardware_key", "usb_drive"}, LOGINS | COMPUTERS),
    _relation("stores_credentials", "stores credentials for", "auth", "source", "required", True, {"application", "cloud_storage", "password_manager"} | DATA, LOGINS | COMPUTERS),
    # One link rather than two, since a password manager holding both is the common case.
    _relation("stores_credentials_totp", "stores password + TOTP for", "auth", "source", "required", True, {"application", "password_manager"}, LOGINS),
    _relation("sso_for", "signs in via SSO to", "auth", "source", "required", True, ACCOUNTS, LOGINS),
    _relation("grants_access", "grants access to", "auth", "source", "required", True, ANY, ANY),
    _relation("runs_on", "runs on", "stack", "target", "alternative", True, {"application", "password_manager"}, COMPUTERS | {"cloud", APP_GROUP}),
    _relation("installed_on", "installed on", "stack", "target", "alternative", True, {"application", APP_GROUP}, COMPUTERS | {APP_GROUP}),
    _relation("hosted_in", "hosted in", "stack", "target", "alternative", True, ACCOUNTS | DATA | {"application", "nas_server"}, {"cloud", "offsite"}),
    _relation("account_on", "is an account on", "stack", "target", "required", True, {"local_server_account"}, COMPUTERS | NETWORK_GEAR),
    _relation("located_in", "located in", "stack", "target", "required", False, HARDWARE | NETWORK_GEAR, LOCATIONS),
    _relation("connected_via", "connects through", "network", "target", "network", False, COMPUTERS, NETWORK_GEAR),
    _relation("uplink_to", "uplinks to", "network", "target", "alternative", True, NETWORK_GEAR, NETWORK_GEAR),
    _relation("stored_on", "stored on", "data", "target", "alternative", True, DATA, STORAGE_DEVICES | COMPUTERS | {"cloud_storage", "cloud"}),
    _relation("backs_up_to", "backs up to", "data", "target", "backup", True, DATA | COMPUTERS | {"cloud_storage", "email_account", "password_manager"}, _COPY_TARGETS),
    _relation("syncs_to", "syncs to", "data", "target", "backup", True, DATA | COMPUTERS, _COPY_TARGETS),
    _relation("depends_on", "depends on", "other", "target", "required", False, ANY, ANY),
    _relation("connects_to", "connects to", "other", "target", "none", False, ANY, ANY),
]

RELATIONS: dict[str, Relation] = {relation.id: relation for relation in _RELATIONS}


def relation_allowed(relation_id: str, source_type: str, target_type: str) -> bool:
    relation = RELATIONS[relation_id]
    return source_type in relation.sources and target_type in relation.targets


# Offered first in the edge picker, keyed by the type of the node dragged from.
_SUGGESTED_BY_CATEGORY: dict[str, list[str]] = {
    "identity": ["stores_credentials", "stores_credentials_totp", "provides_2fa_email", "can_reset_password", "recovery_for", "sso_for"],
    "hardware": ["connected_via", "provides_2fa_sms", "provides_hardware_key", "located_in", "backs_up_to"],
    "network": ["uplink_to", "located_in"],
    "software": ["runs_on", "provides_totp", "stores_credentials", "stores_credentials_totp"],
    "data": ["stored_on", "backs_up_to", "syncs_to"],
    "location": [],
}


def _new(label: str, type_id: str, relation: str, new_is: str) -> dict:
    """A menu entry for dragging from a node into empty canvas. `new_is` is the new node's end."""
    return {"label": label, "type": type_id, "relation": relation, "new_is": new_is}


_LOCATED = [
    _new("Located in: Local Network", "local_network", "located_in", "target"),
    _new("Located in: Offsite", "offsite", "located_in", "target"),
]
_COMPUTER_MENU = [
    _new("Apps", APP_GROUP, "installed_on", "source"),
    _new("Folder stored here", "folder", "stored_on", "source"),
    _new("Database stored here", "database", "stored_on", "source"),
    _new("Backs up to USB drive", "usb_drive", "backs_up_to", "target"),
    _new("Backs up to cloud storage", "cloud_storage", "backs_up_to", "target"),
    _new("Local account on it", "local_server_account", "account_on", "source"),
    _new("Connects through: WiFi", "wifi", "connected_via", "target"),
    _new("Connects through: switch", "switch", "connected_via", "target"),
    _new("Connects through: router", "router", "connected_via", "target"),
    *_LOCATED,
]
_GEAR_MENU = [
    _new("Uplinks to: router", "router", "uplink_to", "target"),
    _new("Connected: switch", "switch", "uplink_to", "source"),
    _new("Connected: WiFi network", "wifi", "uplink_to", "source"),
    _new("Connected: desktop PC", "desktop", "connected_via", "source"),
    _new("Connected: laptop", "laptop", "connected_via", "source"),
    _new("Connected: smartphone", "smartphone", "connected_via", "source"),
    _new("Connected: smart TV", "smart_tv", "connected_via", "source"),
    _new("Connected: NAS / server", "nas_server", "connected_via", "source"),
    _new("Admin account on it", "local_server_account", "account_on", "source"),
]
_ACCOUNT_MENU = [
    _new("Can reset: online account", "online_account", "can_reset_password", "target"),
    _new("Can reset: financial account", "financial_account", "can_reset_password", "target"),
    _new("Can reset: social media", "social_account", "can_reset_password", "target"),
    _new("Signs in to: online account", "online_account", "sso_for", "target"),
]
_DATA_MENU = [
    _new("Stored on: NAS / server", "nas_server", "stored_on", "target"),
    _new("Stored on: cloud storage", "cloud_storage", "stored_on", "target"),
    _new("Backs up to USB drive", "usb_drive", "backs_up_to", "target"),
    _new("Backs up to cloud storage", "cloud_storage", "backs_up_to", "target"),
    _new("Backs up to NAS / server", "nas_server", "backs_up_to", "target"),
]
_APP_MENU = [
    _new("Gives TOTP to: online account", "online_account", "provides_totp", "target"),
    _new("Gives TOTP to: email account", "email_account", "provides_totp", "target"),
    _new("Gives TOTP to: financial account", "financial_account", "provides_totp", "target"),
    _new("Stores password of: online account", "online_account", "stores_credentials", "target"),
    _new("Stores password of: email account", "email_account", "stores_credentials", "target"),
    _new("Stores password of: financial account", "financial_account", "stores_credentials", "target"),
]
_DROP_MENU: dict[str, list[dict]] = {
    **{t: _COMPUTER_MENU for t in COMPUTERS},
    "smartphone": [*_COMPUTER_MENU, _new("Gets SMS 2FA for: financial account", "financial_account", "provides_2fa_sms", "target")],
    "usb_drive": [
        _new("Folder stored here", "folder", "stored_on", "source"),
        _new("Backup file stored here", "backup", "stored_on", "source"),
        *_LOCATED,
    ],
    "hardware_key": [
        _new("Protects: email account", "email_account", "provides_hardware_key", "target"),
        _new("Protects: online account", "online_account", "provides_hardware_key", "target"),
        _new("Protects: financial account", "financial_account", "provides_hardware_key", "target"),
        *_LOCATED,
    ],
    **{t: _GEAR_MENU for t in NETWORK_GEAR},
    "modem": [_new("Connected: router", "router", "uplink_to", "source"), _new("Connected: firewall", "firewall", "uplink_to", "source")],
    "smart_tv": [
        _new("Apps", APP_GROUP, "installed_on", "source"),
        _new("Connects through: WiFi", "wifi", "connected_via", "target"),
        _new("Connects through: switch", "switch", "connected_via", "target"),
        _new("Located in: Local Network", "local_network", "located_in", "target"),
    ],
    "local_network": [
        _new("Router here", "router", "located_in", "source"),
        _new("Desktop PC here", "desktop", "located_in", "source"),
        _new("Laptop here", "laptop", "located_in", "source"),
        _new("NAS / server here", "nas_server", "located_in", "source"),
    ],
    "offsite": [
        _new("USB drive here", "usb_drive", "located_in", "source"),
        _new("NAS / server here", "nas_server", "located_in", "source"),
    ],
    "cloud": [
        _new("Hosted here: application", "application", "hosted_in", "source"),
        _new("Hosted here: database", "database", "hosted_in", "source"),
    ],
    "application": _APP_MENU,
    **{t: _ACCOUNT_MENU for t in ACCOUNTS},
    "email_account": [_new("2FA email for: financial account", "financial_account", "provides_2fa_email", "target"), *_ACCOUNT_MENU],
    "cloud_storage": [_new("Folder stored here", "folder", "stored_on", "source"), *_ACCOUNT_MENU],
    "password_manager": [
        _new("Stores password of: email account", "email_account", "stores_credentials", "target"),
        _new("Stores password of: financial account", "financial_account", "stores_credentials", "target"),
        _new("Stores password of: online account", "online_account", "stores_credentials", "target"),
        _new("Stores password of: social media", "social_account", "stores_credentials", "target"),
        _new("Gives TOTP to: online account", "online_account", "provides_totp", "target"),
        _new("Stores password + TOTP of: online account", "online_account", "stores_credentials_totp", "target"),
        _new("Stores password of: entertainment", "entertainment_account", "stores_credentials", "target"),
        _new("Vault backs up to USB drive", "usb_drive", "backs_up_to", "target"),
    ],
    **{t: _DATA_MENU for t in DATA},
}


def catalog_payload() -> dict:
    relations = [{**asdict(r), "sources": sorted(r.sources), "targets": sorted(r.targets)} for r in _RELATIONS]
    return {
        "categories": NODE_CATEGORIES,
        "palette_hidden": [APP_GROUP],
        "security_levels": SECURITY_LEVELS,
        "default_levels": DEFAULT_LEVELS,
        "password_types": PASSWORD_TYPES,
        "password_options": PASSWORD_OPTIONS,
        "password_labels": PASSWORD_LABELS,
        "encryption_types": ENCRYPTION_TYPES,
        "operating_systems": OPERATING_SYSTEMS,
        "os_options": OS_OPTIONS,
        "defenses": DEFENSES,
        "defense_options": DEFENSE_OPTIONS,
        "ip_labels": IP_LABELS,
        "fields": NODE_FIELDS,
        "statuses": NODE_STATUSES,
        "loss_modes": LOSS_MODES,
        "relations": relations,
        "suggested_relations": _SUGGESTED_BY_CATEGORY,
        "drop_menu": _DROP_MENU,
    }
