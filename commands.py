"""Slash commands for GLM CLI"""

import asyncio
import os
from typing import Callable, Dict, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import config
from session import Session, history_manager
from api import api
from ui import (
    Colors, console, print_help, print_error, print_success,
    print_info, print_warning, print_model_update
)


class CommandResult:
    """Result of a command execution"""

    def __init__(self, success: bool = True, message: str = "", should_exit: bool = False):
        self.success = success
        self.message = message
        self.should_exit = should_exit


class CommandHandler:
    """Handles slash commands"""

    def __init__(self, session: Session):
        self.session = session
        self.commands: Dict[str, Callable] = {
            "help": self.cmd_help,
            "h": self.cmd_help,
            "?": self.cmd_help,
            "clear": self.cmd_clear,
            "cls": self.cmd_clear,
            "exit": self.cmd_exit,
            "quit": self.cmd_exit,
            "q": self.cmd_exit,
            "model": self.cmd_model,
            "history": self.cmd_history,
            "compact": self.cmd_compact,
            "rewind": self.cmd_rewind,
            "config": self.cmd_config,
            "session": self.cmd_session,
            "version": self.cmd_version,
        }

    def is_command(self, text: str) -> bool:
        """Check if input is a command"""
        return text.strip().startswith("/")

    def parse_command(self, text: str) -> Tuple[str, list]:
        """Parse command and arguments"""
        parts = text.strip()[1:].split()
        if not parts:
            return "", []
        return parts[0].lower(), parts[1:]

    async def execute(self, text: str) -> CommandResult:
        """Execute a command"""
        cmd, args = self.parse_command(text)

        if not cmd:
            return CommandResult(False, "Empty command")

        if cmd not in self.commands:
            return CommandResult(False, f"Unknown command: /{cmd}. Type /help for available commands.")

        return await self.commands[cmd](args)

    async def cmd_help(self, args: list) -> CommandResult:
        """Show help"""
        print_help()
        return CommandResult()

    async def cmd_clear(self, args: list) -> CommandResult:
        """Clear screen"""
        os.system('clear' if os.name != 'nt' else 'cls')
        return CommandResult()

    async def cmd_exit(self, args: list) -> CommandResult:
        """Exit the CLI"""
        print_info("Goodbye!")
        return CommandResult(should_exit=True)

    async def cmd_model(self, args: list) -> CommandResult:
        """Model commands"""
        if not args:
            # Show current model
            console.print(f"\n[bold]Current Model:[/bold] [{Colors.ACCENT}]{config.model}[/{Colors.ACCENT}]")
            console.print(f"[bold]API Base:[/bold] [{Colors.DIM}]{config.api_base}[/{Colors.DIM}]\n")

            # Check for updates
            update_info = await api.check_model_updates()
            if update_info:
                print_model_update(update_info["current"], update_info["latest"])

            return CommandResult()

        subcmd = args[0].lower()

        if subcmd == "list":
            # List available models
            console.print("\n[bold]Fetching available models...[/bold]")
            models = await api.get_available_models(force_refresh=True)

            if not models:
                print_warning("Could not fetch model list. Check your API key.")
                return CommandResult()

            table = Table(title="Available Models")
            table.add_column("Model ID", style=Colors.ACCENT)
            table.add_column("Owner", style=Colors.DIM)

            for model in models:
                is_current = "✓ " if model.get("id") == config.model else "  "
                table.add_row(
                    f"{is_current}{model.get('id', 'unknown')}",
                    model.get("owned_by", "unknown")
                )

            console.print(table)
            console.print()
            return CommandResult()

        elif subcmd == "set" and len(args) > 1:
            new_model = args[1]
            old_model = config.model
            config.set("model", new_model)
            api.model = new_model
            self.session.model = new_model
            print_success(f"Model changed: {old_model} → {new_model}")
            return CommandResult()

        else:
            print_error("Usage: /model list  OR  /model set <model_name>")
            return CommandResult(False)

    async def cmd_history(self, args: list) -> CommandResult:
        """History commands"""
        if args and args[0].lower() == "clear":
            self.session.clear()
            print_success("Conversation history cleared")
            return CommandResult()

        # Show history
        if not self.session.messages:
            print_info("No conversation history")
            return CommandResult()

        console.print(f"\n[bold]Conversation History[/bold] ({len(self.session.messages)} messages)\n")

        for i, msg in enumerate(self.session.messages[-20:], 1):  # Show last 20
            role_color = Colors.USER if msg.role == "user" else Colors.ASSISTANT
            role_label = "You" if msg.role == "user" else "GLM"
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            console.print(f"[{Colors.DIM}]{i}.[/{Colors.DIM}] [{role_color}]{role_label}:[/{role_color}] {content_preview}")

        console.print()
        return CommandResult()

    async def cmd_compact(self, args: list) -> CommandResult:
        """Compact conversation context"""
        keep = 10
        if args and args[0].isdigit():
            keep = int(args[0])

        removed = self.session.compact(keep)
        if removed:
            print_success(f"Compacted: removed {removed} old messages, keeping {keep} recent")
        else:
            print_info("Nothing to compact")
        return CommandResult()

    async def cmd_rewind(self, args: list) -> CommandResult:
        """Rewind to previous message"""
        count = 2  # Default: remove last user + assistant pair
        if args and args[0].isdigit():
            count = int(args[0])

        removed = self.session.rewind(count)
        if removed:
            print_success(f"Rewound {removed} messages")
        else:
            print_warning("Nothing to rewind")
        return CommandResult()

    async def cmd_config(self, args: list) -> CommandResult:
        """Configuration commands"""
        if not args:
            # Show all config
            console.print("\n[bold]Current Configuration[/bold]\n")
            for key, value in config.all.items():
                if key == "api_key":
                    value = "****" + str(value)[-4:] if value else "not set"
                console.print(f"  [{Colors.ACCENT}]{key}[/{Colors.ACCENT}]: {value}")
            console.print()
            return CommandResult()

        if args[0].lower() == "set" and len(args) >= 3:
            key = args[1]
            value = " ".join(args[2:])

            # Type conversion
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.isdigit():
                value = int(value)

            config.set(key, value)
            print_success(f"Config updated: {key} = {value}")
            return CommandResult()

        print_error("Usage: /config  OR  /config set <key> <value>")
        return CommandResult(False)

    async def cmd_session(self, args: list) -> CommandResult:
        """Session commands"""
        if not args:
            # Show current session info
            console.print(f"\n[bold]Current Session[/bold]")
            console.print(f"  ID: [{Colors.ACCENT}]{self.session.session_id}[/{Colors.ACCENT}]")
            console.print(f"  Messages: {len(self.session.messages)}")
            console.print(f"  Model: {self.session.model}")
            console.print(f"  CWD: {self.session.cwd}")
            console.print()
            return CommandResult()

        if args[0].lower() == "list":
            sessions = Session.list_sessions()
            if not sessions:
                print_info("No saved sessions")
                return CommandResult()

            table = Table(title="Recent Sessions")
            table.add_column("ID", style=Colors.ACCENT)
            table.add_column("Messages")
            table.add_column("Updated")
            table.add_column("Directory", style=Colors.DIM)

            for s in sessions:
                is_current = "→ " if s["session_id"] == self.session.session_id else "  "
                table.add_row(
                    f"{is_current}{s['session_id']}",
                    str(s["messages"]),
                    s["updated_at"],
                    s["cwd"][:30]
                )

            console.print(table)
            return CommandResult()

        print_error("Usage: /session  OR  /session list")
        return CommandResult(False)

    async def cmd_version(self, args: list) -> CommandResult:
        """Show version"""
        from . import __version__, __model__
        console.print(f"\n[bold]GLM CLI[/bold] v{__version__}")
        console.print(f"[bold]Model:[/bold] {__model__}")
        console.print()
        return CommandResult()
