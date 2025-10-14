# SRE Agent - Copilot Instructions

## Project Overview
SRE automation toolkit for managing Customer Data Platform (CDP) operations across Jira, GitHub (196 repos), and AWS. Built for AI agent consumption with structured JSON outputs and human-readable reports.

## Architecture & Components

### Core Scripts (All require venv activation)
1. **`github_repo_watcher.py`** - Monitors 196 repos across 2 GitHub orgs
   - **LexisNexis-RBA**: Discovers via `data-dragons` topic search
   - **lexisnexis-iac**: Reads from `dsg-cirium-cdp-tools/scripts/github-codeowners/iac-repos.txt` (auto-prefixes with org)
   - Uses `gh` CLI (not Python GitHub lib) for all API calls
   - Parallel processing: 10 workers default, ~30 seconds for 196 repos
   - Critical pattern: Silently handles errors in parallel to avoid spam

2. **`jira_support_board_watcher.py`** - CDPSUPPORT board triage automation
   - Uses direct Jira REST API (not Python SDK)
   - Tracks: triage items, stale items (>1 day), unacknowledged customer comments
   - Board ID hardcoded: `404` (from config.yaml)

### Data Flow
```
gh CLI → GitHubRepoMonitor → JSON output → Agent consumption
Jira API → JiraBoardWatcher → TriageReport → Daily triage meetings
MCP servers → AI agent → AWS cost analysis (no Python script - MCP only)
```

## Critical Workflows

### Setup (Always First!)
```bash
source venv/bin/activate  # REQUIRED for all scripts
```

### GitHub Monitoring
```bash
# Agent-friendly JSON output (for programmatic use)
python github_repo_watcher.py --json --quiet

# Human-readable report (saves to docs/reports/)
python github_repo_watcher.py --output docs/reports/$(date +%Y%m%d).txt

# Performance tuning
python github_repo_watcher.py --workers 20  # Increase parallelism
```

### Running Jira Triage
```bash
python jira_support_board_watcher.py  # Outputs to stdout
```

### Report Storage Convention
- All generated reports go to `docs/reports/` directory
- Reports are gitignored by default
- Use date-based naming: `YYYYMMDD` format recommended

## Project-Specific Conventions

### 1. GitHub CLI Over Libraries
**Why**: Avoids Python dependency versioning issues, leverages existing auth
- All GitHub operations use `subprocess.run(['gh', ...])` 
- Pattern: `_run_gh_command()` → wraps subprocess → returns stdout or None
- Error handling: Silent failures in parallel mode to prevent spam

### 2. Dual Organization Strategy
**Critical**: IAC repos require special handling
```python
# iac-repos.txt contains ONLY repo names (no org prefix)
# Example file content: "dsg-cirium-aef-core-account-dev"
# Code prefixes with: "lexisnexis-iac/{repo_name}"
```

### 3. Parallel Processing Pattern
```python
# Always use partial() for fixed parameters
analyze_func = partial(self.analyze_repo, days=days, verbose=False)
with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    future_to_repo = {executor.submit(analyze_func, repo): repo for repo in repos}
```

### 4. Output Formats
- **`--json`**: Machine-readable, full detail, for agents
- **`--json --quiet`**: Suppress progress, only JSON output
- **Human reports**: Prioritized sections (High Priority → Vulnerable → Active → Quiet)

### 5. Configuration Pattern
- `config.yaml`: High-level settings (board IDs, project keys)
- Environment vars: Credentials (via MCP servers, not in code)
- No `.env` file committed (in .gitignore)

## Integration Points

### MCP (Model Context Protocol) Servers
Used by AI agents, NOT by Python scripts:
- **Atlassian MCP**: Jira ticket operations, board queries
- **AWS Billing MCP**: Cost analysis, optimization recommendations (no Python implementation)
- **GitHub**: Via `gh` CLI (not MCP)

### External Dependencies
- `gh` CLI: Must be installed and authenticated (`gh auth login`)
- Jira: Direct API access via requests library
- AWS: Through MCP servers in AI agent context only

## File Organization
```
├── github_repo_watcher.py       # Main repo scanner
├── jira_support_board_watcher.py # Jira triage tool
├── config.yaml                   # Non-sensitive config
├── requirements.txt              # Python deps
├── docs/
│   ├── reports/                  # Generated reports go here (gitignored)
│   └── github_repo_watcher_quickstart.md  # User guide (committed)
└── .github/
    ├── copilot-instructions.md   # This file
    └── chatmodes/SRE.chatmode.md # AI agent behavior config
```

## Common Tasks

### Adding New Repository Source
Edit `get_all_repos()` in `github_repo_watcher.py`:
```python
def get_all_repos(self) -> List[str]:
    repos = set()
    repos.update(self.get_data_dragons_repos())  # Topic search
    repos.update(self.get_iac_repos_from_file()) # From file
    # Add new source here
    return sorted(list(repos))
```

### Modifying Report Priorities
See `generate_report()` in `github_repo_watcher.py`:
1. High Priority: Active repos WITH vulnerabilities
2. Vulnerable: Inactive repos with vulnerabilities  
3. Active Clean: Activity, no vulnerabilities
4. Quiet: No activity, no vulnerabilities

### Debugging Parallel Processing
```python
# Temporarily disable parallelism
python github_repo_watcher.py --no-parallel
```

## Testing & Validation
```bash
# Quick test (single repo filter)
python github_repo_watcher.py --filter cdp-tools --days 1

# Verify both orgs are fetched
python -c "from github_repo_watcher import GitHubRepoMonitor; \
  m = GitHubRepoMonitor(); \
  repos = m.get_all_repos(); \
  print(f'Total: {len(repos)}, RBA: {sum(1 for r in repos if r.startswith(\"LexisNexis-RBA\"))}, IAC: {sum(1 for r in repos if r.startswith(\"lexisnexis-iac\"))}')"
```

## Known Limitations
- GitHub rate limiting: Monitor with `gh api rate_limit`
- Parallel workers: Max 20 recommended (API rate limits)
- Dependabot alerts: Requires `security_events` scope in `gh` auth
- IAC repos file: Single source of truth, must be kept current
