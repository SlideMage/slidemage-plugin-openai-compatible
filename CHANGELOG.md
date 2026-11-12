# OpenAI-compatible release history

v0.9.0 (2026-11-12, first release): An AI route for OpenAI-compatible /chat/completions servers.

NEW: OpenAI-compatible servers in SlideMage, with your own key and model.
- Choose OpenAI, Mistral or OpenRouter under Settings → AI → OpenAI-compatible for chat, image descriptions, translation and fixes.
- Connect LM Studio, vLLM, Ollama's /v1 or another OpenAI-compatible server by choosing Other and setting its base URL.
- Keep a separate API key for each server host; switching servers restores its own key.
- Add a model the server does not list under Extra model IDs.
- Check connection shows whether the server and key work, and how many models it offers.
- Mistral's reasoning models answer with their text only; their thinking is left out.
