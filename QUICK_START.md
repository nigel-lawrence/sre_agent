# Repository Monitor - Quick Start Guide

## ✅ Setup Complete!

Your repository monitoring system is ready to use. The script successfully monitored **120 repositories** and found **20 with recent activity** in the last 14 days.

## Quick Commands

```bash
# Activate virtual environment (always do this first!)
source venv/bin/activate

# Basic run
python github_repo_watcher.py

# Save to reports folder
python github_repo_watcher.py --days 14 --output reports/$(date +%Y%m%d)_report.txt

# Filter specific repos
python github_repo_watcher.py --filter cdp-airflow --days 7
```

### Example: Daily SRE Check
```bash
#!/bin/bash
# Save as: daily_sre_check.sh

cd /Users/lawrencen/code/sre_agent
source venv/bin/activate

# Run monitor
python github_repo_watcher.py \
  --days 7 \
  --output "reports/sre_$(date +%Y%m%d).txt"

# Show summary
echo "=== Today's Summary ==="
grep "📊 SUMMARY" -A 10 "reports/sre_$(date +%Y%m%d).txt"
```

### Example: Weekly Security Audit
```bash
#!/bin/bash
# Save as: weekly_security_audit.sh

cd /Users/lawrencen/code/sre_agent
source venv/bin/activate

python github_repo_watcher.py \
  --days 7 \
  --output "reports/weekly_$(date +%Y%m%d).txt"

# Check for vulnerabilities
if grep -q "🔥 HIGH PRIORITY" "reports/weekly_$(date +%Y%m%d).txt"; then
  echo "⚠️  HIGH PRIORITY VULNERABILITIES FOUND!"
  grep "🔥 HIGH PRIORITY" -A 30 "reports/weekly_$(date +%Y%m%d).txt"
fi
```

## 📊 What the Script Monitors

### Repository Sources
- ✅ All repos with `data-dragons` topic (found 120 repos)
- ✅ IAC repos from `dsg-cirium-cdp-tools/scripts/github-codeowners/iac-repos.txt`

### Activity Tracking
- Commits in the specified time window
- Pull requests (open, merged, closed)
- Last activity timestamps

### Security Monitoring
- Dependabot vulnerability alerts (currently 0 across all repos 🎉)
- Severity levels: Critical, High, Medium, Low
- CVE tracking and links

## 📈 Understanding the Report

### Report Sections Priority

1. **🔥 HIGH PRIORITY** - Active repos WITH vulnerabilities
   - These need immediate attention
   - Currently: None! ✅

2. **⚠️ VULNERABLE** - Repos with security issues but no recent activity
   - May be dormant but still need patching
   - Currently: None! ✅

3. **✅ ACTIVE CLEAN** - Active repos without vulnerabilities
   - Your current state: 20 repos with recent PRs
   - Good state - keep monitoring

4. **😴 QUIET** - No activity, no issues
   - 100 repos in this state
   - Monitoring only

## 🔧 Customization Options

### Change Time Window
```bash
# Last 24 hours of activity
python github_repo_watcher.py --days 1

# Last month
python github_repo_watcher.py --days 30
```

### Filter Repos
```bash
# Only cdp-related repos
python github_repo_watcher.py --filter cdp

# Multiple filters
python github_repo_watcher.py --filter airflow --filter streaming
```

### JSON Output for Automation
```bash
# The script automatically saves JSON to repo_monitor_results.json
# Use it for automation:
python -c "
import json
with open('repo_monitor_results.json') as f:
    data = json.load(f)
    active = [r for r in data if r['has_activity']]
    print(f'Active repos: {len(active)}')
"
```

## 📅 Automation Setup

### Add to Crontab
```bash
# Edit crontab
crontab -e

# Add daily run at 9 AM
0 9 * * * cd /Users/lawrencen/code/sre_agent && source venv/bin/activate && python github_repo_watcher.py --output /tmp/daily_report.txt

# Weekly report every Monday
0 9 * * 1 cd /Users/lawrencen/code/sre_agent && source venv/bin/activate && python github_repo_watcher.py --days 7 --output ~/reports/weekly_$(date +\%Y\%m\%d).txt
```

### Create Reports Directory
```bash
mkdir -p ~/reports
mkdir -p /Users/lawrencen/code/sre_agent/reports
```

## 🎯 Current State (Last Run)

```
Total Repositories: 120
Active (last 14 days): 20
With Vulnerabilities: 0
Total Dependabot Alerts: 0
```

### Most Active Repos Recently
- `dsg-cirium-cdp-gut-collections-pipeline`: 17 PRs
- `dsg-cirium-cdp`: 15 PRs
- `dsg-cirium-cdp-config-build`: 11 PRs
- `dsg-cirium-cdp-streaming`: 8 PRs
- `dsg-cirium-cdp-airflow-dag-scripts`: 5 PRs

## 🆘 Troubleshooting

### "gh CLI not found"
```bash
brew install gh
gh auth login
```

### "Permission denied"
```bash
# Refresh authentication with security_events scope
gh auth refresh -s security_events
```

### Rate Limiting
If you hit GitHub rate limits:
```bash
# Check rate limit status
gh api rate_limit

# Wait or spread out monitoring runs
```

## 📚 Additional Resources

- Full documentation: `REPO_MONITOR_README.md`
- Test script: `test_repo_monitor.py`
- API version (if needed): `repo_monitor.py`

## 🔐 Security Notes

- The script only reads data, never modifies repos
- Uses your existing `gh auth` credentials
- Requires: `repo`, `security_events`, `read:org` scopes
- All data is stored locally

## 💡 Next Steps

1. **Set up daily automation** - Add to cron for regular monitoring
2. **Create report archives** - Save historical reports for trend analysis
3. **Integrate with notifications** - Send alerts to Slack/Teams for high priority items
4. **Track metrics over time** - Compare vulnerability counts week-over-week

---

**Need help?** Check `REPO_MONITOR_README.md` for more examples and automation ideas.
