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

from config import config

__version__ = "1.2.0"  # Synced with main.py
__model__ = "GLM-4.7"

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
    SUCCESS = "bright_green"  # Added for tool mode
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
[bold]Basic Commands:[/bold]

  [cyan]/help[/cyan]              Show this help message
  [cyan]/clear[/cyan]             Clear the screen
  [cyan]/exit[/cyan], [cyan]/quit[/cyan]      Exit GLM CLI
  [cyan]/version[/cyan]           Show version info

[bold]Model & Session:[/bold]

  [cyan]/model[/cyan]             Show current model info
  [cyan]/model list[/cyan]        List available models
  [cyan]/model set <name>[/cyan]  Switch to a different model
  [cyan]/history[/cyan]           Show conversation history
  [cyan]/history clear[/cyan]     Clear conversation history
  [cyan]/compact[/cyan]           Compress conversation context
  [cyan]/rewind[/cyan]            Go back to a previous message
  [cyan]/session[/cyan]           Show/list sessions
  [cyan]/config[/cyan]            Show current configuration

[bold]Tools & MCP:[/bold]

  [cyan]/tools[/cyan]             Tool system status/options
  [cyan]/tools list[/cyan]        List available tools
  [cyan]/tools enable[/cyan]      Enable tool support
  [cyan]/mcp[/cyan]               MCP server status/options
  [cyan]/mcp list[/cyan]          List MCP servers
  [cyan]/mcp connect <name>[/cyan] Connect to MCP server

[bold]Agents & Skills:[/bold]

  [cyan]/agent[/cyan]             Show current agent
  [cyan]/agent list[/cyan]        List available agents
  [cyan]/agent use <name>[/cyan]  Activate an agent
  [cyan]/skill list[/cyan]        List available skills
  [cyan]/commit[/cyan]            Run commit skill
  [cyan]/review[/cyan]            Run code review skill
  [cyan]/test[/cyan]              Run test skill
  [cyan]/docs[/cyan]              Run docs skill
  [cyan]/refactor[/cyan]          Run refactor skill
  [cyan]/audit[/cyan]             Run audit skill

[bold]Keyboard Shortcuts:[/bold]

  [cyan]Ctrl+C[/cyan]             Cancel / Exit
  [cyan]Ctrl+D[/cyan]             Exit GLM CLI
  [cyan]Ctrl+L[/cyan]             Clear screen
  [cyan]↑/↓[/cyan]                Navigate history
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


class InteractiveSelector:
    """Arrow key interactive selector for lists"""

    def __init__(self, title: str, options: list, current: str = None):
        """
        Args:
            title: Title to display above options
            options: List of (value, label) tuples or just strings
            current: Currently selected value (for highlighting)
        """
        self.title = title
        self.options = []
        for opt in options:
            if isinstance(opt, tuple):
                self.options.append(opt)
            else:
                self.options.append((opt, opt))
        self.current = current
        self.selected_index = 0

        # Find current selection index
        for i, (value, _) in enumerate(self.options):
            if value == current:
                self.selected_index = i
                break

    def run(self) -> Optional[str]:
        """Run the interactive selector, returns selected value or None if cancelled"""
        import sys
        import termios
        import tty

        if not self.options:
            return None

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            self._render()

            while True:
                ch = sys.stdin.read(1)

                if ch == '\x1b':  # Escape sequence
                    next1 = sys.stdin.read(1)
                    if next1 == '[':
                        next2 = sys.stdin.read(1)
                        if next2 == 'A':  # Up arrow
                            self.selected_index = max(0, self.selected_index - 1)
                            self._render()
                        elif next2 == 'B':  # Down arrow
                            self.selected_index = min(len(self.options) - 1, self.selected_index + 1)
                            self._render()
                    elif next1 == '\x1b':  # Double escape = cancel
                        self._clear()
                        return None
                    else:
                        self._clear()
                        return None
                elif ch == '\r' or ch == '\n':  # Enter
                    self._clear()
                    return self.options[self.selected_index][0]
                elif ch == 'q' or ch == '\x03':  # q or Ctrl+C
                    self._clear()
                    return None
                elif ch == 'k':  # vim up
                    self.selected_index = max(0, self.selected_index - 1)
                    self._render()
                elif ch == 'j':  # vim down
                    self.selected_index = min(len(self.options) - 1, self.selected_index + 1)
                    self._render()

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    def _render(self):
        """Render the selector"""
        import sys

        # Move cursor up and clear lines
        sys.stdout.write('\r')
        sys.stdout.write(f'\033[{len(self.options) + 2}A')  # Move up
        sys.stdout.write('\033[J')  # Clear from cursor to end

        # Print title
        sys.stdout.write(f'\033[1m{self.title}\033[0m\n')
        sys.stdout.write('\033[90m↑/↓ select · Enter confirm · q/Esc cancel\033[0m\n')

        # Print options
        for i, (value, label) in enumerate(self.options):
            is_current = value == self.current
            is_selected = i == self.selected_index

            if is_selected:
                prefix = '\033[96m❯\033[0m '  # Cyan arrow
                style_start = '\033[1;96m'  # Bold cyan
                style_end = '\033[0m'
            else:
                prefix = '  '
                style_start = ''
                style_end = ''

            current_mark = ' \033[92m✓\033[0m' if is_current else ''
            sys.stdout.write(f'{prefix}{style_start}{label}{style_end}{current_mark}\n')

        sys.stdout.flush()

    def _clear(self):
        """Clear the selector display"""
        import sys
        sys.stdout.write('\r')
        sys.stdout.write(f'\033[{len(self.options) + 2}A')  # Move up
        sys.stdout.write('\033[J')  # Clear from cursor to end
        sys.stdout.flush()


def interactive_select(title: str, options: list, current: str = None) -> Optional[str]:
    """
    Show an interactive selector with arrow key navigation.

    Args:
        title: Title to display
        options: List of options (strings or (value, label) tuples)
        current: Currently selected value

    Returns:
        Selected value or None if cancelled
    """
    # Print blank lines to make room for the selector
    print('\n' * (len(options) + 2))

    selector = InteractiveSelector(title, options, current)
    return selector.run()
