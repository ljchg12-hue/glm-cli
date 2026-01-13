"""Skill System for GLM CLI

Lightweight skill system with 10 core skills.
Skills are predefined workflows/prompts for common tasks.
Supports loading custom skills from ~/.glm/skills/
"""

import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Any


@dataclass
class Skill:
    """Skill definition"""
    name: str
    description: str
    prompt_template: str
    keywords: List[str]
    requires_args: bool = False


class SkillRegistry:
    """Registry for managing skills"""

    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self._loaded = False

    def register(self, skill: Skill) -> None:
        """Register a skill"""
        self.skills[skill.name] = skill

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get skill by name"""
        return self.skills.get(name)

    def list_skills(self) -> List[Dict[str, str]]:
        """List all available skills"""
        return [
            {"name": s.name, "description": s.description}
            for s in self.skills.values()
        ]

    def find_skill_by_keyword(self, text: str) -> Optional[Skill]:
        """Find skill matching keywords in text"""
        text_lower = text.lower()

        for skill in self.skills.values():
            for keyword in skill.keywords:
                if keyword.lower() in text_lower:
                    return skill

        return None

    def get_skill_prompt(self, name: str, args: str = "") -> Optional[str]:
        """Get expanded prompt for skill"""
        skill = self.get_skill(name)
        if skill:
            if "{args}" in skill.prompt_template:
                return skill.prompt_template.format(args=args)
            return skill.prompt_template
        return None

    def load_external_skills(self, skills_dir: Optional[str] = None) -> int:
        """Load external skills from directory

        Args:
            skills_dir: Directory to load skills from. Defaults to ~/.glm/skills/

        Returns:
            Number of skills loaded
        """
        if skills_dir is None:
            skills_dir = Path.home() / ".glm" / "skills"
        else:
            skills_dir = Path(skills_dir)

        if not skills_dir.exists():
            return 0

        loaded = 0
        for skill_file in skills_dir.glob("*.md"):
            try:
                skill = self._parse_skill_file(skill_file)
                if skill and skill.name not in self.skills:
                    self.register(skill)
                    loaded += 1
            except Exception as e:
                print(f"Error loading skill {skill_file}: {e}")

        return loaded

    def _parse_skill_file(self, file_path: Path) -> Optional[Skill]:
        """Parse skill definition from markdown file

        Expected format:
        ---
        name: skill-name
        description: Short description
        keywords: [keyword1, keyword2]
        requires_args: false
        ---
        Prompt template content here...
        """
        content = file_path.read_text(encoding='utf-8')

        # Parse YAML frontmatter
        frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not frontmatter_match:
            return None

        try:
            frontmatter = yaml.safe_load(frontmatter_match.group(1))
        except yaml.YAMLError:
            return None

        body = frontmatter_match.group(2).strip()

        name = frontmatter.get('name', file_path.stem)
        description = frontmatter.get('description', '')
        keywords = frontmatter.get('keywords', [])
        requires_args = frontmatter.get('requires_args', False)

        if isinstance(keywords, str):
            keywords = [keywords]

        return Skill(
            name=name,
            description=description,
            prompt_template=body,
            keywords=keywords,
            requires_args=requires_args
        )


# Global registry
skill_registry = SkillRegistry()


# Built-in skills (10 core skills)
BUILTIN_SKILLS = [
    Skill(
        name="commit",
        description="Create a well-formatted git commit",
        keywords=["commit", "커밋"],
        requires_args=False,
        prompt_template="""Create a git commit for the current changes.

Steps:
1. Run `git status` to see changes
2. Run `git diff --staged` or `git diff` to understand changes
3. Create a commit message following conventional commits format:
   - type: feat, fix, docs, style, refactor, test, chore
   - scope: optional area of change
   - description: concise summary

Example: feat(auth): add OAuth2 login support

Execute the commit after confirming the message."""
    ),
    Skill(
        name="review",
        description="Review code changes for quality and issues",
        keywords=["review", "리뷰", "검토"],
        requires_args=False,
        prompt_template="""Review the recent code changes.

Focus areas:
1. **Security**: Vulnerabilities, injection risks
2. **Quality**: Code style, readability, maintainability
3. **Performance**: Bottlenecks, inefficiencies
4. **Best Practices**: Design patterns, SOLID

