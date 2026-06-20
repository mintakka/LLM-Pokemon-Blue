#!/usr/bin/env python3
from abc import ABC, abstractmethod
from PIL import Image
import os
import sys
import traceback

class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    def __init__(self, config):
        self.config = config
        self.provider_name = "base"
    
    @abstractmethod
    def initialize(self):
        """Initialize the LLM client with API key and configuration"""
        pass
    
    @abstractmethod
    def generate_content(self, prompt, images=None):
        """
        Generate content using the LLM
        
        Args:
            prompt (str): The text prompt
            images (list): Optional list of image paths or PIL Image objects
            
        Returns:
            str: The generated text response
        """
        pass
    
    def get_provider_name(self):
        """Get the name of the provider for prompt templating"""
        return self.provider_name
    
    def get_model_name(self):
        """Get the model name being used"""
        return self.config.get("model_name", "unknown model")


class GoogleProvider(LLMProvider):
    """Google's google LLM provider implementation"""
    
    def __init__(self, config):
        super().__init__(config)
        self.provider_name = "google"
        self.model = None
    
    def initialize(self):
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.config["api_key"])
            self.model = genai.GenerativeModel(self.config["model_name"])
            return True
        except Exception as e:
            print(f"Error initializing google: {e}")
            return False
    
    def generate_content(self, prompt, images=None):
        try:
            if not self.model:
                if not self.initialize():
                    return "Error: google model not initialized"
            
            # Prepare the content parts
            content_parts = [prompt]
            
            # Add images if provided
            if images:
                for img in images:
                    if isinstance(img, str) and os.path.exists(img):
                        img = Image.open(img)
                    if isinstance(img, Image.Image):
                        content_parts.append(img)
            
            # Generate the response
            response = self.model.generate_content(content_parts)
            
            if response:
                return response.text
            return "No response from google"
            
        except Exception as e:
            print(f"Error generating content with google: {e}")
            return f"Error: {str(e)}"


