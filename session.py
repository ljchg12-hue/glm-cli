"""Session and history management for GLM CLI"""

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from config import config


class Message:
    """A single message in the conversation"""

    def __init__(self, role: str, content: str, timestamp: Optional[float] = None):
        self.role = role
        self.content = content
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
        )

    def to_api_format(self) -> Dict[str, str]:
        """Convert to API format"""
        return {"role": self.role, "content": self.content}


class Session:
    """Manages a conversation session"""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.messages: List[Message] = []
        self.created_at = time.time()
        self.updated_at = time.time()
        self.model = config.model
        self.cwd = os.getcwd()

    @property
    def session_file(self) -> Path:
        """Get the session file path"""
        return config.sessions_dir / f"{self.session_id}.json"

    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the session"""
        msg = Message(role, content)
        self.messages.append(msg)
        self.updated_at = time.time()
        self.save()
        return msg

    def get_messages_for_api(self, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """Get messages in API format"""
        messages = self.messages
        if max_messages:
            messages = messages[-max_messages:]
        return [m.to_api_format() for m in messages]

    def compact(self, keep_last: int = 10):
        """Compact the session by keeping only recent messages"""
        if len(self.messages) > keep_last:
            # Create a summary of old messages
            old_messages = self.messages[:-keep_last]
            summary = f"[Previous conversation summary: {len(old_messages)} messages discussing various topics]"

            # Keep only recent messages
            self.messages = [Message("system", summary)] + self.messages[-keep_last:]
            self.save()
            return len(old_messages)
        return 0

    def rewind(self, count: int = 2) -> int:
        """Remove the last N messages (usually user + assistant pair)"""
        if len(self.messages) >= count:
            self.messages = self.messages[:-count]
            self.save()
            return count
        return 0

    def clear(self):
        """Clear all messages"""
        self.messages = []
        self.save()

    def save(self):
        """Save session to file"""
        data = {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "cwd": self.cwd,
            "messages": [m.to_dict() for m in self.messages],
        }
        with open(self.session_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, session_id: str) -> Optional["Session"]:
        """Load a session from file"""
        session_file = config.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return None

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            session = cls(session_id=data["session_id"])
            session.created_at = data["created_at"]
            session.updated_at = data["updated_at"]
            session.model = data.get("model", config.model)
            session.cwd = data.get("cwd", os.getcwd())
            session.messages = [Message.from_dict(m) for m in data["messages"]]
            return session
        except (json.JSONDecodeError, KeyError, IOError):
            return None

    @classmethod
    def get_latest(cls, cwd: Optional[str] = None) -> Optional["Session"]:
        """Get the most recent session, optionally filtered by cwd"""
        sessions_dir = config.sessions_dir
        if not sessions_dir.exists():
            return None

        session_files = list(sessions_dir.glob("*.json"))
        if not session_files:
            return None

        # Sort by modification time
        session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        for session_file in session_files:
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Filter by cwd if specified
                if cwd and data.get("cwd") != cwd:
                    continue

                return cls.load(data["session_id"])
            except (json.JSONDecodeError, IOError):
                continue

        return None

    @classmethod
    def list_sessions(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent sessions"""
        sessions_dir = config.sessions_dir
        if not sessions_dir.exists():
            return []

        session_files = list(sessions_dir.glob("*.json"))
        session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        sessions = []
        for session_file in session_files[:limit]:
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data["session_id"],
                    "created_at": datetime.fromtimestamp(data["created_at"]).strftime("%Y-%m-%d %H:%M"),
                    "updated_at": datetime.fromtimestamp(data["updated_at"]).strftime("%Y-%m-%d %H:%M"),
                    "messages": len(data.get("messages", [])),
                    "cwd": data.get("cwd", ""),
                })
            except (json.JSONDecodeError, IOError):
                continue

        return sessions


class HistoryManager:
    """Manages command history"""

    def __init__(self):
        self.history_file = config.history_dir / "commands.txt"

    def add(self, command: str):
        """Add a command to history"""
        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(f"{command}\n")

    def get_all(self, limit: int = 100) -> List[str]:
        """Get command history"""
        if not self.history_file.exists():
            return []

        with open(self.history_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        return [line.strip() for line in lines[-limit:]]

    def clear(self):
        """Clear command history"""
        if self.history_file.exists():
            self.history_file.unlink()


# Global instances
history_manager = HistoryManager()
