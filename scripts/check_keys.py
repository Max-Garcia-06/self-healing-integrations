"""Verify sponsor API keys are live by making a cheap real request to each provider."""

import os
from pathlib import Path

import httpx

TIMEOUT = 10.0


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def check_minimax(key: str) -> tuple[bool, int, str]:
    resp = httpx.post(
        "https://api.minimax.io/v1/text/chatcompletion_v2",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": "MiniMax-Text-01",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        },
        timeout=TIMEOUT,
    )
    return resp.status_code < 400, resp.status_code, resp.text[:200]


def check_elevenlabs(key: str) -> tuple[bool, int, str]:
    resp = httpx.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": key},
        timeout=TIMEOUT,
    )
    return resp.status_code < 400, resp.status_code, resp.text[:200]


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    checks = [
        ("MINIMAX_API_KEY", check_minimax),
        ("ELEVENLABS_API_KEY", check_elevenlabs),
    ]

    for env_name, check_fn in checks:
        key = os.environ.get(env_name)
        if not key:
            print(f"{env_name:24} SKIP   no key in .env")
            continue
        try:
            ok, status, body = check_fn(key)
            label = "PASS" if ok else "FAIL"
            print(f"{env_name:24} {label}   status={status}" + (f"  body={body!r}" if not ok else ""))
        except httpx.HTTPError as exc:
            print(f"{env_name:24} FAIL   request error: {exc}")

    band_key = os.environ.get("BAND_API_KEY")
    if not band_key:
        print(f"{'BAND_API_KEY':24} SKIP   no key in .env")
    else:
        print(f"{'BAND_API_KEY':24} SKIP   unsure of Band's simplest authenticated GET endpoint, not guessing")


if __name__ == "__main__":
    main()
