"""Agent System for GLM CLI

Lightweight agent system with 8 core agents.
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Agent:
    """Agent definition"""
    name: str
    description: str
    system_prompt: str
    tools: List[str]
    keywords: List[str]


class AgentRegistry:
    """Registry for managing agents"""

    def __init__(self):
        self.agents: Dict[str, Agent] = {}
        self._loaded = False

    def load_agents(self, agents_dir: Optional[str] = None) -> None:
        """Load agents from directory"""
        if self._loaded:
            return

        if agents_dir is None:
            # Default to the agents directory in glm-cli
            agents_dir = Path(__file__).parent.parent / "agents"

        agents_dir = Path(agents_dir)
        if not agents_dir.exists():
            return

        for agent_file in agents_dir.glob("*.md"):
            try:
                agent = self._parse_agent_file(agent_file)
                if agent:
                    self.agents[agent.name] = agent
            except Exception as e:
                print(f"Error loading agent {agent_file}: {e}")

        self._loaded = True

    def _parse_agent_file(self, file_path: Path) -> Optional[Agent]:
        """Parse agent definition from markdown file"""
        content = file_path.read_text(encoding='utf-8')

        # Parse YAML frontmatter
        frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not frontmatter_match:
            return None

        frontmatter = yaml.safe_load(frontmatter_match.group(1))
        body = frontmatter_match.group(2).strip()

        name = frontmatter.get('name', file_path.stem)
        description = frontmatter.get('description', '')
        tools = frontmatter.get('tools', '').split(', ') if frontmatter.get('tools') else []
        keywords = frontmatter.get('keywords', [])

        return Agent(
            name=name,
            description=description,
            system_prompt=body,
            tools=tools,
            keywords=keywords if isinstance(keywords, list) else [keywords]
        )

    def get_agent(self, name: str) -> Optional[Agent]:
        """Get agent by name"""
        self.load_agents()
        return self.agents.get(name)

    def list_agents(self) -> List[Dict[str, str]]:
        """List all available agents"""
        self.load_agents()
        return [
            {"name": a.name, "description": a.description}
            for a in self.agents.values()
        ]

    def find_agent_by_keyword(self, text: str) -> Optional[Agent]:
        """Find agent matching keywords in text"""
        self.load_agents()
        text_lower = text.lower()

        for agent in self.agents.values():
            for keyword in agent.keywords:
                if keyword.lower() in text_lower:
                    return agent

        return None

    def get_agent_system_prompt(self, name: str) -> Optional[str]:
        """Get system prompt for agent"""
        agent = self.get_agent(name)
        if agent:
            return f"""You are {agent.name}.

{agent.description}

{agent.system_prompt}
"""
        return None


# Global registry
agent_registry = AgentRegistry()


# Built-in agents (lightweight versions)
BUILTIN_AGENTS = {
    "code-reviewer": Agent(
        name="code-reviewer",
        description="Expert code reviewer for quality and security",
        keywords=["review", "리뷰", "코드리뷰", "검토"],
        tools=["read_file", "glob", "grep", "bash"],
        system_prompt="""You are a senior code reviewer.

## Review Focus
1. **Security**: SQL injection, XSS, CSRF, auth flaws
2. **Quality**: Code style, complexity, readability
3. **Performance**: N+1 queries, memory leaks, bottlenecks
4. **Best Practices**: Design patterns, SOLID principles

## Output Format
- Rate: A/B/C/D/F
- Issues: List with severity (Critical/High/Medium/Low)
- Suggestions: Actionable improvements
"""
    ),
    "backend-dev": Agent(
        name="backend-dev",
        description="Backend API and server-side specialist",
        keywords=["backend", "백엔드", "api", "서버"],
        tools=["read_file", "write_file", "edit_file", "bash", "glob", "grep"],
        system_prompt="""You are a senior backend developer.

## Expertise
- **Runtime**: Node.js, Python, Deno
- **Frameworks**: Express, FastAPI, NestJS, Django
- **Databases**: PostgreSQL, MySQL, MongoDB, Redis
- **API**: REST, GraphQL, tRPC

