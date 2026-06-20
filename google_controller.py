#!/usr/bin/env python3
import os
import socket
import time
import threading
import PIL.Image
import signal
import sys
import atexit
import argparse
import json
from collections import deque
from typing import Dict, List, Any, Tuple

# Import from your existing modules
from local_llm_client import create_local_llm_client, create_local_llm_client_for_provider
from pokemon_logger import PokemonLogger

class Tool:
    """Simple class to define a tool for the LLM"""
    def __init__(self, name: str, description: str, parameters: List[Dict[str, Any]]):
        self.name = name
        self.description = description
        self.parameters = parameters
    
    def to_gemini_format(self) -> Dict[str, Any]:
        """Convert to Gemini's expected format"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    p["name"]: {
                        "type": p["type"],
                        "description": p["description"]
                    } for p in self.parameters
                },
                "required": [p["name"] for p in self.parameters if p.get("required", False)]
            }
        }

class ToolCall:
    """Represents a tool call from the LLM"""
    def __init__(self, id: str, name: str, arguments: Dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments

class GeminiClient:
    """Client specifically for communicating with Gemini"""
    def __init__(self, api_key: str, model_name: str, max_tokens: int = 1024, game_title: str = "Pokémon Blue"):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.game_title = game_title
        self._setup_client()
    
    def _setup_client(self):
        """Set up the Gemini client"""
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        self.client = genai
    
    def call_with_tools(self, message: str, tools: List[Tool], images: List[PIL.Image.Image] = None) -> Tuple[Any, List[ToolCall], str]:
        """
        Call Gemini with the given message and tools, optionally including images
        """
        import google.generativeai as genai
        
        provider_tools = [tool.to_gemini_format() for tool in tools]
        
        model = self.client.GenerativeModel(model_name=self.model_name)
        
        system_message = f"""
        You are playing {self.game_title}. Your job is to press buttons to control the game.
        
        IMPORTANT: After analyzing the screenshot, you MUST use the press_button function.
        You are REQUIRED to use the press_button function with every response.
        
        NEVER just say what button to press - ALWAYS use the press_button function to actually press it.
        """
        
        chat = model.start_chat(
            history=[
                {"role": "user", "parts": [system_message]},
                {"role": "model", "parts": ["I understand. For every screenshot, I will use the press_button function to specify which button to press (A, B, UP, DOWN, etc.)."]}
            ]
        )
        
        enhanced_message = f"{message}\n\nIMPORTANT: You MUST use the press_button function. Select which button to press (A, B, UP, DOWN, LEFT, RIGHT, START or SELECT)."
        
        content_parts = [enhanced_message]
        
        if images:
            for image in images:
                content_parts.append(image)
        
        response = chat.send_message(
            content=content_parts,
            generation_config={
                "max_output_tokens": self.max_tokens,
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 0
            },
            tools={"function_declarations": provider_tools}
        )
        
        return response, self._parse_tool_calls(response), self._extract_text(response)
    
    def _parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """Parse tool calls from Gemini's response"""
        tool_calls = []
        
        try:
            if hasattr(response, "candidates"):
                for candidate in response.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                if hasattr(part.function_call, "name") and part.function_call.name:
                                    args = {}
                                    if hasattr(part.function_call, "args") and part.function_call.args is not None:
                                        try:
                                            if hasattr(part.function_call.args, "items"):
                                                for key, value in part.function_call.args.items():
                                                    args[key] = str(value)
                                            else:
                                                args = {"argument": str(part.function_call.args)}
                                        except:
                                            pass
                                    
                                    tool_calls.append(ToolCall(
                                        id=f"call_{len(tool_calls)}",
                                        name=part.function_call.name,
                                        arguments=args
                                    ))
        except Exception as e:
            print(f"Error parsing Gemini tool calls: {e}")
            import traceback
            print(traceback.format_exc())
        
        for call in tool_calls:
            print(f"Tool call: {call.name}, args: {call.arguments}")
        
        return tool_calls
    
    def _extract_text(self, response: Any) -> str:
        """Extract text from the Gemini response"""
        try:
            if hasattr(response, "text"):
                return response.text
            if hasattr(response, "candidates") and response.candidates:
                text_parts = []
                for candidate in response.candidates:
                    if hasattr(candidate, "content") and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                text_parts.append(part.text)
                if text_parts:
                    return "\n".join(text_parts)
        except:
            pass
        
        return ""

