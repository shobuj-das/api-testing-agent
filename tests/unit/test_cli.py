"""Unit tests for Milestone 13: Project config and test storage."""

from pathlib import Path

import pytest

from config.project_config import ProjectAuthConfig, ProjectConfig
from models.api_models import HTTPMethod
from models.test_case import Priority, TestCategory as ApiTestCategory, TestCase as ApiTestCase
from test_data.test_storage import load_generated_tests, save_generated_tests


def test_project_config_roundtrip(tmp_path: Path) -> None:
    config_file = tmp_path / "project.yaml"
    cfg = ProjectConfig(
        project_name="Order Service",
        spec_path="swagger.json",
        base_url="https://api.orders.test",
        auth=ProjectAuthConfig(
            endpoint="/api/v1/login",
            payload={"user": "admin"},
        ),
        initial_variables={"tenant_id": "cust-1"},
    )
    cfg.to_file(config_file)
    assert config_file.exists()

    loaded = ProjectConfig.from_file(config_file)
    assert loaded.project_name == "Order Service"
    assert loaded.base_url == "https://api.orders.test"
    assert loaded.auth is not None
    assert loaded.auth.endpoint == "/api/v1/login"
    assert loaded.initial_variables["tenant_id"] == "cust-1"


def test_test_storage_save_and_load(tmp_path: Path) -> None:
    storage_file = tmp_path / "tests.json"
    tc = ApiTestCase(
        id="order-create",
        title="Create Order",
        description="Functional test for creating an order",
        method=HTTPMethod.POST,
        endpoint="/orders",
        request_body={"item_id": 42},
        expected_status=201,
        category=ApiTestCategory.FUNCTIONAL,
        priority=Priority.CRITICAL,
        source="unit_test",
    )

    save_path = save_generated_tests([tc], destination=storage_file)
    assert save_path.exists()

    loaded_tests = load_generated_tests(storage_file)
    assert len(loaded_tests) == 1
    assert loaded_tests[0].id == "order-create"
    assert loaded_tests[0].method == HTTPMethod.POST
    assert loaded_tests[0].expected_status == 201
