# SRE Agent for CDP Management

An AI-powered SRE agent that helps manage Customer Data Platform (CDP) operations across multiple systems including Jira support tickets, GitHub repositories, and AWS infrastructure.

## Overview

This agent provides comprehensive monitoring and management capabilities for CDP operations:
- 🎫 **Jira Support Tickets**: Monitor CDPSUPPORT board for triage, track stale items, catch unacknowledged customer comments
- � **GitHub Repository Monitoring**: Track 120+ repos for recent activity, open PRs, and Dependabot security vulnerabilities
- ☁️ **AWS Cost Analysis**: Interrogate AWS infrastructure for cost optimization, resource utilization, and spending patterns
- 🤖 **Agent-Ready Output**: Structured output designed for AI agent consumption and automation

## Features

- **Multi-System Integration**: Unified view across Jira, GitHub, and AWS
- **Automated Daily Reports**: Generate structured triage and monitoring reports
- **Security-First**: Track Dependabot vulnerabilities across all repositories
- **Performance Optimized**: Parallel processing for fast GitHub scanning (120 repos in 19 seconds)
- **MCP Integration**: Uses Model Context Protocol for Atlassian, GitHub, and AWS interactions
- **Agent-Friendly**: JSON and human-readable output formats for automation
- **Actionable Insights**: Exit codes, alerts, and structured data to drive decisions

## Quick Start

### Prerequisites

- Python 3.8+ with virtual environment
- Access to Atlassian Jira (CDPSUPPORT project)
- GitHub CLI (`gh`) authenticated with appropriate permissions
- MCP (Model Context Protocol) configured for Atlassian and AWS
- AWS credentials configured for cost analysis

### Installation

```bash
# Clone or download this repository
cd sre_agent

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Edit `config.yaml` to match your setup:

```yaml
atlassian:
  cloud_id: "cirium.atlassian.net"
  
project:
  key: "CDPSUPPORT"
  board_id: "404"

github:
  organizations:
    - name: "LexisNexis-RBA"
      filter_topic: "data-dragons"
    - name: "LexisNexis-IAC"
      repos_file: "iac-repos.txt"

thresholds:
  staleness_days: 1
  recently_closed_days: 1
```

## Core Tools

### 1. Jira Support Board Monitoring

Monitor the CDPSUPPORT board for daily triage:

```bash
source venv/bin/activate
python jira_support_board_watcher.py
```

**Generates reports showing:**
- 🎉 Recently closed items (celebrate wins!)
- 📋 New items needing triage and sizing
- 🚧 In-progress work with assignees
- ⚠️ Stale items (not updated in >1 day)
- 💬 Unacknowledged customer comments

### 2. GitHub Repository Monitoring

Scan 120+ repositories for activity and security vulnerabilities:

```bash
source venv/bin/activate
python github_repo_watcher.py
```

**Features:**
- Tracks repos across LexisNexis-RBA (data-dragons topic) and LexisNexis-IAC organizations
- Identifies repos with recent commits (last 7 days)
- Detects open pull requests with clickable URLs
- Reports Dependabot security alerts (CRITICAL, HIGH, MEDIUM, LOW) with direct links
- Parallel processing: scans 120 repos in ~19 seconds

**Output formats:**
```bash
# Human-readable report (default)
source venv/bin/activate
python github_repo_watcher.py

# JSON output for agent consumption
source venv/bin/activate
python github_repo_watcher.py --json

