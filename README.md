# GLM CLI

Claude Code 스타일의 대화형 AI CLI 터미널. Z.AI API를 통해 GLM-4 모델을 사용합니다.

## 특징

- **대화형 터미널**: 스트리밍 응답, 세션 관리
- **도구 시스템**: Read, Write, Edit, Bash, Glob, Grep
- **MCP 통합**: `~/.mcp.json` 서버 자동 연동
- **에이전트 시스템**: 8개 전문 에이전트
- **스킬 시스템**: 10개 워크플로우 단축키

## 설치

```bash
# 의존성 설치
pip install aiohttp prompt_toolkit rich pyyaml

# 실행 권한
chmod +x ~/.local/lib/glm-cli/main.py

# PATH 추가 (선택)
ln -s ~/.local/lib/glm-cli/main.py ~/.local/bin/glm
```

## 환경 변수

```bash
export ZAI_API_KEY="your-api-key"
# 또는
export GLM_API_KEY="your-api-key"
```

## 사용법

### 기본 실행

```bash
glm                       # 대화형 모드
glm --tools               # 도구 모드 활성화
glm -p "안녕하세요"        # 단발성 질의
glm -c                    # 이전 세션 이어하기
```

### 키보드 단축키

| 단축키 | 동작 |
|--------|------|
| `Ctrl+C` | 종료 |
| `Ctrl+D` | 종료 |
| `Ctrl+Z` | 종료 |
| `Ctrl+L` | 화면 지우기 |

### 슬래시 명령어

#### 기본
```
/help         도움말
/exit         종료
/clear        화면 지우기
/version      버전 정보
/model        모델 정보
/session      세션 정보
```

#### 도구 (--tools 모드)
```
/tools list   도구 목록
/tools enable 도구 활성화
/mcp list     MCP 서버 목록
/mcp connect <name>  MCP 서버 연결
```

#### 에이전트
```
/agent list           에이전트 목록
/agent use <name>     에이전트 활성화
/agent clear          에이전트 비활성화
```

#### 스킬 (단축키)
```
/commit       Git 커밋 워크플로우
/review       코드 리뷰
/test         테스트 실행
/docs <file>  문서 생성
/refactor <target>  리팩토링
/audit        보안 감사
/optimize <target>  성능 최적화
/fix <issue>  버그 수정
/explore <area>  코드베이스 탐색
```

## 에이전트

| 이름 | 설명 |
|------|------|
| `code-reviewer` | 코드 리뷰 전문가 |
| `backend-dev` | 백엔드 API 전문가 |
| `frontend-dev` | 프론트엔드 UI/UX 전문가 |
| `devops-eng` | DevOps/인프라 전문가 |
| `doc-writer` | 기술 문서 전문가 |
| `db-architect` | 데이터베이스 설계 전문가 |
| `test-runner` | 테스트 자동화 전문가 |
| `orchestrator` | 태스크 조율자 |

## 도구

| 이름 | 설명 |
|------|------|
| `read_file` | 파일 읽기 |
| `write_file` | 파일 쓰기 |
| `edit_file` | 파일 수정 (문자열 교체) |
| `bash` | 명령어 실행 |
| `glob` | 파일 패턴 검색 |
| `grep` | 내용 검색 |

## MCP 서버

`~/.mcp.json` 파일에서 MCP 서버 설정을 자동으로 로드합니다.

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "your-token"
      }
    }
  }
}
```

## 설정

설정 파일: `~/.glm/config.json`

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "api_base": "https://api.z.ai/api/anthropic/v1",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

## 라이선스

MIT License

## 기여

이슈와 PR을 환영합니다.

---

**버전**: 1.2.0
**GitHub**: https://github.com/ljchg12-hue/glm-cli