class OpenAIProvider(LLMProvider):
    """OpenAI's GPT LLM provider implementation"""
    
    def __init__(self, config):
        super().__init__(config)
        self.provider_name = "GPT"
        self.client = None
    
    def initialize(self):
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.config["api_key"])
            return True
        except Exception as e:
            print(f"Error initializing OpenAI: {e}")
            return False
    
    def generate_content(self, prompt, images=None):
        try:
            if not self.client:
                if not self.initialize():
                    return "Error: OpenAI client not initialized"
            
            # Handle text-only prompt
            if not images:
                response = self.client.chat.completions.create(
                    model=self.config["model_name"],
                    messages=[
                        {"role": "system", "content": f"You are an AI playing {self.config.get('game_title', 'Pokémon Blue')}."},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.choices[0].message.content
            
            # Add a small delay to ensure images are fully written
            import time
            time.sleep(0.1)
            
            # Prepare content for API - start with text
            message_content = [{"type": "text", "text": prompt}]
            
            # Only use the current (first) image for reliability
            if images and len(images) > 0:
                try:
                    current_img = images[0]
                    
                    # Process the image
                    import io
                    import base64
                    
                    # Convert to PNG in memory
                    if isinstance(current_img, Image.Image):
                        buffer = io.BytesIO()
                        current_img.save(buffer, format="PNG")
                        buffer.seek(0)
                        base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
                        
                        # Add to message content
                        message_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "low"
                            }
                        })
                except Exception as img_error:
                    print(f"Error processing current image: {img_error}")
            
            # Make the API call
            response = self.client.chat.completions.create(
                model=self.config["model_name"],
                messages=[
                    {"role": "system", "content": f"You are an AI playing {self.config.get('game_title', 'Pokémon Blue')}."},
                    {"role": "user", "content": message_content}
                ]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Error generating content with OpenAI: {e}")
            
            # Fall back to text-only if there's an error
            if images:
                try:
                    return self.generate_content(prompt + "\n[Note: Image could not be processed]", None)
                except:
                    pass
                    
            return f"Error: {str(e)}"


class AnthropicProvider(LLMProvider):
    """Anthropic's Claude LLM provider implementation"""
    
    def __init__(self, config):
        super().__init__(config)
        self.provider_name = "Claude"
        self.client = None
    
    def initialize(self):
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.config["api_key"])
            return True
        except Exception as e:
            print(f"Error initializing Anthropic: {e}")
            return False
    
    def generate_content(self, prompt, images=None):
        try:
            if not self.client:
                if not self.initialize():
                    return "Error: Anthropic client not initialized"
            
            # Set max tokens, defaulting to 1024 if not specified
            max_tokens = self.config.get("max_tokens", 1024)
            
            # Handle text-only prompt
            if not images:
                response = self.client.messages.create(
                    model=self.config["model_name"],
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text
            
            # Add a small delay to ensure images are fully written
            import time
            time.sleep(0.1)
            
            # Create message content with text and images
            content = []
            
            # Add text prompt
            content.append({
                "type": "text",
                "text": prompt
            })
            
            # Process and add images
            if images:
                for img in images:
                    try:
                        if isinstance(img, Image.Image):
                            # Convert PIL Image to base64
                            import io
                            import base64
                            
                            buffer = io.BytesIO()
                            img.save(buffer, format="PNG")
                            buffer.seek(0)
                            base64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
                            
                            content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": base64_image
                                }
                            })
                    except Exception as e:
                        print(f"Error processing image for Claude: {e}")
                        # Continue with other images if one fails
            
            # Make the API call
            response = self.client.messages.create(
                model=self.config["model_name"],
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": content}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            print(f"Error generating content with Anthropic: {e}")
            
            # Fall back to text-only if there's an error with images
            if images:
                try:
                    return self.generate_content(prompt + "\n[Note: Image processing failed]", None)
                except:
                    pass
                    
            return f"Error: {str(e)}"


# Factory function to get the right provider
def get_llm_provider(config):
    """
    Factory function to create the appropriate LLM provider
    
    Args:
        config (dict): Configuration for the LLM provider
        
    Returns:
        LLMProvider: An instance of the appropriate LLM provider
    """
    provider_name = config.get("llm_provider", "").lower()
    provider_config = config.get("providers", {}).get(provider_name, {})
    
    if not provider_config:
        print(f"Warning: No configuration found for provider '{provider_name}'")
        return None
    
    if provider_name == "google":
        return GoogleProvider(provider_config)
    elif provider_name == "openai":
        return OpenAIProvider(provider_config)
    elif provider_name == "anthropic":
        return AnthropicProvider(provider_config)
    else:
        print(f"Error: Unknown LLM provider '{provider_name}'")
        return None

# Quick test function if this module is run directly
if __name__ == "__main__":
    import json
    import argparse
    
    parser = argparse.ArgumentParser(description="Test LLM providers")
    parser.add_argument("--provider", "-p", choices=["google", "openai", "anthropic"], 
                        default="google", help="Provider to test")
    parser.add_argument("--config", "-c", default="config.json", help="Config file path")
    parser.add_argument("--prompt", default="Say hello and confirm you're working", 
                        help="Test prompt")
    
    args = parser.parse_args()
    
    try:
        # Load config
        with open(args.config, 'r') as f:
            config = json.load(f)
        
        # Override provider for testing
        config["llm_provider"] = args.provider
        
        # Get provider
        provider = get_llm_provider(config)
        if not provider:
            print(f"Failed to initialize {args.provider} provider")
            sys.exit(1)
            
        print(f"Testing {provider.get_provider_name()} ({provider.get_model_name()})...")
        
        # Generate response
        response = provider.generate_content(args.prompt)
        
        print("\n----- RESPONSE -----")
        print(response)
        print("----- END RESPONSE -----")
        
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)
