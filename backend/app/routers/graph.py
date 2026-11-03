"""CRUD for nodes and edges, plus blast radius, import/export and the sample graph."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..catalog import APP_GROUP, RELATIONS, catalog_payload, relation_allowed
from ..database import get_db
from ..models import Edge, Node
from ..schemas import (EdgeCreate, EdgeOut, EdgeUpdate, GraphImport, GraphOut, NodeCreate, NodeOut, NodeUpdate)
from ..seed import seed_payload
from ..services.graph_engine import blast_radius
from ..upgrades import COMBINED, apply_type_rules, fold_os_nodes, link_email_to_accounts, merge_password_totp_edges

router = APIRouter(prefix="/api", tags=["graph"])


def node_dicts(db: Session) -> list[dict]:
    return [NodeOut.model_validate(n).model_dump() for n in db.scalars(select(Node))]


def edge_dicts(db: Session) -> list[dict]:
    return [EdgeOut.model_validate(e).model_dump() for e in db.scalars(select(Edge))]


def _get_node(db: Session, node_id: str) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(404, "Node not found")
    return node


def _get_edge(db: Session, edge_id: str) -> Edge:
    edge = db.get(Edge, edge_id)
    if edge is None:
        raise HTTPException(404, "Edge not found")
    return edge


def _clear_breach_data(node: Node) -> None:
    node.breaches = None
    node.breach_checked_email = None
    node.breach_checked_at = None
    node.breach_advice = None


@router.get("/catalog")
def get_catalog() -> dict:
    return catalog_payload()


@router.get("/graph", response_model=GraphOut)
def get_graph(db: Session = Depends(get_db)):
    return {"nodes": list(db.scalars(select(Node))), "edges": list(db.scalars(select(Edge)))}


@router.post("/nodes", response_model=NodeOut, status_code=201)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)):
    if payload.parent_id:
        parent = _get_node(db, payload.parent_id)
        if parent.type != APP_GROUP or payload.type != "application":
            raise HTTPException(422, "Only applications can go inside an Apps node")
    node = Node(**payload.model_dump())
    apply_type_rules(node)
    db.add(node)
    db.flush()
    if payload.parent_id:
        db.add(Edge(source_id=node.id, target_id=payload.parent_id, relation="runs_on"))
    db.commit()
    link_email_to_accounts(db, node)
    return node


@router.patch("/nodes/{node_id}", response_model=NodeOut)
def update_node(node_id: str, payload: NodeUpdate, db: Session = Depends(get_db)):
    node = _get_node(db, node_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("type", "name", "security_level", "password_type", "encryption", "defenses", "status", "notes", "pos_x", "pos_y"):
        if field in changes and changes[field] is None:
            del changes[field]
    previous_email, previous_type = node.email, node.type
    for field, value in changes.items():
        setattr(node, field, value)
    apply_type_rules(node)
    if node.email != previous_email:
        _clear_breach_data(node)
    db.commit()
    # Only on a change, so a link the user deleted doesn't come back on the next save.
    if node.email != previous_email or node.type != previous_type:
        link_email_to_accounts(db, node)
    return node


@router.delete("/nodes/{node_id}", status_code=204)
def delete_node(node_id: str, db: Session = Depends(get_db)):
    db.delete(_get_node(db, node_id))
    db.commit()
    return Response(status_code=204)


@router.get("/nodes/{node_id}/blast-radius")
def get_blast_radius(node_id: str, db: Session = Depends(get_db)):
    _get_node(db, node_id)
    return blast_radius(node_dicts(db), edge_dicts(db), node_id)


def _check_relation(relation: str, source: Node, target: Node) -> None:
    if not relation_allowed(relation, source.type, target.type):
        label = RELATIONS[relation].label
        raise HTTPException(422, f"{source.name} can't be “{label}” {target.name}")


def _combined_edge(db: Session, source_id: str, target_id: str) -> Edge | None:
    return db.scalar(select(Edge).where(
        Edge.source_id == source_id, Edge.target_id == target_id, Edge.relation == COMBINED,
    ))


@router.post("/edges", response_model=EdgeOut, status_code=201)
def create_edge(payload: EdgeCreate, db: Session = Depends(get_db)):
    if payload.source_id == payload.target_id:
        raise HTTPException(422, "A node can't be connected to itself")
    source = _get_node(db, payload.source_id)
    target = _get_node(db, payload.target_id)
    _check_relation(payload.relation, source, target)
    duplicate = db.scalar(select(Edge).where(
        Edge.source_id == payload.source_id, Edge.target_id == payload.target_id, Edge.relation == payload.relation,
    ))
    if duplicate:
        raise HTTPException(409, "That relationship already exists")
    if payload.relation in ("stores_credentials", "provides_totp") and _combined_edge(db, payload.source_id, payload.target_id):
        raise HTTPException(409, "That relationship already exists")
    edge = Edge(**payload.model_dump())
    db.add(edge)
    db.commit()
    merge_password_totp_edges(db)
    return _combined_edge(db, payload.source_id, payload.target_id) if db.get(Edge, edge.id) is None else edge


@router.patch("/edges/{edge_id}", response_model=EdgeOut)
def update_edge(edge_id: str, payload: EdgeUpdate, db: Session = Depends(get_db)):
    edge = _get_edge(db, edge_id)
    changes = payload.model_dump(exclude_unset=True)
    # loss_mode may legitimately be set to null, meaning "back to the default".
    for field in ("relation", "notes"):
        if field in changes and changes[field] is None:
            del changes[field]
    if "relation" in changes:
        _check_relation(changes["relation"], db.get(Node, edge.source_id), db.get(Node, edge.target_id))
    for field, value in changes.items():
        setattr(edge, field, value)
    db.commit()
    source_id, target_id = edge.source_id, edge.target_id
    merge_password_totp_edges(db)
    return _combined_edge(db, source_id, target_id) if db.get(Edge, edge_id) is None else edge


@router.delete("/edges/{edge_id}", status_code=204)
def delete_edge(edge_id: str, db: Session = Depends(get_db)):
    db.delete(_get_edge(db, edge_id))
    db.commit()
    return Response(status_code=204)


@router.get("/export")
def export_graph(db: Session = Depends(get_db)):
    fields = ("id", "type", "name", "ip_address", "email", "security_level", "password_type",
              "os", "os_version", "encryption", "defenses", "parent_id", "status", "notes", "pos_x", "pos_y")
    edge_fields = ("source_id", "target_id", "relation", "loss_mode", "notes")
    return {
        "nodes": [{f: n[f] for f in fields} for n in node_dicts(db)],
        "edges": [{f: e[f] for f in edge_fields} for e in edge_dicts(db)],
    }


def _replace_graph(db: Session, payload: GraphImport) -> None:
    ids = {node.id for node in payload.nodes}
    if len(ids) != len(payload.nodes):
        raise HTTPException(422, "Import has duplicate node ids")
    for edge in payload.edges:
        if edge.source_id not in ids or edge.target_id not in ids:
            raise HTTPException(422, "Import has an edge pointing at a missing node")
    for item in payload.nodes:
        if item.parent_id and item.parent_id not in ids:
            raise HTTPException(422, "Import has an app inside a missing Apps node")
    db.execute(delete(Edge))
    db.execute(delete(Node))
    # Ids in a file are only references within that file, so fresh ones are issued.
    new_nodes = {}
    for item in payload.nodes:
        node = Node(**item.model_dump(exclude={"id", "parent_id"}))
        apply_type_rules(node)
        db.add(node)
        new_nodes[item.id] = node
    db.flush()
    for item in payload.nodes:
        if item.parent_id:
            new_nodes[item.id].parent_id = new_nodes[item.parent_id].id
    for item in payload.edges:
        db.add(Edge(**{
            **item.model_dump(),
            "source_id": new_nodes[item.source_id].id,
            "target_id": new_nodes[item.target_id].id,
        }))
    db.commit()
    fold_os_nodes(db)
    merge_password_totp_edges(db)


@router.post("/import", response_model=GraphOut)
def import_graph(payload: GraphImport, db: Session = Depends(get_db)):
    _replace_graph(db, payload)
    return get_graph(db)


@router.post("/seed", response_model=GraphOut)
def load_sample(db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(Node)):
        raise HTTPException(409, "The sample can only be loaded into an empty graph")
    _replace_graph(db, GraphImport.model_validate(seed_payload()))
    return get_graph(db)
