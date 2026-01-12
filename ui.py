"""UI components for GLM CLI - Claude Code style"""

import os
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown
from rich.live import Live
from rich.spinner import Spinner

__version__ = "1.0.0"
__model__ = "GLM-4.7"
from config import config

console = Console()

# GLM Logo ASCII Art (Claude Code style)
GLM_LOGO = """
 ▐▛███▜▌   GLM CLI v{version}
▝▜█████▛▘  {model} · ZhipuAI
  ▘▘ ▝▝    {cwd}
"""

GLM_LOGO_SIMPLE = """╭─────────────────────────────────────╮
│  ▄▄▄▄▄  GLM CLI v{version}        │
│ █▀▀▀▀█  {model}                │
│ █ ██ █  ZhipuAI API              │
│ █▄▄▄▄█  {cwd}│
╰─────────────────────────────────────╯"""


class Colors:
    """Color definitions"""
    PRIMARY = "bright_green"
    SECONDARY = "bright_blue"
    ACCENT = "bright_cyan"
    ERROR = "bright_red"
    WARNING = "bright_yellow"
    INFO = "bright_white"
    DIM = "dim"
    USER = "bright_cyan"
    ASSISTANT = "bright_green"


def get_banner() -> str:
    """Generate the startup banner"""
    cwd = os.getcwd()
    # Truncate cwd if too long
    max_len = 30
    if len(cwd) > max_len:
        cwd = "..." + cwd[-(max_len-3):]

    return GLM_LOGO.format(
        version=__version__,
        model=config.model.upper(),
        cwd=cwd
    )


def print_banner():
    """Print the startup banner"""
    banner = get_banner()
    console.print(Text(banner, style=Colors.PRIMARY))


def print_welcome():
    """Print welcome message"""
    console.print()
    console.print(f"  [dim]Type your message or use [/dim][{Colors.ACCENT}]/help[/{Colors.ACCENT}][dim] for commands[/dim]")
    console.print(f"  [dim]Press [/dim][{Colors.ACCENT}]Ctrl+C[/{Colors.ACCENT}][dim] to cancel, [/dim][{Colors.ACCENT}]Ctrl+D[/{Colors.ACCENT}][dim] to exit[/dim]")
    console.print()


def print_error(message: str):
    """Print error message"""
    console.print(f"[{Colors.ERROR}]✗ {message}[/{Colors.ERROR}]")


def print_warning(message: str):
    """Print warning message"""
    console.print(f"[{Colors.WARNING}]⚠ {message}[/{Colors.WARNING}]")


def print_info(message: str):
    """Print info message"""
    console.print(f"[{Colors.INFO}]ℹ {message}[/{Colors.INFO}]")


def print_success(message: str):
    """Print success message"""
    console.print(f"[{Colors.PRIMARY}]✓ {message}[/{Colors.PRIMARY}]")


def print_model_update(current: str, latest: str):
    """Print model update notification"""
    console.print()
    console.print(Panel(
        f"[{Colors.WARNING}]New model available![/{Colors.WARNING}]\n"
        f"Current: [{Colors.DIM}]{current}[/{Colors.DIM}]\n"
        f"Latest:  [{Colors.ACCENT}]{latest}[/{Colors.ACCENT}]\n\n"
        f"[dim]Use [/dim][{Colors.ACCENT}]/model set {latest}[/{Colors.ACCENT}][dim] to switch[/dim]",
        title="[bold]Model Update[/bold]",
        border_style=Colors.WARNING,
    ))
    console.print()


def print_help():
    """Print help message"""
    help_text = """
[bold]Available Commands:[/bold]

  [cyan]/help[/cyan]              Show this help message
  [cyan]/clear[/cyan]             Clear the screen
  [cyan]/exit[/cyan], [cyan]/quit[/cyan]      Exit GLM CLI
  [cyan]/model[/cyan]             Show current model info
  [cyan]/model list[/cyan]        List available models
  [cyan]/model set <name>[/cyan]  Switch to a different model
  [cyan]/history[/cyan]           Show conversation history
  [cyan]/history clear[/cyan]     Clear conversation history
  [cyan]/compact[/cyan]           Compress conversation context
  [cyan]/rewind[/cyan]            Go back to a previous message
  [cyan]/config[/cyan]            Show current configuration
  [cyan]/config set <k> <v>[/cyan] Set a configuration value

[bold]Keyboard Shortcuts:[/bold]

  [cyan]Ctrl+C[/cyan]             Cancel current response
  [cyan]Ctrl+D[/cyan]             Exit GLM CLI
  [cyan]Ctrl+L[/cyan]             Clear screen
  [cyan]↑/↓[/cyan]                Navigate history

[bold]Tips:[/bold]

  • Use triple backticks for multi-line code input
  • Session is auto-saved for --continue support
  • Model updates are checked automatically
"""
    console.print(Panel(help_text, title="[bold]GLM CLI Help[/bold]", border_style=Colors.ACCENT))


class StreamingDisplay:
    """Display streaming response with live updates"""

    def __init__(self):
        self.content = ""
        self.live: Optional[Live] = None

    def start(self):
        """Start the live display"""
        self.content = ""
        self.live = Live(
            Text("", style=Colors.ASSISTANT),
            refresh_per_second=15,
            console=console,
        )
        self.live.start()

    def update(self, chunk: str):
        """Update with new content"""
        self.content += chunk
        if self.live:
            # Try to render as markdown
            try:
                self.live.update(Markdown(self.content))
            except Exception:
                self.live.update(Text(self.content, style=Colors.ASSISTANT))

    def stop(self):
        """Stop the live display"""
        if self.live:
            self.live.stop()
            self.live = None

    def get_content(self) -> str:
        """Get the full content"""
        return self.content


def get_prompt_style():
    """Get prompt toolkit style"""
    from prompt_toolkit.styles import Style
    return Style.from_dict({
        'prompt': f'ansicyan bold',
        'input': 'ansiwhite',
    })


def format_user_input(text: str) -> str:
    """Format user input for display"""
    return f"[{Colors.USER}]❯[/{Colors.USER}] {text}"


def format_assistant_prefix() -> str:
    """Format assistant response prefix"""
    return f"[{Colors.ASSISTANT}]GLM[/{Colors.ASSISTANT}] "
