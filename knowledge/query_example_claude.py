import asyncio
import json
import subprocess
from pathlib import Path


async def query_claude(
    prompt: str,
    model: str = "claude-opus-4-8",
    json_schema: dict | None = None,
) -> str:
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--allowedTools", "WebSearch,WebFetch",
        "--output-format", "json",
    ]
    if json_schema is not None:
        cmd.extend(["--json-schema", json.dumps(json_schema)])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path.home()),
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited with {proc.returncode}")

    data = json.loads(stdout.decode())
    structured = data.get("structured_output")
    if structured is not None:
        return json.dumps(structured)
    return data.get("result", "")


async def main() -> None:
    schema = {
        "type": "object",
        "properties": {
            "countries_and_capitals": {
                "type": "array",
                "description": "List containing pairs of country names and their capitals.",
                "items": {
                    "type": "object",
                    "properties": {
                        "country": {"type": "string", "description": "The name of the country."},
                        "capital": {"type": "string", "description": "The capital city of the country."},
                    },
                    "required": ["country", "capital"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["countries_and_capitals"],
        "additionalProperties": False,
    }
    text = await query_claude(
        prompt="Capital cities of France, Germany, Japan, and Italy are?",
        model="haiku",
        json_schema=schema,
    )
    data = json.loads(text)
    flat = {item["country"]: item["capital"] for item in data["countries_and_capitals"]}
    print(json.dumps(flat))


if __name__ == "__main__":
    asyncio.run(main())
