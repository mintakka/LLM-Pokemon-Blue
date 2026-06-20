#!/usr/bin/env python3
import base64
import io
import json
import re
import socket
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image
from urllib3.util import connection


class LocalToolCall:
    """Tool-call shaped object used by the controller."""

    def __init__(self, name: str, arguments: Dict[str, Any]):
        self.id = name
        self.name = name
        self.arguments = arguments


class LocalLLMClient:
    """Client for local OpenAI-compatible and Ollama chat endpoints."""

    VALID_BUTTONS = {"A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L"}

    def __init__(self, config: Dict[str, Any], game_title: str = "Pokemon Blue"):
        self.config = config
        self.provider = config.get("provider", "openai_compatible").lower()
        self.base_url = config.get("base_url", "http://127.0.0.1:1234/v1").rstrip("/")
        self.model_name = config["model_name"]
        self.api_key = config.get("api_key", "not-needed")
        self.max_tokens = config.get("max_tokens", 1024)
        self.temperature = config.get("temperature", 0.2)
        self.timeout = config.get("timeout", 120)
        self.connect_timeout = config.get("connect_timeout", 10)
        self.force_ipv4 = config.get("force_ipv4", True)
        self.game_title = game_title

        if self.force_ipv4:
            connection.allowed_gai_family = lambda: socket.AF_INET

    def call_with_tools(
        self,
        message: str,
        tools: List[Any],
        images: Optional[List[Image.Image]] = None,
    ) -> Tuple[Any, List[LocalToolCall], str]:
        prompt = self._build_action_prompt(message, tools)

        if self.provider == "ollama":
            raw_response = self._call_ollama(prompt, images)
            text = raw_response.get("message", {}).get("content", "")
        else:
            raw_response = self._call_openai_compatible(prompt, images)
            text = self._extract_openai_text(raw_response)

        tool_calls = self._parse_tool_calls(text, tools)
        return raw_response, tool_calls, text

    def _extract_openai_text(self, raw_response: Dict[str, Any]) -> str:
        choices = raw_response.get("choices", [])
        if not choices:
            return ""

        message = choices[0].get("message", {}) or {}
        content = message.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = ""

        if text:
            return text

        for key in ("reasoning_content", "reasoning", "thinking"):
            value = message.get(key)
            if isinstance(value, str) and value.strip():
                return value

        return ""

    def _build_action_prompt(self, message: str, tools: List[Any]) -> str:
        if not tools:
            return message

        tool_names = {tool.name for tool in tools}
        response_shape = {
            "screen_type": "title | menu | dialogue | overworld | battle | naming | unknown",
            "description": "Briefly describe the current screen.",
            "plan": "Briefly explain the next action in terms of the current screen type.",
        }

        if "press_button" in tool_names:
            response_shape["button"] = "UP | DOWN | LEFT | RIGHT | A | B | START | SELECT"
        if "update_notepad" in tool_names:
            response_shape["notepad_update"] = "Optional concise memory update, or empty string."

        return f"""{message}

You are connected to a local LLM endpoint that may not support native function calls.
Return ONLY valid JSON. Do not wrap it in markdown.

Required JSON shape:
{json.dumps(response_shape, indent=2)}

Rules:
- Choose exactly one button.
- The button value must be one of: A, B, START, SELECT, UP, DOWN, LEFT, RIGHT, R, L.
- Prefer movement buttons while navigating. Use A only for menus, dialogue, or when directly facing an interactable object.
- Use an empty string for notepad_update unless something important changed.
"""

    def _call_openai_compatible(self, prompt: str, images: Optional[List[Image.Image]]) -> Dict[str, Any]:
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images or []:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{self._image_to_base64(image)}",
                    "detail": self.config.get("image_detail", "low"),
                },
            })

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are an AI playing {self.game_title}. "
                        "Respond with the exact JSON shape requested by the user."
                    ),
                },
                {"role": "user", "content": content},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(self.connect_timeout, self.timeout),
        )
        response.raise_for_status()
        return response.json()

    def _call_ollama(self, prompt: str, images: Optional[List[Image.Image]]) -> Dict[str, Any]:
        user_message: Dict[str, Any] = {"role": "user", "content": prompt}
        image_payload = [self._image_to_base64(image) for image in images or []]
        if image_payload:
            user_message["images"] = image_payload

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are an AI playing {self.game_title}. "
                        "Respond with the exact JSON shape requested by the user."
                    ),
                },
                user_message,
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=(self.connect_timeout, self.timeout),
        )
        response.raise_for_status()
        return response.json()

    def _parse_tool_calls(self, text: str, tools: List[Any]) -> List[LocalToolCall]:
        tool_names = {tool.name for tool in tools}
        parsed = self._extract_json(text)
        calls: List[LocalToolCall] = []

        if parsed and "update_notepad" in tool_names:
            notepad_update = str(parsed.get("notepad_update", "")).strip()
            if notepad_update:
                calls.append(LocalToolCall("update_notepad", {"content": notepad_update}))

        button = ""
        if parsed:
            button = str(parsed.get("button", "")).upper().strip()
        if not button:
            button = self._extract_button_from_text(text)

        if button in self.VALID_BUTTONS and "press_button" in tool_names:
            calls.append(LocalToolCall("press_button", {"button": button}))

        return calls

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None

        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def _extract_button_from_text(self, text: str) -> str:
        patterns = [
            r"\b(?:button|press|choose|input|selected_button|next_button)\s*[:=-]\s*['\"]?(A|B|START|SELECT|UP|DOWN|LEFT|RIGHT|R|L)\b",
            r"\b(?:press|choose|input)\s+(?:the\s+)?(?:button\s+)?['\"]?(A|B|START|SELECT|UP|DOWN|LEFT|RIGHT|R|L)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return ""

    def _image_to_base64(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


def create_local_llm_client_for_provider(config: Dict[str, Any], provider_name: str, game_title: str) -> LocalLLMClient:
    provider_config = config.get("providers", {}).get(provider_name)
    if not provider_config:
        raise ValueError(f"No provider config found for llm_provider '{provider_name}'")

    return LocalLLMClient(provider_config, game_title=game_title)


def create_local_llm_client(config: Dict[str, Any], game_title: str) -> LocalLLMClient:
    provider_name = config.get("llm_provider", "lmstudio").lower()
    return create_local_llm_client_for_provider(config, provider_name, game_title)