## Best Practices
- Input validation at boundaries
- Proper error handling
- Database transaction management
- Authentication/Authorization
"""
    ),
    "frontend-dev": Agent(
        name="frontend-dev",
        description="Frontend UI/UX specialist",
        keywords=["frontend", "프론트엔드", "ui", "react", "vue"],
        tools=["read_file", "write_file", "edit_file", "bash", "glob", "grep"],
        system_prompt="""You are a senior frontend developer.

## Expertise
- **Frameworks**: React, Vue, Svelte, Next.js
- **Styling**: Tailwind CSS, CSS-in-JS, SCSS
- **State**: Redux, Zustand, React Query
- **Build**: Vite, Webpack, esbuild

## Best Practices
- Component composition
- Accessibility (a11y)
- Performance optimization
- Responsive design
"""
    ),
    "devops-eng": Agent(
        name="devops-eng",
        description="DevOps and infrastructure specialist",
        keywords=["devops", "deploy", "배포", "docker", "ci/cd"],
        tools=["read_file", "write_file", "edit_file", "bash", "glob", "grep"],
        system_prompt="""You are a DevOps engineer.

## Expertise
- **Containers**: Docker, Podman, containerd
- **Orchestration**: Kubernetes, Docker Compose
- **CI/CD**: GitHub Actions, GitLab CI, Jenkins
- **Cloud**: AWS, GCP, Azure

## Best Practices
- Infrastructure as Code
- 12-factor app methodology
- Security scanning
- Monitoring and logging
"""
    ),
    "doc-writer": Agent(
        name="doc-writer",
        description="Technical documentation specialist",
        keywords=["docs", "문서", "readme", "documentation"],
        tools=["read_file", "write_file", "edit_file", "glob", "grep"],
        system_prompt="""You are a technical writer.

## Documentation Types
- README files
- API documentation
- User guides
- Architecture docs

## Best Practices
- Clear structure
- Code examples
- Visual diagrams
- Versioning
"""
    ),
    "db-architect": Agent(
        name="db-architect",
        description="Database design and optimization specialist",
        keywords=["database", "db", "sql", "schema", "데이터베이스"],
        tools=["read_file", "write_file", "edit_file", "bash", "glob", "grep"],
        system_prompt="""You are a database architect.

## Expertise
- **Relational**: PostgreSQL, MySQL, SQLite
- **NoSQL**: MongoDB, Redis, DynamoDB
- **Design**: Normalization, indexing, partitioning
- **Performance**: Query optimization, EXPLAIN analysis

## Best Practices
- Data integrity constraints
- Proper indexing strategy
- Migration management
- Backup and recovery
"""
    ),
    "test-runner": Agent(
        name="test-runner",
        description="Test automation and quality assurance",
        keywords=["test", "테스트", "testing", "coverage"],
        tools=["read_file", "write_file", "edit_file", "bash", "glob", "grep"],
        system_prompt="""You are a test automation engineer.

## Testing Types
- Unit tests
- Integration tests
- E2E tests
- Performance tests

## Frameworks
- Jest, Vitest (JS)
- pytest (Python)
- Playwright, Cypress (E2E)

## Best Practices
- TDD: RED -> GREEN -> REFACTOR
- High coverage on critical paths
- Fast feedback loops
"""
    ),
    "orchestrator": Agent(
        name="orchestrator",
        description="Task coordinator and workflow manager",
        keywords=["orchestrate", "coordinate", "조율", "관리"],
        tools=["read_file", "glob", "grep", "bash"],
        system_prompt="""You are a project orchestrator.

## Responsibilities
- Break down complex tasks
- Coordinate between specialists
- Track progress
- Ensure quality

## Workflow
1. Analyze requirements
2. Create task breakdown
3. Delegate to specialists
4. Review and integrate
5. Validate output
"""
    ),
}


def register_builtin_agents():
    """Register built-in agents"""
    for name, agent in BUILTIN_AGENTS.items():
        agent_registry.agents[name] = agent
    agent_registry._loaded = True


# Auto-register built-in agents
register_builtin_agents()
