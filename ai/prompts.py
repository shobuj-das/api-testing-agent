"""Prompt construction kept separate from client and agent business logic."""

from __future__ import annotations

from pydantic import BaseModel

STRUCTURED_OUTPUT_SYSTEM_PROMPT = """You are an API quality-analysis assistant.
Return only a JSON object that matches the requested schema. Do not include Markdown,
shell commands, Python code intended for execution, credentials, or unsupported fields.
Reasoning must be a concise evidence-based summary, never hidden chain-of-thought."""


def structured_output_prompt(task: str, response_model: type[BaseModel]) -> str:
    """Request JSON-only output and expose the public Pydantic JSON schema."""
    return (
        f"Task:\n{task}\n\n"
        "Return exactly one JSON object conforming to this JSON Schema:\n"
        f"{response_model.model_json_schema()}"
    )


def correction_prompt(response_model: type[BaseModel], validation_error: str) -> str:
    """Ask for a corrected response without echoing possibly sensitive prior content."""
    return (
        "Your previous structured response was rejected. Return a replacement JSON object only. "
        f"It must conform to this schema: {response_model.model_json_schema()}\n"
        f"Validation feedback: {validation_error}"
    )
