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
from prompt_toolkit.completion import Completer, Completion

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

from ui import __version__  # 버전은 ui.py에서 관리


class SlashCommandCompleter(Completer):
    """Custom completer for slash commands - filters by prefix"""

    def __init__(self, commands: list):
        self.commands = sorted(commands)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()

        # /로 시작할 때만 자동완성
        if not text.startswith('/'):
            return

        # 입력된 텍스트로 시작하는 명령어만 반환
        for cmd in self.commands:
            if cmd.lower().startswith(text.lower()):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display=cmd
                )


class GLMCLI:
    """Main GLM CLI Application with Tool Support"""

    # 도구 모드 시스템 프롬프트 - GLM이 실제 레포트를 생성하도록 유도
    TOOL_SYSTEM_PROMPT = """당신은 도구를 사용하여 작업을 수행하는 AI 어시스턴트입니다.

## 중요 규칙

1. **실제 내용 출력**: "작성하겠습니다", "분석하겠습니다" 같은 의도 표현 대신 **실제 결과를 즉시 출력**하세요.
2. **구조화된 레포트**: 도구로 수집한 정보를 종합하여 다음 형식으로 레포트를 작성하세요:
   - 📋 개요/요약
   - 📊 주요 발견사항 (구체적 수치/통계 포함)
   - ⚠️ 문제점/이슈
   - 💡 권장사항/다음 단계
3. **완결성**: 모든 응답은 완결된 형태로 제공하세요. 미완성 상태로 끝내지 마세요.
4. **한국어 응답**: 사용자가 한국어로 질문하면 한국어로 답변하세요.

## 금지 사항
- ❌ "~하겠습니다", "~해보겠습니다" 로 끝나는 응답
- ❌ 정보 수집만 하고 결과 없이 종료
- ❌ 짧은 한두 문장으로 마무리"""

    # 의도만 표현하는 패턴 (이런 패턴으로 끝나면 실제 내용 요청)
    INTENT_PATTERNS = [
        "작성하겠습니다", "분석하겠습니다", "확인하겠습니다",
        "살펴보겠습니다", "정리하겠습니다", "보고하겠습니다",
        "알아보겠습니다", "검토하겠습니다", "진행하겠습니다",
        "시작하겠습니다", "수행하겠습니다", "제공하겠습니다"
    ]

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

        # Command completer for slash commands (prefix filtering)
        self.completer = SlashCommandCompleter([
            '/help', '/clear', '/exit', '/quit', '/model', '/model list',
            '/model set', '/history', '/history clear', '/compact', '/rewind',
            '/config', '/config set', '/session', '/session list', '/version',
            '/tools', '/tools list', '/tools enable', '/tools disable',
            '/mcp', '/mcp list', '/mcp connect', '/mcp disconnect',
            '/agent', '/agent list', '/agent use', '/agent clear',
            '/skill', '/skill list', '/skill run',
            '/commit', '/review', '/test', '/docs', '/refactor', '/audit',
            '/optimize', '/fix', '/explore', '/git-push'
        ])

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
            complete_while_typing=True,  # /m 입력 시 /mcp, /model 등 바로 표시
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
            skill_shortcuts = ['commit', 'review', 'test', 'docs', 'refactor', 'audit', 'optimize', 'fix', 'explore', 'git-push']
            cmd_name = user_input[1:].split()[0].lower()
            if cmd_name in skill_shortcuts:
                args = ' '.join(user_input[1:].split()[1:])
                return await self._run_skill(cmd_name, args)

            result = await self.command_handler.execute(user_input)
            if not result.success and result.message:
                print_error(result.message)
            return not result.should_exit

        # Regular message - send to GLM
        # 에이전트 자동 활성화 (키워드 기반)
        if self.enable_tools and not self.current_agent:
            auto_agent = self._detect_agent_by_keyword(user_input)
            if auto_agent:
                self.current_agent = auto_agent
                print_info(f"🤖 에이전트 자동 활성화: {auto_agent.name}")

        if self.enable_tools and self.tool_executor:
            await self._send_message_with_tools(user_input)
        else:
            await self._send_message(user_input)

        return True

    def _detect_agent_by_keyword(self, text: str) -> Optional[Any]:
        """키워드 기반으로 적절한 에이전트를 감지"""
        try:
            from tools.agents import agent_registry
            return agent_registry.find_agent_by_keyword(text)
        except Exception:
            return None

    async def _handle_tool_command(self, command: str) -> bool:
        """Handle tool-related commands"""
        from ui import interactive_select

        parts = command.strip()[1:].split()

        if not parts:
            return True

        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        if cmd == "tools":
            if not args:
                # Show interactive menu
                tool_count = len(self.tool_executor.get_all_tools()) if self.tool_executor else 0
                options = [
                    ("status", f"📊 Show status ({tool_count} tools)"),
                    ("list", "📋 List all tools"),
                    ("enable", "✅ Enable tools"),
                    ("disable", "❌ Disable tools"),
                ]
                selected = interactive_select("Tools options:", options)

                if selected == "status":
                    status = "enabled" if self.enable_tools else "disabled"
                    console.print(f"\n[bold]Tool System:[/bold] {status}")
                    if self.tool_executor:
                        tools = self.tool_executor.get_all_tools()
                        console.print(f"[bold]Available Tools:[/bold] {len(tools)}")
                elif selected == "list":
                    if self.tool_executor:
                        tools = self.tool_executor.get_all_tools()
                        console.print("\n[bold]Available Tools:[/bold]")
                        for tool in tools:
                            console.print(f"  [{Colors.ACCENT}]{tool['name']}[/{Colors.ACCENT}] - {tool.get('description', '')[:60]}")
                    else:
                        print_warning("Tools not initialized")
                elif selected == "enable":
                    if not self.tool_executor:
                        await self._initialize_tools()
                    self.enable_tools = True
                    print_success("Tools enabled")
                elif selected == "disable":
                    self.enable_tools = False
                    print_info("Tools disabled")
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
                # Show interactive menu
                servers = self.tool_executor.list_mcp_servers()
                connected = self.tool_executor.list_connected_mcp()
                options = [
                    ("status", f"📊 Show status ({len(connected)}/{len(servers)} connected)"),
                    ("list", "📋 List all servers"),
                    ("connect", "🔌 Connect to a server"),
                    ("disconnect", "🔴 Disconnect all"),
                ]
                selected = interactive_select("MCP options:", options)

                if selected == "status":
                    console.print(f"\n[bold]MCP Servers:[/bold] {len(servers)} configured, {len(connected)} connected")
                elif selected == "list":
                    console.print("\n[bold]MCP Servers:[/bold]")
                    for server in servers:
                        status = "✓" if server in connected else "○"
                        console.print(f"  {status} [{Colors.ACCENT}]{server}[/{Colors.ACCENT}]")
                elif selected == "connect":
                    # Show server selection
                    server_options = [(s, f"{'✓ ' if s in connected else '○ '}{s}") for s in servers]
                    server_selected = interactive_select("Select server to connect:", server_options)
                    if server_selected:
                        console.print(f"Connecting to {server_selected}...")
                        if await self.tool_executor.connect_mcp_server(server_selected):
                            print_success(f"Connected to {server_selected}")
                        else:
                            print_error(f"Failed to connect to {server_selected}")
                elif selected == "disconnect":
                    await self.tool_executor.disconnect_all_mcp()
                    print_info("Disconnected from all MCP servers")
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

    def _is_intent_only_response(self, text: str) -> bool:
        """응답이 의도만 표현하고 실제 내용이 없는지 확인"""
        if not text or len(text) < 10:
            return True

        # 의도 패턴으로 끝나는지 확인
        text_stripped = text.strip()
        for pattern in self.INTENT_PATTERNS:
            if text_stripped.endswith(pattern):
                return True
            # 패턴 뒤에 마침표/느낌표만 있는 경우도 체크
            if text_stripped.endswith(pattern + ".") or text_stripped.endswith(pattern + "。"):
                return True

        return False

    async def _request_detailed_report(self, messages: List[Dict], content_blocks: List) -> str:
        """상세 레포트를 요청하고 반환"""
        # 원본 messages를 수정하지 않도록 복사본 사용
        report_messages = messages.copy()

        # 현재 응답을 메시지에 추가
        report_messages.append({
            "role": "assistant",
            "content": content_blocks
        })

        # 상세 레포트 요청
        report_messages.append({
            "role": "user",
            "content": [{
                "type": "text",
                "text": """지금까지 수집한 모든 정보를 종합해서 **지금 바로** 상세한 분석 레포트를 작성해주세요.

형식:
## 📋 개요
(프로젝트/작업에 대한 간략한 설명)

## 📊 주요 발견사항
- 구체적인 수치와 통계 포함
- 파일 수, 라인 수, 패턴 등

## ⚠️ 문제점/이슈
- 발견된 문제 나열
- 심각도 표시 (높음/중간/낮음)

## 💡 권장사항
- 구체적인 개선 방안
- 다음 단계 제안

**중요: "작성하겠습니다" 같은 말 없이 바로 위 형식으로 레포트를 출력하세요.**"""
            }]
        })

        # 도구 없이 최종 레포트 요청
        report_response = await api.chat_with_tools(
            messages=report_messages,
            tools=[],  # 도구 없이
            temperature=config.get("temperature", 0.7),
            max_tokens=config.get("max_tokens", 4096),
        )

        report_blocks = report_response.get("content", [])
        report_text = ""
        for block in report_blocks:
            if block.get("type") == "text":
                report_text += block.get("text", "")

        return report_text

    async def _send_message_with_tools(self, message: str):
        """Send message to GLM with tool support"""
        # Add user message to session
        self.session.add_message("user", message)

        # Get available tools
        tools = self.tool_executor.get_all_tools()

        # Prepare messages for API
        messages = self.session.get_messages_for_api()

        # 시스템 프롬프트 추가 (에이전트 + 도구 규칙 결합)
        if self.current_agent:
            # 에이전트 프롬프트 + 도구 응답 규칙 결합
            combined_prompt = f"""{self.current_agent.system_prompt}

---
{self.TOOL_SYSTEM_PROMPT}"""
            messages.insert(0, {"role": "system", "content": combined_prompt})
        else:
            # 도구 모드 기본 시스템 프롬프트 추가
            messages.insert(0, {"role": "system", "content": self.TOOL_SYSTEM_PROMPT})

        self._cancelled = False
        max_iterations = 20  # 도구 호출 최대 횟수
        total_tool_calls = 0  # 총 도구 호출 횟수 추적

        try:
            for iteration in range(max_iterations):
                # 진행 상황 표시 (5회마다)
                if iteration > 0 and iteration % 5 == 0:
                    print_info(f"도구 호출 {iteration}회 진행 중...")

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
                    final_text = "".join(text_parts) if text_parts else ""

                    # 조건 1: 도구를 사용했는데 응답이 너무 짧은 경우
                    # 조건 2: 의도만 표현하는 패턴으로 끝나는 경우
                    needs_detailed_report = False

                    if total_tool_calls >= 1 and len(final_text) < 500:
                        needs_detailed_report = True
                        print_warning("응답이 너무 짧습니다. 상세 레포트 요청 중...")

                    elif self._is_intent_only_response(final_text):
                        needs_detailed_report = True
                        print_warning("의도만 표현된 응답입니다. 실제 레포트 요청 중...")

                    if needs_detailed_report:
                        report_text = await self._request_detailed_report(messages, content_blocks)

                        if report_text:
                            console.print(f"\n{report_text}")
                            self.session.add_message("assistant", report_text)

                        # 완료 통계 표시
                        if total_tool_calls > 0:
                            console.print(f"\n[dim]━━━ 📊 도구 사용 통계: {total_tool_calls}회 호출, {iteration + 1}회 반복 ━━━[/dim]")
                        break

                    # 정상적인 응답
                    if text_parts:
                        self.session.add_message("assistant", final_text)

                    # 완료 통계 표시 (도구 사용 시에만)
                    if total_tool_calls > 0:
                        console.print(f"\n[dim]━━━ 📊 도구 사용 통계: {total_tool_calls}회 호출 완료 ━━━[/dim]")
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

                    # 도구 호출 횟수 증가
                    total_tool_calls += 1

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

            else:
                # max_iterations 도달 시 최종 응답 강제 생성
                print_warning(f"도구 호출 {max_iterations}회 도달 (총 {total_tool_calls}회 도구 사용). 최종 레포트 생성 중...")

                # 도구 없이 최종 응답 요청 (강력한 프롬프트)
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "text",
                        "text": """⚠️ 도구 호출 한도에 도달했습니다.

**지금 바로** 수집한 모든 정보를 종합하여 최종 분석 레포트를 작성해주세요.

## 📋 개요
## 📊 주요 발견사항
## ⚠️ 문제점/이슈
## 💡 권장사항

위 형식으로 **실제 내용을 바로 출력**하세요. "작성하겠습니다" 같은 말은 하지 마세요."""
                    }]
                })

                final_response = await api.chat_with_tools(
                    messages=messages,
                    tools=[],  # 도구 없이 호출
                    temperature=config.get("temperature", 0.7),
                    max_tokens=config.get("max_tokens", 4096),
                )

                final_blocks = final_response.get("content", [])
                final_text = ""
                for block in final_blocks:
                    if block.get("type") == "text":
                        final_text += block.get("text", "")

                if final_text:
                    console.print(f"\n{final_text}")
                    self.session.add_message("assistant", final_text)

                # 완료 통계 표시
                console.print(f"\n[dim]━━━ 📊 도구 사용 통계: {total_tool_calls}회 호출, {max_iterations}회 반복 (한도 도달) ━━━[/dim]")

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
                if not self.tool_executor:
                    print_error("Tool executor not available")
                    return

                # 도구 루프 실행 (interactive와 동일한 로직)
                tools = self.tool_executor.get_all_tools()
                messages = [{"role": "user", "content": message}]

                # 시스템 프롬프트 추가
                messages.insert(0, {"role": "system", "content": self.TOOL_SYSTEM_PROMPT})

                max_iterations = 20
                total_tool_calls = 0

                for iteration in range(max_iterations):
                    response = await api.chat_with_tools(
                        messages=messages,
                        tools=tools,
                        temperature=config.get("temperature", 0.7),
                        max_tokens=config.get("max_tokens", 4096),
                    )

                    content_blocks = response.get("content", [])
                    stop_reason = response.get("stop_reason", "")

                    text_parts = []
                    tool_uses = []

                    for block in content_blocks:
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_uses.append(block)

                    # 텍스트 출력
                    if text_parts:
                        print("".join(text_parts))

                    # 도구 호출 없으면 종료
                    if not tool_uses or stop_reason != "tool_use":
                        break

                    # 도구 실행
                    tool_results = []
                    for tool_use in tool_uses:
                        tool_name = tool_use.get("name", "")
                        tool_input = tool_use.get("input", {})
                        tool_id = tool_use.get("id", "")

                        print(f"\n🔧 Using tool: {tool_name}")
                        result = await self.tool_executor.execute_tool(tool_name, tool_input)

                        if result.content:
                            content_preview = result.content[:300] + "..." if len(result.content) > 300 else result.content
                            print(content_preview)

                        tool_results.append(
                            self.tool_executor.format_tool_result_for_api(tool_id, result)
                        )
                        total_tool_calls += 1

                    # 메시지에 추가
                    messages.append({"role": "assistant", "content": content_blocks})
                    messages.append({"role": "user", "content": tool_results})

                if total_tool_calls > 0:
                    print(f"\n[도구 {total_tool_calls}회 사용]")

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