# Quiet mode (no progress messages)
source venv/bin/activate
python github_repo_watcher.py --quiet
```

### 3. AWS Cost Analysis

Query AWS infrastructure using MCP integration:

```bash
# Ask the SRE agent questions like:
"What are our top 5 AWS services by cost this month?"
"Show me any EC2 instances that have been idle for more than 7 days"
"What's our S3 storage growth trend over the last 3 months?"
```

The agent uses MCP AWS tools to analyze costs, identify optimization opportunities, and track spending patterns.

## Report Structure

### Jira Triage Reports

The Jira board watcher generates reports including:

#### 🎉 Recently Closed Items
Items completed in the last 24 hours (configurable) - celebrate these wins!

#### 📋 New Items Needing Triage
Tickets that haven't been sized or assigned yet. Team should:
- Review and understand the request
- Assign an owner
- Estimate complexity/effort
- Set priority

#### 🚧 In Progress Items
All currently active work with:
- Current status
- Assignee
- Last update time
- Link to ticket

#### ⚠️ Stale Items
**CRITICAL**: Items in progress but not updated in >1 day. These likely indicate:
- Blockers that need escalation
- Work that needs reassignment
- Tickets needing customer follow-up

#### 💬 Unacknowledged Customer Comments
Tickets where customers have commented but haven't received a response. These need immediate attention to maintain customer satisfaction.

### GitHub Security Reports

The GitHub repo watcher provides:

#### 🚨 Security Alerts
- Dependabot vulnerabilities by severity (CRITICAL, HIGH, MEDIUM, LOW)
- Direct links to each alert for quick remediation
- Grouped by repository for easy triage

#### 📊 Development Activity
- Repositories with recent commits (last 7 days)
- Open pull requests with clickable URLs
- Activity summary across 120+ repositories

#### ⚡ Performance Metrics
- Scan completion time
- Total repositories monitored
- Organizations covered

## Agent Instructions

See [`AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md) for detailed instructions on using this agent to facilitate daily triage meetings and operational reviews.

The agent can help with:
- Daily standup facilitation for support tickets
- Security vulnerability triage and prioritization
- Development activity tracking across repositories
- AWS cost optimization and spending analysis
- Cross-system correlation (e.g., "Which repos have both security alerts AND recent customer issues?")

For detailed SRE chatmode instructions, see [`.github/chatmodes/SRE.chatmode.md`](.github/chatmodes/SRE.chatmode.md) which covers:
- Part 1: Jira CDPSUPPORT board monitoring
- Part 2: GitHub repository monitoring with security analysis
- Part 3: AWS cost and infrastructure analysis (coming soon)

## Documentation

- **[AGENT_INSTRUCTIONS.md](AGENT_INSTRUCTIONS.md)**: How to use the SRE agent for daily operations
- **[AGENT_OUTPUT_GUIDE.md](AGENT_OUTPUT_GUIDE.md)**: Understanding script outputs for automation
- **[REPO_MONITOR_README.md](REPO_MONITOR_README.md)**: Detailed GitHub monitoring documentation
- **[QUICK_START.md](QUICK_START.md)**: Fast reference for common commands
- **[.github/chatmodes/SRE.chatmode.md](.github/chatmodes/SRE.chatmode.md)**: Complete SRE chatmode guide

## Configuration Reference

### Thresholds

```yaml
thresholds:
  staleness_days: 1              # Days without update = stale
  recently_closed_days: 1        # Lookback for celebrations
  unacknowledged_comment_hours: 4 # Time before comment is flagged
```

## Example Report Outputs

### Jira Triage Report

```markdown
# 🎯 Daily Triage Report

**Generated:** 2025-10-14 09:30:00
**Board:** CDPSUPPORT (Board #404)

## 🎉 Recently Closed Items (Celebrate!)

**Count:** 2 items completed!

- **CDPSUPPORT-234**: API rate limiting issue
  - Resolved by: Alice
  - Resolved: 2025-10-13 16:45:00
  - Link: https://cirium.atlassian.net/browse/CDPSUPPORT-234

## ⚠️ Stale Items (Not Updated >1 Day)

**Count:** 1 item may be blocked!

- **🚨 CDPSUPPORT-456**: Integration endpoint failing
  - Assignee: Bob
  - Last Updated: 2025-10-12 10:00:00
  - Link: https://cirium.atlassian.net/browse/CDPSUPPORT-456
```

### GitHub Security Report

