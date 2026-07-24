"""Hugging Face Spaces compatibility launcher."""

import os

from app.main import demo, launch


if __name__ == "__main__":
    hosted_space = bool(
        os.environ.get("SPACE_ID")
        or os.environ.get("SPACE_HOST")
        or os.environ.get("SPACE_REPO_NAME")
    )
    launch(inbrowser=not hosted_space)