Steps:
1. Get changes: `git diff HEAD~1` or `git diff --staged`
2. Analyze each file
3. Rate: A/B/C/D/F
4. List issues by severity
5. Provide actionable suggestions"""
    ),
    Skill(
        name="test",
        description="Run tests and fix failures",
        keywords=["test", "테스트"],
        requires_args=False,
        prompt_template="""Run the test suite and handle results.

Steps:
1. Detect test framework (pytest, jest, vitest, etc.)
2. Run tests with coverage if available
3. If failures:
   - Analyze error messages
   - Identify root cause
   - Suggest or apply fixes
4. Report coverage summary"""
    ),
    Skill(
        name="docs",
        description="Generate or update documentation",
        keywords=["docs", "문서", "readme"],
        requires_args=True,
        prompt_template="""Generate or update documentation.

Target: {args}

Documentation types:
- README.md: Project overview, setup, usage
- API docs: Endpoints, parameters, responses
- Code comments: JSDoc, docstrings
- Architecture docs: System design

Ensure:
- Clear structure
- Code examples
- Up-to-date information"""
    ),
    Skill(
        name="refactor",
        description="Refactor code to improve structure",
        keywords=["refactor", "리팩토링"],
        requires_args=True,
        prompt_template="""Refactor the specified code.

Target: {args}

Refactoring goals:
- Reduce complexity
- Improve readability
- Apply design patterns
- Remove duplication
- Enhance maintainability

Ensure tests still pass after refactoring."""
    ),
    Skill(
        name="audit",
        description="Perform security audit on codebase",
        keywords=["audit", "감사", "security", "보안"],
        requires_args=False,
        prompt_template="""Perform a security audit on the codebase.

Check for:
1. **OWASP Top 10**
   - Injection flaws
   - Broken authentication
   - Sensitive data exposure
   - XXE, XSS, CSRF
   - Security misconfigurations

2. **Dependencies**
   - Known vulnerabilities (npm audit, pip-audit)
   - Outdated packages

3. **Secrets**
   - Hardcoded credentials
   - API keys in code

4. **Access Control**
   - Authorization checks
   - Input validation

Report findings with severity and remediation steps."""
    ),
    Skill(
        name="optimize",
        description="Optimize code performance",
        keywords=["optimize", "최적화", "performance", "성능"],
        requires_args=True,
        prompt_template="""Optimize the specified code or component.

Target: {args}

Optimization areas:
1. **Algorithm**: Time/space complexity
2. **Database**: Query optimization, indexing
3. **Memory**: Leaks, excessive allocation
4. **Bundle**: Code splitting, tree shaking
5. **Caching**: Memoization, HTTP caching

Profile before and after to measure improvement."""
    ),
    Skill(
        name="git-push",
        description="Push changes to remote repository",
        keywords=["push", "푸시"],
        requires_args=False,
        prompt_template="""Push local commits to the remote repository.

Steps:
1. Check current branch: `git branch --show-current`
2. Check remote status: `git status`
3. Pull latest changes if needed: `git pull --rebase`
4. Push: `git push origin <branch>`
5. Verify push was successful"""
    ),
    Skill(
        name="explore",
        description="Explore and understand codebase structure",
        keywords=["explore", "탐색", "structure", "구조"],
        requires_args=True,
        prompt_template="""Explore and explain the codebase.

Focus: {args}

Analysis:
1. Directory structure
2. Entry points
3. Key components/modules
4. Data flow
5. Dependencies

Provide a clear overview of how the code is organized."""
    ),
    Skill(
        name="fix",
        description="Fix a bug or issue",
        keywords=["fix", "수정", "bug", "버그"],
        requires_args=True,
        prompt_template="""Fix the reported issue.

Issue: {args}

Process:
1. Understand the bug report
2. Reproduce the issue
3. Identify root cause
4. Implement fix
5. Add test to prevent regression
6. Verify fix works"""
    ),
]


def register_builtin_skills():
    """Register built-in skills"""
    for skill in BUILTIN_SKILLS:
        skill_registry.register(skill)


# Auto-register built-in skills
register_builtin_skills()
