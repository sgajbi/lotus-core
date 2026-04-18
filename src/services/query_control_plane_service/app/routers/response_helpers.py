from __future__ import annotations


def problem_response(description: str, example: dict[str, str]) -> dict[str, object]:
    return {"description": description, "content": {"application/json": {"example": example}}}
