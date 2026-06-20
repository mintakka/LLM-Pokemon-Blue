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

3. **LLM Provider** (Gemini) acts as the "brain":
   - Analyzes game screenshots with enhanced visibility
   - Uses game state context to make informed decisions
   - Decides which buttons to press
   - Updates the notepad to track progress

## Quick Setup

1. **Install dependencies**:
```bash
pip install "google-generativeai>=0.3.0" pillow openai anthropic python-dotenv
```

2. **Set up your config**:
   - Edit `config.json` with your Gemini API key and settings:
```json
{
  "game_title": "Pokémon Blue",
  "rom_path": "~/Downloads/ROM/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).sgb",
  "host": "127.0.0.1",
  "port": 8888,
  "decision_cooldown": 1.0,
  "screenshot_path": "data/screenshots/screenshot.png",
  "notepad_path": "data/notepad/game_memory.md",
  "debug_mode": true,
  "providers": {
    "google": {
      "api_key": "YOUR_GEMINI_API_KEY",
      "model_name": "gemini-2.0-flash",
      "max_tokens": 1024
    }
  }
}
```

3. **Update the Lua script path**:
   - Open `emulator/script.lua` in any text editor
   - Find and change the following line to match your system's full path:
   ```lua
   local screenshotPath = "/Users/matt/Projects/LLM-Pokemon-Blue/data/screenshots/screenshot.png"
   ```
   - Example: `local screenshotPath = "/Users/yourname/Documents/LLM-Pokemon-Blue/data/screenshots/screenshot.png"`

4. **Run in the correct order**:
   - Start mGBA and load your Pokémon Blue ROM from `~/Downloads/ROM/Pokemon - Blue Version (USA, Europe) (SGB Enhanced).sgb`
   - Start playing the game
   - In a separate terminal, run the controller:
   ```bash
   python google_controller.py
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

## Supported LLM Provider

- Google Gemini (gemini-2.0-flash)

*Note: This version currently only supports Google's Gemini API. Removed support for other LLM's while I solve it for Gemini as the API is free.*

## Tips

- Adjust the `decision_cooldown` in your config based on your Gemini API quota:
  - Recommended: 3-6 seconds for most Gemini API keys
  - If you encounter rate limiting: increase to 6+ seconds
- Consider API costs when running for extended time

## Contributing

Contributions welcome! You can:
- Improve the code
- Add support for more LLMs
- Share benchmark results
- Create visualization tools

## License

MIT
