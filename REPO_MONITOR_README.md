# GitHub Repository Monitor

A Python script to help SREs monitor GitHub repositories for recent activity and security vulnerabilities.

## Features

- 🔍 **Monitors multiple repository sources**:
  - Repositories tagged with `data-dragons` topic
  - IAC repositories from `dsg-cirium-cdp-tools/scripts/github-codeowners/iac-repos.txt`

- 📊 **Tracks recent activity**:
  - Recent commits (configurable time window)
  - Recent pull requests
  
- 🚨 **Security monitoring**:
  - Open Dependabot alerts
  - Severity breakdown (critical, high, medium, low)
  - CVE tracking

- 📝 **Intelligent reporting**:
  - Prioritizes repos with both activity and vulnerabilities
  - Groups repos by risk level
  - Exports to text and JSON formats


**Prerequisites:**
```bash
# Install gh CLI (if not already installed)
brew install gh  # macOS

# Authenticate
gh auth login

# Set up virtual environment (if not already done)
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Usage:**
```bash
# Activate virtual environment
source venv/bin/activate

# Basic usage - monitor last 7 days
python github_repo_watcher.py

# Monitor last 14 days
python github_repo_watcher.py --days 14

# Save report to file
python github_repo_watcher.py --output sre_report_$(date +%Y%m%d).txt

# Filter specific repos
python github_repo_watcher.py --filter data-dragons --filter cdp-tools
```

## Report Structure

The generated report includes:

### 📊 Summary Section
- Total repositories monitored
- Repos with recent activity
- Repos with vulnerabilities
- Total Dependabot alerts
- Severity breakdown

### 🔥 High Priority Section
**Active repos with vulnerabilities** - These need immediate attention:
- Shows repos with recent commits/PRs AND open security alerts
- Lists critical/high severity vulnerabilities
- Direct links to alerts

### ⚠️ Vulnerable Repos Section
Repos with security issues but no recent activity:
- May be dormant but still need patching
- Shows severity breakdown
- Lists top critical/high alerts

### ✅ Active Clean Repos
Repos with recent activity but no vulnerabilities - good state!

### 😴 Quiet Repos
No activity, no vulnerabilities - monitoring only

## Output Files

The script generates two files:

1. **Text report** (`report.txt`): Human-readable formatted report
2. **JSON data** (`report.json`): Machine-readable data for automation

## Example Output

```
================================================================================
GitHub Repository Monitoring Report
Generated: 2025-10-14 10:30:00
Monitoring Period: Last 7 days
================================================================================

📊 SUMMARY
--------------------------------------------------------------------------------
Total Repositories: 45
Repos with Recent Activity: 12
Repos with Vulnerabilities: 8
Total Open Dependabot Alerts: 23

🚨 VULNERABILITY SEVERITY BREAKDOWN
--------------------------------------------------------------------------------
  CRITICAL: 2
  HIGH: 8
  MEDIUM: 10
  LOW: 3

🔥 HIGH PRIORITY: Active Repos with Vulnerabilities
--------------------------------------------------------------------------------

📦 LexisNexis-RBA/data-dragons-api
   Activity: 15 commits, 3 PRs
   Vulnerabilities: 5 open alerts
   ⚠️  Critical/High Severity Alerts:
      - [HIGH] axios: Improper handling of user-supplied URLs
        https://github.com/LexisNexis-RBA/data-dragons-api/security/dependabot/42
```

## Automation Ideas

### Daily Cron Job
```bash
# Add to crontab (crontab -e)
0 9 * * * cd /path/to/sre_agent && source venv/bin/activate && python github_repo_watcher.py --output /var/log/repo_monitor_$(date +\%Y\%m\%d).txt
```

### Slack Integration
```bash
# Send high priority alerts to Slack
cd /path/to/sre_agent && source venv/bin/activate && \
  python github_repo_watcher.py --output report.txt && \
  grep -A 20 "HIGH PRIORITY" report.txt | \
  slack-cli send --channel sre-alerts
```

### GitHub Actions
```yaml
name: Weekly Repo Audit
on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9am
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'
      - name: Install dependencies
        run: |
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt
      - name: Run monitor
        run: |
          source venv/bin/activate
          python github_repo_watcher.py --output report.txt
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: weekly-report
          path: report.txt
```

## Permissions Required

The script requires the following GitHub permissions:
- `repo` - Read access to repositories
- `security_events` - Read Dependabot alerts
- `read:org` - List organization repositories

When using `gh` CLI, these are typically granted during `gh auth login`.

## Troubleshooting

### "gh CLI not found"
```bash
# Install gh CLI
brew install gh  # macOS
# Or download from https://cli.github.com/
```

### "Authentication required"
```bash
gh auth login
# Follow the prompts to authenticate
```

### "Permission denied on security alerts"
```bash
# Ensure your token has security_events scope
gh auth refresh -s security_events
```

### Rate limiting
If monitoring many repos:
```bash
# Check rate limit status
gh api rate_limit

# Add delays between repos if needed
```

## Best Practices

1. **Run regularly**: Schedule daily or weekly runs to catch issues early
2. **Focus on high priority**: Address repos with both activity and vulnerabilities first
3. **Track trends**: Compare reports over time to see if vulnerability count is improving
4. **Automate responses**: Use JSON output to trigger automated remediation workflows
5. **Share reports**: Distribute to team leads and security team

## Contributing

To extend this script:
- Add more metrics (issue counts, code coverage, etc.)
- Integrate with JIRA/Linear for ticket creation
- Add email notifications for critical vulnerabilities
- Create dashboard visualization from JSON output

## License

Internal use for LexisNexis Risk Solutions SRE team.
