# LLM-Pokemon-Blue-Benchmark

> An AI benchmark that evaluates LLMs by having them play Pokémon Blue through visual understanding and decision making

## Project Vision

This project challenges AI systems to play Pokémon Blue by only seeing the game screen, just like a human would. It tests the AI's ability to understand visuals, make decisions, remember context, plan strategies, and adapt to changing situations - all valuable skills that translate to real-world AI applications.

## Demo

🎬 [**Watch the Video on Loom**](https://www.loom.com/share/bf5114789d4a4a9fb6fefa5488e7a15f?sid=dbbdeb60-9f4f-4f39-af26-bd68f6935c5e)

## How It Works

1. **Game Emulator (mGBA)** runs Pokémon Blue with a Lua script that:
   - Takes screenshots on request
   - Captures game state information (player position, direction, map ID)
   - Receives button commands from the controller
   - Executes those commands in the game
   - Notifies the controller when ready for the next command

2. **Python Controller** bridges the emulator and AI:
   - Requests screenshots when ready to process
   - Manages the AI's short-term memory of recent actions
   - Maintains a long-term "notepad" of game progress
   - Processes screenshots through the LLM API
   - Sends button commands back to the emulator
   - Enforces rate limiting to prevent API overload

3. **Local LLM Provider** acts as the "brain":
   - Analyzes game screenshots with enhanced visibility
   - Uses game state context to make informed decisions
   - Decides which buttons to press
   - Updates the notepad to track progress

## Quick Setup

1. **Install dependencies**:
```bash
conda activate blue
pip install -r requirements.txt
```

2. **Start a local LLM server**:

   LM Studio:
   - Load `google/gemma-4-12b` or `google/gemma-4-e2b` in LM Studio.
   - Start the local server.
   - The config expects the OpenAI-compatible base URL: `http://127.0.0.1:1234/v1`.

   Ollama:
   - Start Ollama on the machine at `100.87.135.76`.
   - The config expects the OpenAI-compatible base URL: `http://100.87.135.76:11434/v1`.
   - Available configured models include `qwen3-vl:8b-instruct`, `qwen3-vl:32b`, `qwen3-embedding:8b`, `qwen3.6:35b-a3b-q4_K_M`, `glm-4.7-flash:q4_K_M`, `qwen3.6:27b`, `gemma4:31b`, `gemma4:26b`, and `nemotron-3-nano:30b`.

   The model must support images. Text-only models cannot play from screenshots.

3. **Set up your config**:
   - Run the endpoint configurator:
```bash
conda activate blue
python configure_endpoint.py
```

   - The script probes:
     - `http://127.0.0.1:1234/v1`
     - `http://100.87.135.76:11434/v1`
   - It lists available models, marks likely vision models, lets you select one, and updates `config.json`.
   - To probe a different OpenAI-compatible endpoint:
```bash
python configure_endpoint.py --endpoint http://127.0.0.1:8000/v1
```
   - To run a small image smoke test on the selected model:
```bash
python configure_endpoint.py --smoke-test
```

   `config.json` is also already set to LM Studio `google/gemma-4-12b` by default:
```json
{
  "game_title": "Pokémon Blue",
  "rom_path": "~/Downloads/ROM/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).sgb",
  "llm_provider": "lmstudio_gemma_4_12b",
  "host": "127.0.0.1",
  "port": 8888,
  "decision_cooldown": 5,
  "screenshot_path": "data/screenshots/screenshot.png",
  "notepad_path": "notepad.txt",
  "debug_mode": true,
  "providers": {
    "lmstudio_gemma_4_12b": {
      "provider": "openai_compatible",
      "base_url": "http://127.0.0.1:1234/v1",
      "api_key": "lm-studio",
      "model_name": "google/gemma-4-12b",
      "max_tokens": 1024,
      "temperature": 0.2,
      "timeout": 120,
      "image_detail": "low"
    }
  }
}
```

   To switch models, change only `llm_provider` to one of:
   - `lmstudio_gemma_4_12b`
   - `lmstudio_gemma_4_e2b`
   - `ollama_qwen3_vl_8b_instruct`
   - `ollama_qwen3_vl_32b`
   - `ollama_qwen3_embedding_8b`
   - `ollama_qwen3_6_35b_a3b_q4_k_m`
   - `ollama_glm_4_7_flash_q4_k_m`
   - `ollama_qwen3_6_27b`
   - `ollama_gemma4_31b`
   - `ollama_gemma4_26b`
   - `ollama_nemotron_3_nano_30b`

4. **Update the Lua script path**:
   - Open `emulator/script.lua` in any text editor
   - Find and change the following line to match your system's full path:
   ```lua
   local screenshotPath = "/Users/matt/Projects/LLM-Pokemon-Blue/data/screenshots/screenshot.png"
   ```
   - Example: `local screenshotPath = "/Users/yourname/Documents/LLM-Pokemon-Blue/data/screenshots/screenshot.png"`

5. **Run in the correct order**:
   - Start mGBA and load your Pokémon Blue ROM from `~/Downloads/ROM/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).sgb`
   - Start playing the game
   - In a separate terminal, run the controller:
   ```bash
   conda activate blue
   python local_controller.py
   ```
   - Return to mGBA, open Tools > Script Viewer
   - Load and run the `script.lua` file
   
   This sequence is important! The controller must be running before you activate the Lua script.

## Key Improvements in This Version

- **Request-based Screenshot System**: The controller explicitly requests screenshots when it's ready to process them, instead of using a timer-based approach
- **Enhanced Game State Tracking**: Captures player direction, position, and map ID for more informed decision making
- **Rate Limiting**: Properly implements cooldown between API calls to prevent rate limit issues
- **Memory Management**: Improved short-term and long-term memory systems to help the AI make more consistent decisions
- **Image Enhancement**: Screenshots are processed to improve visibility and detail recognition
- **Synchronization**: Better communication flow between emulator and controller

## Supported Local Providers

- LM Studio at `http://127.0.0.1:1234/v1`
- Ollama's OpenAI-compatible endpoint at `http://100.87.135.76:11434/v1`
- Custom local servers that accept OpenAI-compatible image messages at `/v1/chat/completions`

## Tips

- Use a vision-capable model. If your model cannot understand images, the controller will receive unusable decisions.
- Local models often do not support native tool calls, so the controller asks for strict JSON and converts it into button/notepad actions.
- Adjust `decision_cooldown` based on your local model speed. Start with 5 seconds and increase it if your server falls behind.
- If LM Studio returns model-not-found errors, copy the exact model id shown in the LM Studio server page into `model_name`.

## Contributing

Contributions welcome! You can:
- Improve the code
- Add support for more LLMs
- Share benchmark results
- Create visualization tools

## License

MIT
