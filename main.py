#!/usr/bin/env python3
"""GLM CLI - Claude Code Style Interactive Terminal for GLM-4

Now with tool support (Read, Write, Bash, MCP integration)

Usage:
    glm                     Start interactive session
    glm -c, --continue      Continue last session
    glm -r, --resume <id>   Resume specific session
    glm -p, --print <msg>   One-shot query (non-interactive)
    glm --tools             Enable tool use mode
    glm --version           Show version
    glm --help              Show help
"""

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add lib path
sys.path.insert(0, str(Path(__file__).parent))

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.completion import WordCompleter

from rich.console import Console

from config import config
from api import api, GLMAPIError
from session import Session
from commands import CommandHandler, CommandResult
from ui import (
    console, print_banner, print_welcome, print_error, print_success,
    print_info, print_warning, print_model_update, StreamingDisplay,
    get_prompt_style, Colors
)

__version__ = "1.2.0"


class GLMCLI:
    """Main GLM CLI Application with Tool Support"""

    def __init__(self, enable_tools: bool = False):
        self.session: Optional[Session] = None
        self.command_handler: Optional[CommandHandler] = None
        self.prompt_session: Optional[PromptSession] = None
        self.running = False
        self._cancelled = False
        self._ctrl_c_count = 0  # Track Ctrl+C presses for double-tap exit
        self.enable_tools = enable_tools
        self.tool_executor = None
        self.current_agent = None  # Current active agent

        # Setup key bindings
        self.bindings = KeyBindings()
        self._setup_keybindings()

        # Command completer for slash commands
        self.completer = WordCompleter([
            '/help', '/clear', '/exit', '/quit', '/model', '/model list',
            '/model set', '/history', '/history clear', '/compact', '/rewind',
            '/config', '/config set', '/session', '/session list', '/version',
            '/tools', '/tools list', '/tools enable', '/tools disable',
            '/mcp', '/mcp list', '/mcp connect', '/mcp disconnect',
            '/agent', '/agent list', '/agent use', '/agent clear',
            '/skill', '/skill list', '/skill run',
            '/commit', '/review', '/test', '/docs', '/refactor', '/audit'
        ], ignore_case=True)

    def _setup_keybindings(self):
        """Setup keyboard shortcuts"""

        @self.bindings.add(Keys.ControlC)
        def handle_ctrl_c(event):
            """Cancel current operation or exit"""
            self._cancelled = True
            event.app.exit(result='__exit__')

        @self.bindings.add(Keys.ControlD)
        def handle_ctrl_d(event):
            """Exit CLI"""
            event.app.exit(result='__exit__')

        @self.bindings.add(Keys.ControlZ)
        def handle_ctrl_z(event):
            """Exit CLI (like other CLI tools)"""
            event.app.exit(result='__exit__')

        @self.bindings.add(Keys.ControlL)
        def _(event):
            """Clear screen"""
            os.system('clear' if os.name != 'nt' else 'cls')

    def _setup_signal_handlers(self):
        """Setup signal handlers"""
        def handle_sigint(sig, frame):
            self._cancelled = True

        signal.signal(signal.SIGINT, handle_sigint)

    async def initialize(self, continue_session: bool = False, resume_id: Optional[str] = None):
        """Initialize the CLI"""
        # Validate API key first
        is_valid, message = config.validate_api_key()
        if not is_valid:
            print_error(message)
            return False

        # Load or create session
        if resume_id:
            self.session = Session.load(resume_id)
            if not self.session:
                print_error(f"Session not found: {resume_id}")
                self.session = Session()
        elif continue_session:
            self.session = Session.get_latest(cwd=os.getcwd())
            if self.session:
                print_info(f"Continuing session: {self.session.session_id}")
            else:
                self.session = Session()
        else:
            self.session = Session()

        # Initialize command handler
        self.command_handler = CommandHandler(self.session)

        # Initialize prompt session
        history_file = config.history_dir / "prompt_history"
        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            key_bindings=self.bindings,
            style=get_prompt_style(),
            completer=self.completer,
            complete_while_typing=False,
        )

        # Initialize tools if enabled
        if self.enable_tools:
            await self._initialize_tools()

        # Load external skills
        try:
            from tools.skills import skill_registry
            loaded = skill_registry.load_external_skills()
            if loaded > 0:
                print_info(f"Loaded {loaded} external skill(s)")
        except Exception:
            pass  # Silently ignore skill loading errors

        # Check for model updates on startup
        if config.get("auto_update_check", True):
            await self._check_model_updates()

        return True

    async def _initialize_tools(self):
        """Initialize the tool system"""
        try:
            from tools.executor import tool_executor
            await tool_executor.initialize()
            self.tool_executor = tool_executor
            print_success("Tool system initialized")

            # Show available tools count
            tools = self.tool_executor.get_all_tools()
            print_info(f"Available tools: {len(tools)}")

        except Exception as e:
            print_warning(f"Could not initialize tools: {e}")
            self.enable_tools = False

    async def _check_model_updates(self):
        """Check for model updates silently"""
        try:
            update_info = await api.check_model_updates()
            if update_info:
                print_model_update(update_info["current"], update_info["latest"])
        except Exception:
            pass  # Silently ignore update check failures

    async def process_input(self, user_input: str) -> bool:
        """Process user input. Returns True if should continue, False to exit."""
        user_input = user_input.strip()

        if not user_input:
            return True

        # Handle slash commands
        if self.command_handler.is_command(user_input):
            # Handle tool-related commands
            if user_input.startswith("/tools") or user_input.startswith("/mcp"):
                return await self._handle_tool_command(user_input)

            # Handle agent commands
            if user_input.startswith("/agent"):
                return await self._handle_agent_command(user_input)

            # Handle skill commands
            if user_input.startswith("/skill"):
                return await self._handle_skill_command(user_input)

            # Handle skill shortcuts (/commit, /review, /test, etc.)
            skill_shortcuts = ['commit', 'review', 'test', 'docs', 'refactor', 'audit', 'optimize', 'fix', 'explore']
            cmd_name = user_input[1:].split()[0].lower()
            if cmd_name in skill_shortcuts:
                args = ' '.join(user_input[1:].split()[1:])
                return await self._run_skill(cmd_name, args)

            result = await self.command_handler.execute(user_input)
            if not result.success and result.message:
                print_error(result.message)
            return not result.should_exit

        # Regular message - send to GLM
        if self.enable_tools and self.tool_executor:
            await self._send_message_with_tools(user_input)
        else:
            await self._send_message(user_input)

        return True

    async def _handle_tool_command(self, command: str) -> bool:
        """Handle tool-related commands"""
        parts = command.strip()[1:].split()

        if not parts:
            return True

        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        if cmd == "tools":
            if not args:
                # Show tools status
                status = "enabled" if self.enable_tools else "disabled"
                console.print(f"\n[bold]Tool System:[/bold] {status}")
                if self.tool_executor:
                    tools = self.tool_executor.get_all_tools()
                    console.print(f"[bold]Available Tools:[/bold] {len(tools)}")
                return True

            subcmd = args[0].lower()
            if subcmd == "list":
                if self.tool_executor:
                    tools = self.tool_executor.get_all_tools()
                    console.print("\n[bold]Available Tools:[/bold]")
                    for tool in tools:
                        console.print(f"  [{Colors.ACCENT}]{tool['name']}[/{Colors.ACCENT}] - {tool.get('description', '')[:60]}")
                else:
                    print_warning("Tools not initialized")

            elif subcmd == "enable":
                if not self.tool_executor:
                    await self._initialize_tools()
                self.enable_tools = True
                print_success("Tools enabled")

            elif subcmd == "disable":
                self.enable_tools = False
                print_info("Tools disabled")

        elif cmd == "mcp":
            if not self.tool_executor:
                print_warning("Tools not initialized. Use /tools enable first.")
                return True

            if not args:
                # Show MCP status
                servers = self.tool_executor.list_mcp_servers()
                connected = self.tool_executor.list_connected_mcp()
                console.print(f"\n[bold]MCP Servers:[/bold] {len(servers)} configured, {len(connected)} connected")
                return True

            subcmd = args[0].lower()
            if subcmd == "list":
                servers = self.tool_executor.list_mcp_servers()
                connected = self.tool_executor.list_connected_mcp()
                console.print("\n[bold]MCP Servers:[/bold]")
                for server in servers:
                    status = "✓" if server in connected else "○"
                    console.print(f"  {status} [{Colors.ACCENT}]{server}[/{Colors.ACCENT}]")

            elif subcmd == "connect" and len(args) > 1:
                server_name = args[1]
                console.print(f"Connecting to {server_name}...")
                if await self.tool_executor.connect_mcp_server(server_name):
                    print_success(f"Connected to {server_name}")
                else:
                    print_error(f"Failed to connect to {server_name}")

            elif subcmd == "disconnect":
                await self.tool_executor.disconnect_all_mcp()
                print_info("Disconnected from all MCP servers")

        return True

    async def _handle_agent_command(self, command: str) -> bool:
        """Handle agent-related commands"""
        from tools.agents import agent_registry

        parts = command.strip()[1:].split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            # Show current agent status
            if self.current_agent:
                console.print(f"\n[bold]Current Agent:[/bold] {self.current_agent.name}")
                console.print(f"[dim]{self.current_agent.description}[/dim]")
            else:
                console.print("\n[dim]No agent active. Use /agent use <name> to activate.[/dim]")
            return True

        subcmd = args[0].lower()

        if subcmd == "list":
            agents = agent_registry.list_agents()
            console.print("\n[bold]Available Agents:[/bold]")
            for agent in agents:
                marker = "●" if self.current_agent and self.current_agent.name == agent['name'] else "○"
                console.print(f"  {marker} [{Colors.ACCENT}]{agent['name']}[/{Colors.ACCENT}] - {agent['description']}")

        elif subcmd == "use" and len(args) > 1:
            agent_name = args[1]
            agent = agent_registry.get_agent(agent_name)
            if agent:
                self.current_agent = agent
                print_success(f"Activated agent: {agent.name}")
                console.print(f"[dim]{agent.description}[/dim]")
            else:
                print_error(f"Agent not found: {agent_name}")
                console.print("[dim]Use /agent list to see available agents[/dim]")

        elif subcmd == "clear":
            self.current_agent = None
            print_info("Agent deactivated")

        return True

    async def _handle_skill_command(self, command: str) -> bool:
        """Handle skill-related commands"""
        from tools.skills import skill_registry

        parts = command.strip()[1:].split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            # Show skill help
            console.print("\n[bold]Skill Commands:[/bold]")
            console.print("  /skill list         - List available skills")
            console.print("  /skill run <name>   - Run a skill")
            console.print("\n[bold]Skill Shortcuts:[/bold]")
            console.print("  /commit, /review, /test, /docs, /refactor, /audit")
            return True

        subcmd = args[0].lower()

        if subcmd == "list":
            skills = skill_registry.list_skills()
            console.print("\n[bold]Available Skills:[/bold]")
            for skill in skills:
                console.print(f"  [{Colors.ACCENT}]/{skill['name']}[/{Colors.ACCENT}] - {skill['description']}")

        elif subcmd == "run" and len(args) > 1:
            skill_name = args[1]
            skill_args = ' '.join(args[2:]) if len(args) > 2 else ''
            return await self._run_skill(skill_name, skill_args)

        return True

    async def _run_skill(self, skill_name: str, args: str = "") -> bool:
        """Run a skill by name"""
        from tools.skills import skill_registry

        skill = skill_registry.get_skill(skill_name)
        if not skill:
            print_error(f"Skill not found: {skill_name}")
            return True

        # Check if skill requires args
        if skill.requires_args and not args:
            print_warning(f"Skill '{skill_name}' requires arguments")
            console.print(f"[dim]Usage: /{skill_name} <args>[/dim]")
            return True

        # Get the skill prompt
        prompt = skill_registry.get_skill_prompt(skill_name, args)
        if not prompt:
            print_error(f"Could not get prompt for skill: {skill_name}")
            return True

        console.print(f"\n[bold cyan]Running skill:[/bold cyan] {skill_name}")

        # Send the skill prompt as a message
        if self.enable_tools and self.tool_executor:
            await self._send_message_with_tools(prompt)
        else:
            await self._send_message(prompt)

        return True

    async def _send_message(self, message: str):
        """Send message to GLM and display response (no tools)"""
        # Add user message to session
        self.session.add_message("user", message)

        # Prepare messages for API
        messages = self.session.get_messages_for_api()

        # Add agent system prompt if active
        if self.current_agent:
            agent_prompt = self.current_agent.system_prompt
            messages.insert(0, {"role": "system", "content": agent_prompt})

        # Display streaming response
        display = StreamingDisplay()
        self._cancelled = False

        try:
            display.start()
            full_response = ""

            async for chunk in api.chat_stream(
                messages=messages,
                temperature=config.get("temperature", 0.7),
                max_tokens=config.get("max_tokens", 4096),
            ):
                if self._cancelled:
                    display.stop()
                    print_warning("\nCancelled")
                    # Remove the user message if cancelled
                    self.session.rewind(1)
                    return

                full_response += chunk
                display.update(chunk)

            display.stop()
            console.print()  # New line after response

            # Add assistant response to session
            self.session.add_message("assistant", full_response)

        except GLMAPIError as e:
            display.stop()
            print_error(f"API Error: {e}")
            # Remove the user message on error
            self.session.rewind(1)
        except Exception as e:
            display.stop()
            print_error(f"Error: {e}")
            self.session.rewind(1)

    async def _send_message_with_tools(self, message: str):
        """Send message to GLM with tool support"""
        # Add user message to session
        self.session.add_message("user", message)

        # Get available tools
        tools = self.tool_executor.get_all_tools()

        # Prepare messages for API
        messages = self.session.get_messages_for_api()

        # Add agent system prompt if active
        if self.current_agent:
            agent_prompt = self.current_agent.system_prompt
            messages.insert(0, {"role": "system", "content": agent_prompt})

        self._cancelled = False
        max_iterations = 10  # Prevent infinite loops

        try:
            for iteration in range(max_iterations):
                # Make API call with tools
                response = await api.chat_with_tools(
                    messages=messages,
                    tools=tools,
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 4096),
                )

                # Parse response
                content_blocks = response.get("content", [])
                stop_reason = response.get("stop_reason", "")

                # Collect text and tool_use blocks
                text_parts = []
                tool_uses = []

                for block in content_blocks:
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_uses.append(block)

                # Display text response
                if text_parts:
                    text_response = "".join(text_parts)
                    console.print(f"\n{text_response}")

                # If no tool calls, we're done
                if not tool_uses or stop_reason != "tool_use":
                    # Add assistant response to session
                    if text_parts:
                        self.session.add_message("assistant", "".join(text_parts))
                    break

                # Execute tools
                tool_results = []
                for tool_use in tool_uses:
                    tool_name = tool_use.get("name", "")
                    tool_input = tool_use.get("input", {})
                    tool_id = tool_use.get("id", "")

                    # Display tool use
                    self.tool_executor.display_tool_use(tool_name, tool_input)

                    # Execute tool
                    result = await self.tool_executor.execute_tool(tool_name, tool_input)

                    # Display result
                    self.tool_executor.display_tool_result(result)

                    # Format for API
                    tool_results.append(
                        self.tool_executor.format_tool_result_for_api(tool_id, result)
                    )

                # Add assistant message with tool uses
                messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })

                # Add tool results
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

        except GLMAPIError as e:
            print_error(f"API Error: {e}")
            self.session.rewind(1)
        except Exception as e:
            print_error(f"Error: {e}")
            import traceback
            traceback.print_exc()
            self.session.rewind(1)

    async def run_interactive(self):
        """Run the interactive CLI loop"""
        print_banner()
        print_welcome()

        if self.enable_tools:
            console.print(f"[{Colors.SUCCESS}]🔧 Tool mode enabled[/{Colors.SUCCESS}]")

        self.running = True

        while self.running:
            try:
                # Get user input using async prompt (more efficient than run_in_executor)
                prompt_text = '❯ ' if not self.enable_tools else '🔧❯ '
                user_input = await self.prompt_session.prompt_async(
                    [('class:prompt', prompt_text)],
                    multiline=False,
                )

                if user_input is None:
                    continue

                # Handle exit signal from key bindings
                if user_input == '__exit__':
                    print_info("\nGoodbye!")
                    self.running = False
                    break

                # Process input
                should_continue = await self.process_input(user_input)
                if not should_continue:
                    self.running = False

            except EOFError:
                # Ctrl+D or Ctrl+Z - exit immediately
                print_info("\nGoodbye!")
                self.running = False
            except KeyboardInterrupt:
                # Ctrl+C - exit immediately (like other CLI tools)
                print_info("\nGoodbye!")
                self.running = False
            except Exception as e:
                print_error(f"Error: {e}")

        # Cleanup
        if self.tool_executor:
            await self.tool_executor.disconnect_all_mcp()
        await api.close()

    async def run_oneshot(self, message: str):
        """Run a one-shot query (non-interactive)"""
        try:
            if self.enable_tools:
                await self._initialize_tools()
                # For one-shot with tools, use non-streaming
                tools = self.tool_executor.get_all_tools() if self.tool_executor else []
                response = await api.chat_with_tools(
                    messages=[{"role": "user", "content": message}],
                    tools=tools,
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 4096),
                )
                # Extract text from response
                for block in response.get("content", []):
                    if block.get("type") == "text":
                        print(block.get("text", ""))
            else:
                messages = [{"role": "user", "content": message}]
                async for chunk in api.chat_stream(
                    messages=messages,
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 4096),
                ):
                    print(chunk, end="", flush=True)
                print()  # Final newline

        except GLMAPIError as e:
            print_error(f"API Error: {e}")
            sys.exit(1)
        except Exception as e:
            print_error(f"Error: {e}")
            sys.exit(1)
        finally:
            if self.tool_executor:
                await self.tool_executor.disconnect_all_mcp()
            await api.close()


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="GLM CLI - Claude Code Style Interactive Terminal with Tool Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  glm                       Start interactive session
  glm --tools               Start with tool support enabled
  glm -c                    Continue last session
  glm -r abc123             Resume session abc123
  glm -p "Hello, GLM!"      One-shot query
  glm --model glm-4-plus    Use specific model
  glm --tools -p "List files in current directory"
        """
    )

    parser.add_argument('-c', '--continue', dest='continue_session', action='store_true',
                        help='Continue the most recent session')
    parser.add_argument('-r', '--resume', dest='resume_id', metavar='ID',
                        help='Resume a specific session by ID')
    parser.add_argument('-p', '--print', dest='oneshot', metavar='MSG',
                        help='One-shot query (non-interactive)')
    parser.add_argument('--model', metavar='MODEL',
                        help='Use specific model for this session')
    parser.add_argument('--tools', action='store_true', default=True,
                        help='Enable tool support (Read, Write, Bash, MCP) - enabled by default')
    parser.add_argument('--no-tools', dest='tools', action='store_false',
                        help='Disable tool support')
    parser.add_argument('-v', '--version', action='store_true',
                        help='Show version')
    parser.add_argument('prompt', nargs='?',
                        help='Initial prompt (starts interactive with this prompt)')

    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_args()

    if args.version:
        console.print(f"GLM CLI v{__version__}")
        console.print(f"Model: {config.model}")
        console.print(f"Tool Support: {'enabled' if args.tools else 'disabled'}")
        return

    # Override model if specified
    if args.model:
        config.set("model", args.model)
        api.model = args.model

    # Create CLI instance
    cli = GLMCLI(enable_tools=args.tools)

    # One-shot mode
    if args.oneshot:
        await cli.run_oneshot(args.oneshot)
        return

    # Interactive mode
    init_success = await cli.initialize(
        continue_session=args.continue_session,
        resume_id=args.resume_id
    )

    if not init_success:
        return

    # If initial prompt provided, process it first
    if args.prompt:
        await cli.process_input(args.prompt)

    await cli.run_interactive()


def run():
    """Entry point for the CLI"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
        sys.exit(0)


if __name__ == "__main__":
    run()