```markdown
# 🔍 GitHub Repository Scan

**Repositories Scanned:** 120
**Organizations:** LexisNexis-RBA (data-dragons), LexisNexis-IAC

## 🚨 Security Alerts

**6 repositories** with open Dependabot alerts:

### dsg-cirium-databricks-mlops-stacks
- **1 HIGH** severity alert
  - Vulnerability: JWT token validation bypass
  - URL: https://github.com/LexisNexis-RBA/dsg-cirium-databricks-mlops-stacks/security/dependabot/54

### dsg-cirium-cdp-tools
- **3 MEDIUM** severity alerts
  - Package: requests (CVE-2024-12345)
  - URL: https://github.com/LexisNexis-IAC/dsg-cirium-cdp-tools/security/dependabot/23

## 📊 Recent Activity

**18 repositories** with commits in the last 7 days
**12 repositories** with open pull requests
```

## Best Practices

### Daily Operations Flow
1. **Morning Standup**: Run Jira board watcher for support ticket triage
2. **Security Review**: Run GitHub repo watcher to check for new vulnerabilities
3. **Cost Review**: Query AWS spending patterns (weekly or as needed)
4. **Share Reports**: Distribute to team via Slack/Teams
5. **Take Action**: Update tickets, create PRs, investigate anomalies

### Automation Ideas
- **Scheduled Reports**: Cron jobs for daily GitHub/Jira scans
- **Slack Integration**: Post reports to channels automatically
- **CI/CD Checks**: Block deployments if critical vulnerabilities detected
- **Dashboards**: Aggregate data for trend analysis
- **Alerting**: Trigger PagerDuty for critical security issues

### Security-First Approach
- Prioritize HIGH/CRITICAL Dependabot alerts
- Track mean-time-to-remediation for vulnerabilities
- Correlate security alerts with customer-facing repos
- Regular dependency updates across all repositories

### Cost Optimization
- Review AWS spending weekly for anomalies
- Identify idle resources (EC2, RDS, EBS)
- Track S3 storage growth trends
- Right-size compute resources based on utilization

## Troubleshooting

### Common Issues

**Empty or incomplete reports**
- Verify `config.yaml` settings match your environment
- Check MCP connectivity: `gh auth status` for GitHub, verify AWS credentials
- Ensure virtual environment is activated: `source venv/bin/activate`

**GitHub scanning shows 0 vulnerabilities when you know there are alerts**
- This was a known bug, fixed in latest version
- Ensure you're using `github_repo_watcher.py` (not older versions)
- Check that `gh` CLI has `security_events` permission

**"Module not found" errors**
- Activate virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

**Slow GitHub scanning**
- Script uses parallel processing (10 workers) for optimal speed
- Expected: ~19 seconds for 120 repos
- If slower, check network connectivity and GitHub API rate limits

**Missing customer comments in Jira reports**
- Update `customer_domains` in `config.yaml`
- Verify comment detection logic matches your setup

## Architecture

```
sre_agent/
├── jira_support_board_watcher.py    # Jira CDPSUPPORT monitoring
├── github_repo_watcher.py            # GitHub security & activity scanner
├── config.yaml                       # Central configuration
├── requirements.txt                  # Python dependencies
├── docs/                             # Extended documentation
└── .github/
    └── chatmodes/
        └── SRE.chatmode.md          # Complete agent instructions
```

## Technology Stack

- **Python 3.8+**: Core scripting language
- **GitHub CLI (`gh`)**: GitHub API interactions with parallel execution
- **MCP (Model Context Protocol)**: Atlassian Jira and AWS integrations
- **ThreadPoolExecutor**: Concurrent API calls for performance
- **YAML**: Configuration management

## Contributing

This is an evolving SRE agent toolkit. Ideas for enhancement:

- **Multi-Cloud Support**: Add Azure, GCP cost analysis
- **Custom Metrics**: Team-specific KPIs and dashboards  
- **Alert Routing**: Integrate with PagerDuty, OpsGenie
- **Trend Analysis**: Historical tracking and anomaly detection
- **Slack Bot**: Interactive queries via chat interface
- **Policy Enforcement**: Automated governance checks

## License

MIT License - feel free to use and modify for your team.

## Support

For questions or issues:
- Check the [documentation](docs/)
- Review [SRE chatmode instructions](.github/chatmodes/SRE.chatmode.md)
- Verify configuration in `config.yaml`
- Test MCP connectivity for Atlassian, GitHub, AWS

---

**Built for SRE teams managing complex CDP operations across Jira, GitHub, and AWS.** 🚀
