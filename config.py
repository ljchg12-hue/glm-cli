"""Configuration management for GLM CLI"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG = {
    "model": "glm-4.7",
    "api_base": "https://api.z.ai/api/anthropic/v1",
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": True,
    "history_size": 100,
    "theme": "default",
    "auto_update_check": True,
    "update_check_interval": 86400,  # 24 hours in seconds
}

class Config:
    """Configuration manager for GLM CLI"""

    def __init__(self):
        self.config_dir = Path.home() / ".glm"
        self.config_file = self.config_dir / "config.json"
        self.history_dir = self.config_dir / "history"
        self.sessions_dir = self.config_dir / "sessions"
        self._config: Dict[str, Any] = {}
        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self):
        """Ensure all necessary directories exist"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._config = {}

        # Merge with defaults
        for key, value in DEFAULT_CONFIG.items():
            if key not in self._config:
                self._config[key] = value

    def save(self):
        """Save configuration to file"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value"""
        self._config[key] = value
        self.save()

    def get_api_key(self) -> Optional[str]:
        """Get API key from environment or config"""
        return (
            os.environ.get("ZAI_API_KEY") or
            os.environ.get("GLM_API_KEY") or
            os.environ.get("ZHIPU_API_KEY") or
            self._config.get("api_key")
        )

    def validate_api_key(self) -> tuple[bool, str]:
        """Validate API key format and presence

        Returns:
            tuple: (is_valid, message)
        """
        api_key = self.get_api_key()

        if not api_key:
            return False, "API key not found. Set ZAI_API_KEY, GLM_API_KEY, or ZHIPU_API_KEY environment variable."

        if len(api_key) < 20:
            return False, "API key appears to be too short. Please check your key."

        # Check for common placeholder patterns
        placeholders = ["your_api_key", "xxx", "test", "placeholder", "example"]
        if any(p in api_key.lower() for p in placeholders):
            return False, "API key appears to be a placeholder. Please set a valid key."

        return True, "API key validated"

    def has_api_key(self) -> bool:
        """Check if API key is available"""
        return bool(self.get_api_key())

    @property
    def model(self) -> str:
        return self._config.get("model", "glm-4.7")

    @property
    def api_base(self) -> str:
        return self._config.get("api_base", DEFAULT_CONFIG["api_base"])

    @property
    def all(self) -> Dict[str, Any]:
        """Return all configuration"""
        return self._config.copy()


# Global config instance
config = Config()
