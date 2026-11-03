"""Pydantic request and response models."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from .catalog import ACCEPTED_NODE_TYPES, OPERATING_SYSTEMS, PASSWORD_TYPES, RELATIONS

SecurityLevel = Literal["low", "medium", "high", "critical"]
Encryption = Literal["unknown", "none", "encrypted"]
Status = Literal["active", "legacy"]
LossMode = Literal["required", "alternative", "backup", "network", "none"]


def _known_os(value: str | None) -> str | None:
    value = value or None
    if value and value not in OPERATING_SYSTEMS:
        raise ValueError(f"unknown operating system '{value}'")
    return value


def _known_node_type(value: str) -> str:
    if value not in ACCEPTED_NODE_TYPES:
        raise ValueError(f"unknown node type '{value}'")
    return value


def _known_password_type(value: str) -> str:
    if value not in PASSWORD_TYPES:
        raise ValueError(f"unknown password type '{value}'")
    return value


def _known_relation(value: str) -> str:
    if value not in RELATIONS:
        raise ValueError(f"unknown relation '{value}'")
    return value


def _blank_to_none(value: str | None) -> str | None:
    value = value.strip() if value else value
    return value or None


def _valid_email(value: str | None) -> str | None:
    value = _blank_to_none(value)
    if value and (value.count("@") != 1 or value.startswith("@") or value.endswith("@") or " " in value):
        raise ValueError("not a valid email address")
    return value


NodeType = Annotated[str, AfterValidator(_known_node_type)]
PasswordType = Annotated[str, AfterValidator(_known_password_type)]
RelationId = Annotated[str, AfterValidator(_known_relation)]
OptionalText = Annotated[str | None, Field(default=None, max_length=64), AfterValidator(_blank_to_none)]
Email = Annotated[str | None, Field(default=None, max_length=254), AfterValidator(_valid_email)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
OperatingSystem = Annotated[str | None, Field(default=None), AfterValidator(_known_os)]


class NodeCreate(BaseModel):
    type: NodeType
    name: Name
    ip_address: OptionalText = None
    email: Email = None
    security_level: SecurityLevel = "medium"
    password_type: PasswordType = "unknown"
    os: OperatingSystem = None
    os_version: OptionalText = None
    encryption: Encryption = "unknown"
    defenses: list[str] = []
    parent_id: str | None = None
    status: Status = "active"
    notes: str = ""
    pos_x: float = 0
    pos_y: float = 0


class NodeUpdate(BaseModel):
    type: NodeType | None = None
    name: Name | None = None
    ip_address: OptionalText = None
    email: Email = None
    security_level: SecurityLevel | None = None
    password_type: PasswordType | None = None
    os: OperatingSystem = None
    os_version: OptionalText = None
    encryption: Encryption | None = None
    defenses: list[str] | None = None
    status: Status | None = None
    notes: str | None = None
    pos_x: float | None = None
    pos_y: float | None = None


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    name: str
    ip_address: str | None
    email: str | None
    security_level: str
    password_type: str
    os: str | None
    os_version: str | None
    encryption: str
    defenses: list[str] | None
    parent_id: str | None
    status: str
    notes: str
    pos_x: float
    pos_y: float
    breaches: list | None
    breach_checked_at: datetime | None
    breach_advice: str | None


class EdgeCreate(BaseModel):
    source_id: str
    target_id: str
    relation: RelationId
    loss_mode: LossMode | None = None
    notes: str = ""


class EdgeUpdate(BaseModel):
    relation: RelationId | None = None
    loss_mode: LossMode | None = None
    notes: str | None = None


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    target_id: str
    relation: str
    loss_mode: str | None
    notes: str


class GraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class ImportNode(NodeCreate):
    id: str


class ImportEdge(EdgeCreate):
    pass


class GraphImport(BaseModel):
    nodes: list[ImportNode]
    edges: list[ImportEdge]


class AskRequest(BaseModel):
    question_id: str | None = None
    text: Annotated[str | None, Field(default=None, max_length=500), AfterValidator(_blank_to_none)] = None
    model: str | None = None
    web_search: bool = True


class AnalyzeRequest(BaseModel):
    model: str | None = None
    web_search: bool = True
