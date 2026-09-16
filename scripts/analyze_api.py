"""CLI tool to analyze an OpenAPI specification and explain its dependencies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import yaml

from config.project_config import ProjectConfig
from openapi.analyzer import OpenAPIAnalyzer
from openapi.dependency_detector import DependencyDetector
from openapi.parser import OpenAPIParser


def fetch_spec_document(source: str) -> dict[str, Any]:
    """Fetch spec document from a local path or HTTP/HTTPS URL."""
    if source.startswith(("http://", "https://")):
        resp = requests.get(source, timeout=15)
        resp.raise_for_status()
        content = resp.text
        return json.loads(content) if (source.endswith(".json") or content.strip().startswith("{")) else yaml.safe_load(content)
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {source}")
    content = path.read_text(encoding="utf-8")
    return json.loads(content) if path.suffix.lower() == ".json" else yaml.safe_load(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze an OpenAPI 3 specification for API testing.")
    parser.add_argument("--spec", help="Path or URL to OpenAPI 3 JSON/YAML file.")
    parser.add_argument("--spec-url", help="URL to remote OpenAPI 3 specification.")
    parser.add_argument("--config", help="Optional project config file (YAML/JSON).")
    parser.add_argument("--json", action="store_true", help="Output analysis in JSON format.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output.")

    args = parser.parse_args()

    spec_source = args.spec or args.spec_url
    if args.config:
        cfg = ProjectConfig.from_file(args.config)
        spec_source = spec_source or cfg.spec_path or cfg.spec_url

    if not spec_source:
        print("Error: Specify an OpenAPI spec with --spec <file_or_url> or --config <file>", file=sys.stderr)
        return 1

    try:
        doc = fetch_spec_document(spec_source)
        openapi_parser = OpenAPIParser()
        spec = openapi_parser.parse_document(doc)
    except Exception as exc:
        print(f"Error parsing OpenAPI specification: {exc}", file=sys.stderr)
        return 1

    analyzer = OpenAPIAnalyzer()
    endpoint_facts = analyzer.analyze_specification(spec)

    detector = DependencyDetector()
    graph = detector.detect_dependencies(spec)

    if args.json:
        output = {
            "title": spec.title,
            "version": spec.version,
            "servers": spec.servers,
            "endpoint_count": len(spec.endpoints),
            "dependencies": [dep.model_dump(mode="json") for dep in graph.dependencies],
        }
        print(json.dumps(output, indent=2))
        return 0

    print("=" * 60)
    print(f" API SPECIFICATION ANALYSIS: {spec.title} (v{spec.version})")
    print("=" * 60)
    print(f"OpenAPI Version: {spec.openapi_version}")
    print(f"Servers: {', '.join(spec.servers) if spec.servers else 'None declared'}")
    print(f"Endpoints found: {len(spec.endpoints)}")
    print("-" * 60)

    print("\n[ENDPOINTS & INPUTS]")
    for ep, facts in zip(spec.endpoints, endpoint_facts, strict=False):
        auth_tag = "[AUTH]" if ep.authentication_required else ""
        print(f"  • {ep.method.value:<6} {ep.path} {auth_tag}")
        if facts.required_inputs:
            print(f"    Required: {', '.join(facts.required_inputs)}")
        if args.verbose and facts.optional_inputs:
            print(f"    Optional: {', '.join(facts.optional_inputs)}")

    print(f"\n[DETECTED DEPENDENCIES] ({len(graph.dependencies)} found)")
    if not graph.dependencies:
        print("  No operation dependencies detected.")
    else:
        for i, dep in enumerate(graph.dependencies, start=1):
            print(f"  {i}. [{dep.dependency_type.value.upper()}] (confidence: {dep.confidence:.2f})")
            print(f"     Producer: {dep.producer_method.value} {dep.producer_path} -> extracts '{dep.extraction_path}' as '{dep.variable_name}'")
            print(f"     Consumer: {dep.consumer_method.value} {dep.consumer_path} -> binds to {dep.target_location.value} param '{dep.target_parameter}'")
            if args.verbose:
                print(f"     Evidence: {'; '.join(dep.evidence)}")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
