"""Gemini LLM provider for config generation and scenario generation."""
import os
import json
import logging
import requests

logger = logging.getLogger(__name__)


def _call_gemini(prompt: str, system_prompt: str = "", max_tokens: int = 65536, temperature: float = 0.0) -> str:
    """Call Google Gemini API via REST."""
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set.")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    contents = []
    if system_prompt:
        contents.append({"role": "user", "parts": [{"text": f"System instructions:\n{system_prompt}"}]})
        contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these instructions."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    
    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json"
        }
    }
    
    resp = requests.post(url, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text.strip()
    except (KeyError, IndexError) as e:
        logger.error("Unexpected Gemini response structure: %s", data)
        raise ValueError(f"Failed to parse Gemini response: {e}")