class PokemonController:
    def __init__(self, config_path='config.json'):
        self._cleanup_done = False
        self._cleanup_lock = threading.Lock()
        
        # Load config directly from JSON file
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"Failed to load config from {config_path}: {e}")
            sys.exit(1)
        
        # Ensure paths are absolute
        if 'notepad_path' in self.config and not os.path.isabs(self.config['notepad_path']):
            self.config['notepad_path'] = os.path.abspath(self.config['notepad_path'])
            
        if 'screenshot_path' in self.config and not os.path.isabs(self.config['screenshot_path']):
            self.config['screenshot_path'] = os.path.abspath(self.config['screenshot_path'])
        
        self.game_title = self.config.get("game_title", "Pokémon Blue")
        self.llm_client = create_local_llm_client(self.config, game_title=self.game_title)
        self.battle_llm_client = None
        self.battle_llm_provider = self.config.get("battle_llm_provider")
        if self.battle_llm_provider:
            self.battle_llm_client = create_local_llm_client_for_provider(
                self.config,
                self.battle_llm_provider,
                game_title=self.game_title
            )
        
        self.server_socket = None
        self.tools = self._define_tools()
        
        self.notepad_path = self.config['notepad_path']
        self.screenshot_path = self.config['screenshot_path']
        self.current_client = None
        self.running = True
        self.decision_cooldown = self.config['decision_cooldown']
        self.client_threads = []
        self.debug_mode = self.config.get('debug_mode', False)
        
        # Game state tracking
        self.player_direction = "UNKNOWN"
        self.player_x = 0
        self.player_y = 0
        self.map_id = 0
        
        # Processing state flags
        self.is_processing = False
        self.emulator_ready = False
        
        # Modified: Store timestamp, button, full reasoning text, and position/direction
        self.recent_actions = deque(maxlen=10)
        
        os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.screenshot_path), exist_ok=True)
        
        self.logger = PokemonLogger(debug_mode=self.debug_mode)
        self.initialize_notepad()
        
        self.logger.info("Controller initialized")
        self.logger.info(
            f"LLM provider: {self.config.get('llm_provider')} "
            f"({self.llm_client.model_name} at {self.llm_client.base_url})"
        )
        if self.battle_llm_client:
            self.logger.info(
                f"Battle escalation provider: {self.battle_llm_provider} "
                f"({self.battle_llm_client.model_name} at {self.battle_llm_client.base_url})"
            )
        self.logger.debug(f"Notepad path: {self.notepad_path}")
        self.logger.debug(f"Screenshot path: {self.screenshot_path}")
        
        self.setup_socket()
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        atexit.register(self.cleanup)

    def _define_tools(self) -> List[Tool]:
        """Define the tools needed for the Pokémon game controller"""
        press_button = Tool(
            name="press_button",
            description="Press a button on the Game Boy emulator to control the game",
            parameters=[{
                "name": "button",
                "type": "string",
                "description": "Button to press (A, B, START, SELECT, UP, DOWN, LEFT, RIGHT, R, L)",
                "required": True,
                "enum": ["A", "B", "SELECT", "START", "RIGHT", "LEFT", "UP", "DOWN", "R", "L"]
            }]
        )
        
        update_notepad = Tool(
            name="update_notepad",
            description="Update the AI's long-term memory with new information about the game state",
            parameters=[{
                "name": "content",
                "type": "string",
                "description": "Content to add to the notepad. Only include important information about game progress, objectives, or status.",
                "required": True
            }]
        )
        
        return [press_button, update_notepad]

    def setup_socket(self):
        """Set up the socket server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            try:
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
            except (AttributeError, OSError):
                self.logger.debug("TCP keepalive options not fully supported")
            
            try:
                self.server_socket.bind((self.config['host'], self.config['port']))
            except socket.error:
                self.logger.warning(f"Port {self.config['port']} in use. Attempting to free it...")
                os.system(f"lsof -ti:{self.config['port']} | xargs kill -9")
                time.sleep(1)
                self.server_socket.bind((self.config['host'], self.config['port']))
            
            self.server_socket.listen(1)
            self.server_socket.settimeout(1)
            self.logger.success(f"Socket server set up on {self.config['host']}:{self.config['port']}")
        except socket.error as e:
            self.logger.error(f"Socket setup error: {e}")
            sys.exit(1)

    def signal_handler(self, sig, frame):
        """Handle termination signals"""
        print(f"\nReceived signal {sig}. Shutting down server...")
        self.running = False
        self.cleanup()
        sys.exit(0)
        
    def cleanup(self):
        """Clean up resources"""
        with self._cleanup_lock:
            if self._cleanup_done:
                return
            self._cleanup_done = True
            
            self.logger.section("Cleaning up resources...")
            if self.current_client:
                try:
                    self.current_client.close()
                    self.current_client = None
                except:
                    pass
            if self.server_socket:
                try:
                    self.server_socket.close()
                    self.server_socket = None
                except:
                    pass
            self.logger.success("Cleanup complete")
            time.sleep(0.5)

    def initialize_notepad(self):
        """Initialize the notepad file with clear game objectives"""
        if not os.path.exists(self.notepad_path):
            os.makedirs(os.path.dirname(self.notepad_path), exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.notepad_path, 'w') as f:
                f.write(f"# {self.game_title} Game Progress\n\n")
                f.write(f"Game started: {timestamp}\n\n")
                f.write("## Current Objectives\n")
                f.write("- Play Pokémon Blue from whatever screen or save state is currently loaded.\n")
                f.write("- Make steady game progress: start or continue the game, navigate overworld areas, advance dialogue, battle when required, and pursue story/exploration objectives.\n")
                f.write("- Avoid loops by changing strategy when repeated inputs do not change the screen.\n\n")
                f.write("## Current Location\n- Unknown; infer from the current screenshot and game state.\n\n")
                f.write("## Game Progress\n- Unknown; infer from the current screenshot and update these notes as new facts are discovered.\n\n")
                f.write("## Items\n- Unknown.\n\n")
                f.write("## Pokémon Team\n- Unknown.\n\n")

    def read_notepad(self):
        """Read the current notepad content"""
        try:
            with open(self.notepad_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading notepad: {e}")
            return "Error reading notepad"

    def update_notepad(self, new_content):
        """Update the notepad"""
        try:
            current_content = self.read_notepad()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            updated_content = current_content + f"\n## Update {timestamp}\n{new_content}\n"
            with open(self.notepad_path, 'w') as f:
                f.write(updated_content)
            self.logger.debug("Notepad updated")
            if len(updated_content) > 10000:
                self.summarize_notepad()
        except Exception as e:
            self.logger.error(f"Error updating notepad: {e}")

    def summarize_notepad(self):
        """Summarize the notepad when it gets too long"""
        try:
            self.logger.info("Notepad is getting large, summarizing...")
            notepad_content = self.read_notepad()
            summarize_prompt = """
            Please summarize the following game notes into a more concise format.
            Maintain these key sections:
            - Current Status
            - Game Progress
            - Important Items
            - Pokemon Team
            Remove redundant information while preserving all important game state details.
            Format the response as a well-structured markdown document.
            Here are the notes to summarize:
            """
            response, _, text = self.llm_client.call_with_tools(
                message=summarize_prompt + notepad_content,
                tools=[]
            )
            if text:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                summary = f"# Pokémon Game AI Notepad (Summarized)\n\n"
                summary += f"Last summarized: {timestamp}\n\n"
                summary += text
                with open(self.notepad_path, 'w') as f:
                    f.write(summary)
                self.logger.success("Notepad summarized successfully")
        except Exception as e:
            self.logger.error(f"Error summarizing notepad: {e}")

    def get_recent_actions_text(self):
        """Get formatted text of recent actions with reasoning and position/direction"""
        if not self.recent_actions:
            return "No recent actions."
        
        recent_actions_text = "## Short-term Memory (Recent Actions and Reasoning):\n"
        for i, (timestamp, button, reasoning, direction, x, y, map_id) in enumerate(self.recent_actions, 1):
            recent_actions_text += f"{i}. [{timestamp}] Pressed {button} while facing {direction} at position ({x}, {y}) on map {map_id}\n"
            recent_actions_text += f"   Reasoning: {reasoning.strip()}\n\n"
        return recent_actions_text

    def get_repeat_warning_text(self):
        """Warn the model when the same button is not changing the game state."""
        if not self.recent_actions:
            return ""

        same_state_actions = [
            action for action in reversed(self.recent_actions)
            if action[3] == self.player_direction
            and action[4] == self.player_x
            and action[5] == self.player_y
            and action[6] == self.map_id
        ]

        if len(same_state_actions) < 2:
            return ""

        last_button = same_state_actions[0][1]
        repeated_count = 0
        for action in same_state_actions:
            if action[1] == last_button:
                repeated_count += 1
            else:
                break

        if repeated_count < 2:
            return ""

        warning = f"""
        ## Repeated Input Warning:
        - You pressed {last_button} {repeated_count} times in a row without changing position/map/state.
        - Do NOT choose {last_button} again unless the screenshot clearly changed.
        - Pick a different button that can change the screen.
        """

        return warning

    def crop_game_viewport(self, image):
        """Remove the Super Game Boy border so the model sees only gameplay."""
        if not self.config.get("crop_sgb_border", True):
            return image

        width, height = image.size
        if width == 256 and height == 224:
            self.logger.debug("Cropping Super Game Boy border from screenshot")
            return image.crop((48, 40, 208, 184))

        return image

    def extract_decision_json(self, text):
        """Extract the local-model JSON decision for routing/escalation."""
        if not text:
            return {}

        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.replace("```json", "", 1).replace("```", "", 1).strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

        import re
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def maybe_escalate_battle_decision(self, primary_text, recent_actions, notepad_content):
        """Use a stronger text model for battle judgment after vision identifies a battle."""
        if not self.battle_llm_client:
            return None, [], ""

        decision = self.extract_decision_json(primary_text)
        if decision.get("screen_type", "").lower() != "battle":
            return None, [], ""

        self.logger.section("Escalating battle decision to stronger text model")
        battle_prompt = f"""
        You are deciding a Pokémon Blue battle action. Another vision model already inspected the screenshot.

        ## Vision Model's Current Screen Summary
        {primary_text}

        ## Battle Decision Rules
        - Return ONLY valid JSON.
        - Choose exactly one button: A, B, START, SELECT, UP, DOWN, LEFT, RIGHT.
        - If the cursor is already on the best option, choose A.
        - Safari Zone battle menu: BALL is usually the best default for catching, BAIT can reduce fleeing, ROCK can make catching easier but increases fleeing, RUN exits.
        - If text/dialogue is waiting after a thrown ball or battle message, choose A to advance.
        - Do not choose movement buttons unless you are moving a visible battle/menu cursor.

        {recent_actions}

        ## Long-term Memory
        {notepad_content}
        """

        response, tool_calls, text = self.battle_llm_client.call_with_tools(
            message=battle_prompt,
            tools=self.tools,
            images=None
        )
        if not text:
            self.logger.warning(f"Battle escalation returned empty response: {json.dumps(response)[:1000]}")
        else:
            print(f"Battle LLM Text Response: {text}")
        return response, tool_calls, text

    def get_direction_guidance_text(self):
        """Generate guidance text about player orientation and interactions"""
        directions = {
            "UP": "north",
            "DOWN": "south", 
            "LEFT": "west",
            "RIGHT": "east"
        }
        
        facing_direction = directions.get(self.player_direction, self.player_direction)
        
        guidance = f"""
        ## Navigation Tips:
        - To INTERACT with objects or NPCs, you MUST be FACING them and then press A
        - Your current direction is {self.player_direction} (facing {facing_direction})
        - Your current position is (X={self.player_x}, Y={self.player_y}) on map {self.map_id}
        - If you need to face a different direction, press the appropriate directional button first
        - In buildings, look for exits via stairs, doors, or red mats and walk directly over them
        """
        
        return guidance

    def get_map_name(self, map_id):
        """Get map name from ID, with fallback for unknown maps"""
        # Pokémon Blue map IDs (incomplete, add more as needed)
        map_names = {
            0: "Pallet Town",
            1: "Viridian City",
            2: "Pewter City",
            3: "Cerulean City",
            12: "Route 1",
            13: "Route 2",
            14: "Route 3",
            15: "Route 4",
            37: "Player's House 1F",
            38: "Player's House 2F",
            39: "Blue's House",
            40: "Oak's Lab",
            # Add more map IDs as you explore the game
        }
        
        return map_names.get(map_id, f"Unknown Area (Map ID: {map_id})")

    def process_screenshot(self, screenshot_path=None):
        """Process a screenshot with enhanced game state information"""
        if self.is_processing:
            self.logger.debug("Already processing a decision, skipping")
            return None
            
        self.is_processing = True
        try:
            notepad_content = self.read_notepad()
            recent_actions = self.get_recent_actions_text()
            repeat_warning = self.get_repeat_warning_text()
            direction_guidance = self.get_direction_guidance_text()
            current_map = self.get_map_name(self.map_id)
            
            path_to_use = screenshot_path if screenshot_path else self.screenshot_path
            
            if not os.path.exists(path_to_use):
                self.logger.error(f"Screenshot not found at {path_to_use}")
                self.is_processing = False
                return None
            
            # Load and enhance the image
            original_image = self.crop_game_viewport(PIL.Image.open(path_to_use))
            
            # Scale the image to 3x its original size for better detail recognition
            scale_factor = 3
            scaled_width = original_image.width * scale_factor
            scaled_height = original_image.height * scale_factor
            scaled_image = original_image.resize((scaled_width, scaled_height), PIL.Image.LANCZOS)
            
            # Enhance contrast for better visibility
            from PIL import ImageEnhance
            contrast_enhancer = ImageEnhance.Contrast(scaled_image)
            contrast_image = contrast_enhancer.enhance(1.5)  # Increase contrast by 50%
            
            # Enhance color saturation for better color visibility
            saturation_enhancer = ImageEnhance.Color(contrast_image)
            enhanced_image = saturation_enhancer.enhance(1.8)  # Increase saturation by 80%
            
            # Optionally enhance brightness slightly
            brightness_enhancer = ImageEnhance.Brightness(enhanced_image)
            final_image = brightness_enhancer.enhance(1.1)  # Increase brightness by 10%
            
            prompt = f"""
            You are an AI playing {self.game_title}, you are the player character with the cap. Look at this screenshot and choose ONE button to press.
            
            ## Current Location
            You are in {current_map}
            Position: X={self.player_x}, Y={self.player_y}
            
            ## Current Direction
            You are facing: {self.player_direction}

            ## Overall Goal:
            Play Pokémon Blue competently from the current screen, whether this is a new game, a loaded save, a menu, dialogue, battle, or overworld exploration.
            Make practical progress from what is visible now. Do not assume a fixed starting location or fixed save state.

            ## First classify the screen:
            - title: title/logo/start screen. Press START to begin or continue.
            - menu: a menu or option list is open. Use UP/DOWN to choose, A to confirm, B to cancel if stuck.
            - dialogue: a text box is visible. Press A to advance.
            - naming: a keyboard/name-entry screen is visible. Navigate letters carefully and press A only on the intended letter or END.
            - battle: a Pokémon battle menu is visible. Choose sensible battle actions; A confirms, directions move the cursor.
            - overworld: the player sprite is visible in the world. Prefer movement, exploration, exits, paths, doors, stairs, items, NPCs, and signs.
            - unknown: choose the safest input that reveals more information, usually A for text/prompt screens or movement for overworld-like screens.
            
            ## Controls:
            - A: To talk to people, interact with objects, confirm menu choices, or advance dialogue text (NOT for walking, and NOT for entering/exiting buildings)
            - B: To cancel or go back
            - UP, DOWN, LEFT, RIGHT: To move your character (use these to enter/exit buildings)
            - START: To open the main menu
            - SELECT: Rarely used special function
            
            ## Screen Interpretation Rules:
            - Ignore any decorative Super Game Boy border around the gameplay screen.
            - The word BLUE or Pokémon pictures in the outer border are not the title screen.
            - Decide from the inner gameplay viewport only.
            - If the player is standing in grass or on a path, prefer movement buttons.
            - Do not press A repeatedly unless there is dialogue, a menu prompt, or an object/NPC directly in front of the player.
            - If there is no menu/dialogue text box, A usually does nothing in open terrain.
            - In open terrain, choose UP/DOWN/LEFT/RIGHT based on visible paths and obstacles.
            
            ## Name Entry Screen Guide:
            - The cursor is a BLACK TRIANGLE/POINTER (▶) on the left side of the currently selected letter
            - The letter that will be selected is the one the BLACK TRIANGLE is pointing to
            - To navigate to a different letter, use UP, DOWN, LEFT, RIGHT buttons
            - To enter a letter, press A when the cursor is pointing to that letter
            - The keyboard layout is as follows:
            ROW 1: A B C D E F G H I
            ROW 2: J K L M N O P Q R
            ROW 3: S T U V W X Y Z
            ROW 4: Special characters
            ROW 5: END (bottom right)

            ## URGENT WARNING: DO NOT PRESS A UNLESS YOU ARE ON THE CORRECT LETTER!
            
            ## Navigation Rules:
            - In overworld only: if you've pressed the same movement button 3+ times with no position/map change, try a different direction.
            - In overworld only: if A did not change anything, do not press A again. Move instead.
            - In battle, dialogue, naming, and menus, the player's X/Y position usually will not change; do not treat unchanged position as failure.
            - In Safari Zone battles, repeatedly choosing BALL with A can be correct while Safari Balls remain.
            - Prefer unexplored walkable openings over standing still or interacting with empty space.
            - You must be DIRECTLY ON TOP of exits (red mats, doors, stairs) to use them
            - Light gray or black space is NOT walkable - it's a wall/boundary you need to use the exits (red mats, doors, stairs)
            - To INTERACT with objects or NPCs, you MUST be FACING them and then press A
            - When you enter a new area or discover something important, UPDATE THE NOTEPAD using the update_notepad function
            
            {recent_actions}

            {repeat_warning}
            
            {direction_guidance}
            
            ## Long-term Memory (Game State):
            {notepad_content}
            
            IMPORTANT: After each significant change (entering new area, talking to someone, finding items), use the update_notepad function to record what you learned or where you are.
            
            ## IMPORTANT INSTRUCTIONS:
            1. FIRST, provide a SHORT paragraph (2-3 sentences) describing what you see in the screenshot.
            2. THEN, provide a BRIEF explanation of what you plan to do and why.
            3. FINALLY, use the press_button function to execute your decision.
            """
            
            images = [final_image]
            self.logger.section(f"Requesting decision from LLM")
            
            response, tool_calls, text = self.llm_client.call_with_tools(
                message=prompt,
                tools=self.tools,
                images=images
            )
            
            print(f"LLM Text Response: {text}")
            if not text:
                self.logger.warning(f"Primary LLM returned empty response: {json.dumps(response)[:1000]}")

            battle_response, battle_tool_calls, battle_text = self.maybe_escalate_battle_decision(
                text,
                recent_actions,
                notepad_content
            )
            if battle_tool_calls:
                tool_calls = battle_tool_calls
                text = battle_text or text
            
            button_code = None
            
            for call in tool_calls:
                if call.name == "update_notepad":
                    content = call.arguments.get("content", "")
                    if content:
                        self.update_notepad(content)
                        print(f"Updated notepad with: {content[:50]}...")
                
                elif call.name == "press_button":
                    button = call.arguments.get("button", "").upper()
                    button_map = {
                        "A": 0, "B": 1, "SELECT": 2, "START": 3,
                        "RIGHT": 4, "LEFT": 5, "UP": 6, "DOWN": 7,
                        "R": 8, "L": 9
                    }
                    
                    if button in button_map:
                        button_code = button_map[button]
                        self.logger.success(f"Tool used button: {button}")
                        
                        # Store timestamp, button, reasoning, and position/direction
                        timestamp = time.strftime("%H:%M:%S")
                        self.recent_actions.append(
                            (timestamp, button, text, self.player_direction, 
                            self.player_x, self.player_y, self.map_id)
                        )
                        
                        self.logger.ai_action(button, button_code)
                        return {'button': button_code}
            
            if button_code is None:
                self.logger.warning("No press_button tool call found!")
                return None
            
        except Exception as e:
            self.logger.error(f"Error processing screenshot: {e}")
            if self.debug_mode:
                import traceback
                self.logger.debug(traceback.format_exc())
        finally:
            self.is_processing = False
        return None

    def handle_client(self, client_socket, client_address):
        """Handle communication with the emulator client"""
        self.logger.section(f"Connected to emulator at {client_address}")
        self.current_client = client_socket
        self.last_decision_time = 0  # Track the time of last decision
        
        self.logger.game_state("Waiting for game data...")
        
        while self.running:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                message = data.decode('utf-8').strip()
                parts = message.split("||")
                
                if len(parts) >= 2:
                    message_type = parts[0]
                    content = parts[1:]  # Get all remaining parts
                    
                    # Handle the "ready" message from the emulator
                    if message_type == "ready":
                        self.logger.game_state("Emulator is ready for next command")
                        self.emulator_ready = True
                        
                        # Check if cooldown period has passed
                        current_time = time.time()
                        time_since_last_decision = current_time - self.last_decision_time
                        
                        if time_since_last_decision < self.decision_cooldown:
                            wait_time = self.decision_cooldown - time_since_last_decision
                            self.logger.debug(f"Waiting {wait_time:.2f}s for cooldown before next request")
                            time.sleep(wait_time)
                        
                        # Request a screenshot if we're not currently processing one
                        if not self.is_processing:
                            try:
                                self.logger.debug("Requesting screenshot from emulator")
                                client_socket.send(b'request_screenshot\n')
                            except Exception as e:
                                self.logger.error(f"Failed to request screenshot: {e}")
                    
                    # Handle the screenshot_with_state message type
                    elif message_type == "screenshot_with_state":
                        self.logger.game_state("Received new screenshot with game state from emulator")
                        
                        # Parse the content which now includes game state
                        if len(content) >= 5:  # Path, direction, x, y, mapId
                            screenshot_path = content[0]
                            self.player_direction = content[1]
                            self.player_x = int(content[2])
                            self.player_y = int(content[3])
                            self.map_id = int(content[4])
                            
                            self.logger.debug(f"Game State: Direction={self.player_direction}, " +
                                             f"Position=({self.player_x}, {self.player_y}), " +
                                             f"Map ID={self.map_id}")
                        
                            # Verify the file exists
                            if os.path.exists(screenshot_path):
                                # Process the screenshot with game state info
                                decision = self.process_screenshot(screenshot_path)
                                
                                if decision and decision.get('button') is not None:
                                    try:
                                        button_code = str(decision['button'])
                                        self.logger.debug(f"Sending button code to emulator: {button_code}")
                                        client_socket.send(button_code.encode('utf-8') + b'\n')
                                        self.logger.success("Button command sent to emulator")
                                        self.emulator_ready = False
                                        
                                        # Update the last decision time
                                        self.last_decision_time = time.time()
                                    except Exception as e:
                                        self.logger.error(f"Failed to send button command: {e}")
                                        break
                                else:
                                    # If no decision was made, we still need to respect the cooldown
                                    self.last_decision_time = time.time()
                                    
                                    # Request another screenshot after a small delay
                                    try:
                                        time.sleep(0.5)  # Small delay to avoid flooding
                                        client_socket.send(b'request_screenshot\n')
                                    except Exception as e:
                                        self.logger.error(f"Failed to request another screenshot: {e}")
                            else:
                                self.logger.error(f"Screenshot file not found at {screenshot_path}")
                
            except socket.error as e:
                if e.args[0] != socket.EWOULDBLOCK and str(e) != 'Resource temporarily unavailable':
                    self.logger.error(f"Socket error: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Error handling client: {e}")
                if self.debug_mode:
                    import traceback
                    self.logger.debug(traceback.format_exc())
                if not self.running:
                    break
                continue
            
            # Add a small delay to avoid CPU spinning
            time.sleep(0.01)
        
        self.logger.section(f"Disconnected from emulator at {client_address}")
        self.current_client = None
        try:
            client_socket.close()
        except:
            pass

    def handle_client_connection(self, client_socket, client_address):
        """Wrapper around handle_client"""
        try:
            self.handle_client(client_socket, client_address)
        except Exception as e:
            self.logger.error(f"Client connection error: {e}")
        finally:
            if client_socket:
                try:
                    client_socket.close()
                except:
                    pass
            if self.current_client == client_socket:
                self.current_client = None

    def start(self):
        """Start the controller server"""
        self.logger.header(f"Starting Pokémon Game Controller")
        
        try:
            while self.running:
                try:
                    self.logger.section("Waiting for emulator connection...")
                    client_socket, client_address = self.server_socket.accept()
                    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    try:
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
                        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 6)
                    except (AttributeError, OSError):
                        pass
                    
                    client_socket.setblocking(0)
                    client_thread = threading.Thread(
                        target=self.handle_client_connection,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    self.client_threads.append(client_thread)
                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    self.logger.section("Keyboard interrupt detected. Shutting down...")
                    break
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error in main loop: {e}")
                        if self.debug_mode:
                            import traceback
                            self.logger.debug(traceback.format_exc())
                        time.sleep(1)
        finally:
            self.running = False
            self.logger.section("Closing all client connections...")
            for t in self.client_threads:
                try:
                    t.join(timeout=1)
                except:
                    pass
            self.cleanup()
            self.logger.success("Server shut down cleanly")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pokémon Game AI Controller")
    parser.add_argument("--config", "-c", default="config.json", help="Path to the configuration file")
    args = parser.parse_args()
    
    controller = PokemonController(args.config)
    try:
        controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()
