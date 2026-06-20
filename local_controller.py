#!/usr/bin/env python3
import argparse

from google_controller import PokemonController


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pokemon Game AI Controller")
    parser.add_argument("--config", "-c", default="config.json", help="Path to the configuration file")
    args = parser.parse_args()

    controller = PokemonController(args.config)
    try:
        controller.start()
    except KeyboardInterrupt:
        pass
    finally:
        controller.cleanup()
