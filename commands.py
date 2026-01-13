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
    print_info, print_warning, print_model_update, interactive_select
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

        if subcmd == "list" or subcmd == "set":
            # Fetch available models
            console.print("\n[bold]Fetching available models...[/bold]")
            models = await api.get_available_models(force_refresh=True)

            if not models:
                print_warning("Could not fetch model list. Check your API key.")
                return CommandResult()

            # If /model set <name> was provided directly
            if subcmd == "set" and len(args) > 1:
                new_model = args[1]
                old_model = config.model
                config.set("model", new_model)
                api.model = new_model
                self.session.model = new_model
                print_success(f"Model changed: {old_model} → {new_model}")
                return CommandResult()

            # Show interactive selector
            model_options = [(m.get("id"), m.get("id")) for m in models if m.get("id")]

            selected = interactive_select(
                title="Select a model:",
                options=model_options,
                current=config.model
            )

            if selected:
                old_model = config.model
                config.set("model", selected)
                api.model = selected
                self.session.model = selected
                print_success(f"Model changed: {old_model} → {selected}")
            else:
                print_info("Model selection cancelled")

            return CommandResult()

        else:
            print_error("Usage: /model list  OR  /model set <model_name>")
            return CommandResult(False)

    async def cmd_history(self, args: list) -> CommandResult:
        """History commands"""
        if not self.session.messages:
            print_info("No conversation history")
            return CommandResult()

        # If no args, show interactive menu
        if not args:
            options = [
                ("show", f"📜 Show history ({len(self.session.messages)} messages)"),
                ("clear", "🗑️  Clear all history"),
            ]
            selected = interactive_select("History options:", options)

            if selected == "clear":
                self.session.clear()
                print_success("Conversation history cleared")
                return CommandResult()
            elif selected == "show":
                pass  # Fall through to show history
            else:
                print_info("Cancelled")
                return CommandResult()

        elif args[0].lower() == "clear":
            self.session.clear()
            print_success("Conversation history cleared")
            return CommandResult()

        # Show history
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
        if not self.session.messages:
            print_info("No messages to compact")
            return CommandResult()

        # If no args, show interactive selector for keep count
        if not args:
            msg_count = len(self.session.messages)
            options = [
                ("5", f"Keep 5 messages (remove {max(0, msg_count - 5)})"),
                ("10", f"Keep 10 messages (remove {max(0, msg_count - 10)})"),
                ("20", f"Keep 20 messages (remove {max(0, msg_count - 20)})"),
                ("50", f"Keep 50 messages (remove {max(0, msg_count - 50)})"),
            ]
            selected = interactive_select(f"Compact history ({msg_count} messages):", options, current="10")

            if selected:
                keep = int(selected)
            else:
                print_info("Cancelled")
                return CommandResult()
        else:
            keep = int(args[0]) if args[0].isdigit() else 10

        removed = self.session.compact(keep)
        if removed:
            print_success(f"Compacted: removed {removed} old messages, keeping {keep} recent")
        else:
            print_info("Nothing to compact")
        return CommandResult()

    async def cmd_rewind(self, args: list) -> CommandResult:
        """Rewind to previous message"""
        if not self.session.messages:
            print_info("No messages to rewind")
            return CommandResult()

        # If no args, show interactive selector
        if not args:
            msg_count = len(self.session.messages)
            options = [
                ("2", "Rewind 2 messages (last exchange)"),
                ("4", "Rewind 4 messages"),
                ("6", "Rewind 6 messages"),
                ("all", f"Rewind all ({msg_count} messages)"),
            ]
            selected = interactive_select("Rewind options:", options, current="2")

            if selected == "all":
                count = msg_count
            elif selected:
                count = int(selected)
            else:
                print_info("Cancelled")
                return CommandResult()
        else:
            count = int(args[0]) if args[0].isdigit() else 2

        removed = self.session.rewind(count)
        if removed:
            print_success(f"Rewound {removed} messages")
        else:
            print_warning("Nothing to rewind")
        return CommandResult()

    async def cmd_config(self, args: list) -> CommandResult:
        """Configuration commands"""
        # If no args, show interactive menu
        if not args:
            options = [
                ("show", "📋 Show all configuration"),
                ("set", "✏️  Edit a setting"),
            ]
            selected = interactive_select("Config options:", options)

            if selected == "show":
                console.print("\n[bold]Current Configuration[/bold]\n")
                for key, value in config.all.items():
                    if key == "api_key":
                        value = "****" + str(value)[-4:] if value else "not set"
                    console.print(f"  [{Colors.ACCENT}]{key}[/{Colors.ACCENT}]: {value}")
                console.print()
                return CommandResult()
            elif selected == "set":
                # Show config keys to edit
                config_keys = [(k, f"{k}: {v if k != 'api_key' else '****'}") for k, v in config.all.items()]
                key_selected = interactive_select("Select setting to edit:", config_keys)
                if key_selected:
                    print_info(f"Use: /config set {key_selected} <new_value>")
                return CommandResult()
            else:
                print_info("Cancelled")
                return CommandResult()

        if args[0].lower() == "show":
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
        # If no args, show interactive menu
        if not args:
            options = [
                ("current", "📌 Show current session"),
                ("list", "📋 List all sessions"),
            ]
            selected = interactive_select("Session options:", options)

            if selected == "current":
                console.print(f"\n[bold]Current Session[/bold]")
                console.print(f"  ID: [{Colors.ACCENT}]{self.session.session_id}[/{Colors.ACCENT}]")
                console.print(f"  Messages: {len(self.session.messages)}")
                console.print(f"  Model: {self.session.model}")
                console.print(f"  CWD: {self.session.cwd}")
                console.print()
                return CommandResult()
            elif selected == "list":
                pass  # Fall through to list
            else:
                print_info("Cancelled")
                return CommandResult()

        if args and args[0].lower() != "list":
            print_error("Usage: /session  OR  /session list")
            return CommandResult(False)

        # List sessions
        sessions = Session.list_sessions()
        if not sessions:
            print_info("No saved sessions")
            return CommandResult()

        # Show interactive session selector
        session_options = [
            (s["session_id"], f"{s['session_id'][:8]}... | {s['messages']} msgs | {s['cwd'][:20]}")
            for s in sessions
        ]

        selected_session = interactive_select(
            "Select session to resume:",
            session_options,
            current=self.session.session_id
        )

        if selected_session:
            print_info(f"To resume: glm --resume {selected_session}")
        return CommandResult()

    async def cmd_version(self, args: list) -> CommandResult:
        """Show version"""
        from . import __version__, __model__
        console.print(f"\n[bold]GLM CLI[/bold] v{__version__}")
        console.print(f"[bold]Model:[/bold] {__model__}")
        console.print()
        return CommandResult()
