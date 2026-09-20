"""The knowledge-graph routes when the connector is off or the database is down: normal states, plainly said."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app import graph_projection, main

client = TestClient(main.app)


def test_an_unset_connector_is_reported_as_not_configured_not_as_a_fault() -> None:
    with patch.object(graph_projection, "CHASEOS_GRAPH_DIR", ""), patch.object(main.state, "pool", None):
        response = client.get("/state/knowledge/graph/status")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "not_configured" and body["configured"] is False and body["projected"] is None
    assert body["authority"] == "read_only_projection"


def test_ingest_needs_the_database_and_then_the_connector() -> None:
    with patch.object(main.state, "pool", None):
        assert client.post("/state/knowledge/graph/ingest").status_code == 503
    with patch.object(graph_projection, "CHASEOS_GRAPH_DIR", ""), patch.object(main.state, "pool", object()):
        response = client.post("/state/knowledge/graph/ingest")
    assert response.status_code == 503 and "CHASEOS_GRAPH_DIR" in response.json()["detail"]


def test_an_empty_snapshot_directory_is_a_404_naming_it(tmp_path) -> None:
    with patch.object(graph_projection, "CHASEOS_GRAPH_DIR", str(tmp_path)), patch.object(main.state, "pool", object()):
        response = client.post("/state/knowledge/graph/ingest")
    assert response.status_code == 404 and str(tmp_path) in response.json()["detail"]


def test_the_walk_depth_and_result_size_are_bounded() -> None:
    with patch.object(main.state, "pool", None):
        assert client.get("/state/knowledge/graph/neighbours/n1", params={"depth": 5}).status_code == 422
        assert client.get("/state/knowledge/graph/neighbours/n1", params={"limit": 501}).status_code == 422
        assert client.get("/state/knowledge/graph/nodes", params={"limit": 0}).status_code == 422
