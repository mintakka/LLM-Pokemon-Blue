#!/usr/bin/env python3
import argparse
import json
import re
import socket
from pathlib import Path
from typing import Any, Dict, List, Optional

from urllib3.util import connection


DEFAULT_ENDPOINTS = [
    "http://127.0.0.1:1234/v1",
    "http://100.87.135.76:11434/v1",
]

VISION_HINTS = (
    "vision",
    "vl",
    "llava",
    "bakllava",
    "moondream",
    "pixtral",
    "minicpm-v",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "gemma-4",
    "gemma4",
)

NON_VISION_HINTS = (
    "embedding",
    "embed",
    "text-embedding",
    "nomic-embed",
    "bge-",
)


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        return url
    return url if url.endswith("/v1") else f"{url}/v1"


def provider_key(base_url: str, model_name: str) -> str:
    endpoint = "lmstudio" if "127.0.0.1:1234" in base_url else "ollama" if "11434" in base_url else "local"
    model = re.sub(r"[^a-zA-Z0-9]+", "_", model_name).strip("_").lower()
    return f"{endpoint}_{model}"[:80]


def is_likely_vision_model(model_name: str) -> bool:
    lowered = model_name.lower()
    if any(hint in lowered for hint in NON_VISION_HINTS):
        return False
    return any(hint in lowered for hint in VISION_HINTS)


def get_api_key(base_url: str) -> str:
    if "127.0.0.1:1234" in base_url:
        return "lm-studio"
    if "11434" in base_url:
        return "ollama"
    return "local-api-key"


def list_models(base_url: str, timeout: int) -> List[str]:
    import requests

    response = requests.get(f"{base_url}/models", timeout=(5, timeout))
    response.raise_for_status()
    payload = response.json()
    models = []
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))
    return sorted(set(models), key=str.lower)


def red_pixel_png_base64() -> str:
    return (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/"
        "pLvAAAAAElFTkSuQmCC"
    )


def smoke_test_vision(base_url: str, api_key: str, model_name: str, timeout: int) -> Optional[bool]:
    import requests

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "This image is one solid color. Reply with only the color name, "
                            "one word, lowercase."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{red_pixel_png_base64()}",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 8,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(5, timeout),
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"].strip().lower()
        return "red" in text
    except Exception as exc:
        print(f"Vision smoke test could not complete: {exc}")
        return None


def load_config(path: Path) -> Dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text())

    template = path.with_name("config.template.json")
    if template.exists():
        return json.loads(template.read_text())

    return {
        "game_title": "Pokemon Blue",
        "rom_path": "~/Downloads/ROM/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).sgb",
        "providers": {},
        "host": "127.0.0.1",
        "port": 8888,
        "notepad_path": "notepad.txt",
        "screenshot_path": "data/screenshots/screenshot.png",
        "decision_cooldown": 5,
        "thinking_history_max_chars": 20000,
        "thinking_history_keep_entries": 5,
        "debug_mode": True,
    }


def save_config(path: Path, config: Dict[str, Any]) -> None:
    path.write_text(json.dumps(config, indent=4, ensure_ascii=False) + "\n")


def prompt_choice(prompt: str, count: int) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            choice = int(raw)
            if 1 <= choice <= count:
                return choice - 1
        except ValueError:
            pass
        print(f"Enter a number from 1 to {count}.")


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = input(f"{prompt} [{suffix}] ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Select a local OpenAI-compatible model endpoint.")
    parser.add_argument("--config", default="config.json", help="Config file to update.")
    parser.add_argument(
        "--endpoint",
        action="append",
        dest="endpoints",
        help="OpenAI-compatible base URL. Can be passed more than once.",
    )
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout for probing endpoints.")
    parser.add_argument("--smoke-test", action="store_true", help="Send a tiny image to the selected model.")
    parser.add_argument("--allow-ipv6", action="store_true", help="Do not force IPv4 for endpoint probes.")
    args = parser.parse_args()

    if not args.allow_ipv6:
        connection.allowed_gai_family = lambda: socket.AF_INET

    endpoints = [normalize_base_url(url) for url in (args.endpoints or DEFAULT_ENDPOINTS)]
    available: List[Dict[str, Any]] = []

    print("Probing local model endpoints...\n")
    for endpoint in endpoints:
        try:
            models = list_models(endpoint, args.timeout)
            print(f"{endpoint}: found {len(models)} model(s)")
            for model in models:
                available.append({
                    "base_url": endpoint,
                    "model_name": model,
                    "likely_vision": is_likely_vision_model(model),
                })
        except Exception as exc:
            print(f"{endpoint}: unavailable ({exc})")

    if not available:
        print("\nNo models found. Start LM Studio/Ollama and try again.")
        return 1

    available.sort(key=lambda item: (not item["likely_vision"], item["base_url"], item["model_name"].lower()))

    print("\nAvailable models:")
    for index, item in enumerate(available, 1):
        marker = "likely vision" if item["likely_vision"] else "unknown/text"
        print(f"{index:2}. [{marker}] {item['model_name']}  ({item['base_url']})")

    selected = available[prompt_choice("\nSelect model number: ", len(available))]
    api_key = get_api_key(selected["base_url"])

    should_smoke_test = args.smoke_test or prompt_yes_no("Run a quick image smoke test on this model?", default=False)
    if should_smoke_test:
        result = smoke_test_vision(selected["base_url"], api_key, selected["model_name"], args.timeout)
        if result is True:
            print("Vision smoke test passed.")
        elif result is False:
            print("Vision smoke test did not identify the red image. The model may not support images.")

    config_path = Path(args.config)
    config = load_config(config_path)
    config.setdefault("providers", {})

    key = provider_key(selected["base_url"], selected["model_name"])
    config["providers"][key] = {
        "provider": "openai_compatible",
        "base_url": selected["base_url"],
        "api_key": api_key,
        "model_name": selected["model_name"],
        "max_tokens": 1024,
        "temperature": 0.2,
        "connect_timeout": 10,
        "timeout": 240 if "32b" in selected["model_name"].lower() else 180,
        "force_ipv4": not args.allow_ipv6,
        "image_detail": "low",
    }
    config["llm_provider"] = key

    save_config(config_path, config)

    print(f"\nUpdated {config_path}:")
    print(f'  "llm_provider": "{key}"')
    print(f'  model_name: "{selected["model_name"]}"')
    print(f'  base_url: "{selected["base_url"]}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
