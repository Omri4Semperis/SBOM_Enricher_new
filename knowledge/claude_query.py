import asyncio
import json
import subprocess
from pathlib import Path


async def query_claude(prompt: str, model: str = "claude-opus-4-8") -> str:
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        "--model", model,
        "--allowedTools", "WebSearch,WebFetch",
        "--output-format", "json",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path.home()),
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited with {proc.returncode}")

    data = json.loads(stdout.decode())
    return data.get("result", "")


async def main() -> None:
    print(await query_claude(
        prompt="Reply with one short sentence about SPDX licenses.",
        model="haiku"
    ))


if __name__ == "__main__":
    asyncio.run(main())