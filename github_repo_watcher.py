#!/usr/bin/env python3
"""
GitHub Repository Monitor for SRE (using gh CLI with parallel processing)
Monitors data-dragons repositories for recent changes and Dependabot vulnerabilities

This version uses concurrent processing to speed up repository analysis.
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
import argparse
import concurrent.futures
from functools import partial


class GitHubRepoMonitor:
    """Monitor GitHub repositories for changes and vulnerabilities using gh CLI"""
    
    def __init__(self, max_workers: int = 10):
        """
        Initialize the monitor
        
        Args:
            max_workers: Maximum number of parallel workers (default: 10)
        """
        self.org = 'LexisNexis-RBA'
        self.max_workers = max_workers
        
        # Check if gh CLI is available
        if not self._check_gh_cli():
            raise RuntimeError(
                "gh CLI not found. Please install it from https://cli.github.com/ "
                "and authenticate with 'gh auth login'"
            )
    
    def _check_gh_cli(self) -> bool:
        """Check if gh CLI is installed and authenticated"""
        try:
            result = subprocess.run(
                ['gh', 'auth', 'status'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _run_gh_command(self, args: List[str]) -> Optional[str]:
        """Run a gh CLI command and return output"""
        try:
            result = subprocess.run(
                ['gh'] + args,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            if 'not found' in e.stderr or '404' in e.stderr:
                return None
            # Silently handle errors in parallel mode to avoid spam
            return None
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None
    
    def _run_gh_api(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Run gh api command and return JSON"""
        args = ['api', endpoint]
        
        if params:
            for key, value in params.items():
                args.extend(['-F', f'{key}={value}'])
        
        output = self._run_gh_command(args)
        if output:
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return None
        return None
    
    def get_data_dragons_repos(self) -> List[str]:
        """Get repositories with data-dragons topic using gh search"""
        repos = []
        
        # gh search repos doesn't support pagination, just get up to 1000 results
        output = self._run_gh_command([
            'search', 'repos',
            f'org:{self.org}', f'topic:data-dragons',
            '--json', 'fullName',
            '--limit', '1000'
        ])
        
        if not output:
            return repos
        
        try:
            data = json.loads(output)
            if not data:
                return repos
            
            for repo in data:
                repos.append(repo['fullName'])
        except (json.JSONDecodeError, KeyError):
            pass
        
        return repos
    
    def get_iac_repos_from_file(self) -> List[str]:
        """Fetch iac-repos.txt from dsg-cirium-cdp-tools using gh
        
        These repos are in the lexisnexis-iac organization, not LexisNexis-RBA
        """
        
        output = self._run_gh_command([
            'api',
            f'/repos/{self.org}/dsg-cirium-cdp-tools/contents/scripts/github-codeowners/iac-repos.txt',
            '--jq', '.content'
        ])
        
        if not output:
            return []
        
        # Decode base64 content
        import base64
        try:
            content = base64.b64decode(output.strip()).decode('utf-8')
        except Exception:
            return []
        
        # Parse repos from file
        # The file contains just repo names, which need to be prefixed with lexisnexis-iac org
        repos = []
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                # Handle different formats
                if line.startswith('http'):
                    # Extract repo from URL
                    parts = line.split('github.com/')
                    if len(parts) > 1:
                        repo = parts[1].strip('/').split()[0]
                        repos.append(repo)
                elif '/' in line:
                    # Direct repo format org/repo - use as-is
                    repos.append(line.split()[0])
                else:
                    # Just a repo name - prefix with lexisnexis-iac org
                    repos.append(f'lexisnexis-iac/{line}')
        
        return repos
    
    def get_all_repos(self) -> List[str]:
        """Get combined list of all repos to monitor"""
        repos = set()
        
        repos.update(self.get_data_dragons_repos())
        repos.update(self.get_iac_repos_from_file())
        
        return sorted(list(repos))
    
    def get_recent_commits(self, repo: str, days: int = 7) -> List[Dict]:
        """Get recent commits for a repository"""
        since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
        
        output = self._run_gh_command([
            'api',
            f'/repos/{repo}/commits',
            '-F', f'since={since}',
            '-F', 'per_page=100',
            '--jq', '.[] | {sha: .sha[0:7], message: .commit.message, author: .commit.author.name, date: .commit.author.date}'
        ])
        
        if not output:
            return []
        
        commits = []
        for line in output.strip().split('\n'):
            if line:
                try:
                    commit = json.loads(line)
                    # Get first line of commit message
                    commit['message'] = commit['message'].split('\n')[0]
                    commits.append(commit)
                except json.JSONDecodeError:
                    continue
        
        return commits
    
    def get_recent_prs(self, repo: str, days: int = 7) -> List[Dict]:
        """Get recent pull requests for a repository"""
        since = datetime.now() - timedelta(days=days)
        
        output = self._run_gh_command([
            'pr', 'list',
            '--repo', repo,
            '--state', 'all',
            '--limit', '100',
            '--json', 'number,title,state,author,updatedAt,url'
        ])
        
        if not output:
            return []
        
        try:
            all_prs = json.loads(output)
            prs = []
            
            for pr in all_prs:
                try:
                    updated_at = datetime.fromisoformat(pr['updatedAt'].replace('Z', '+00:00'))
                    if updated_at < since.astimezone(updated_at.tzinfo):
                        continue
                    
                    prs.append({
                        'number': pr['number'],
                        'title': pr['title'],
                        'state': pr['state'],
                        'author': pr['author']['login'] if pr.get('author') else 'unknown',
                        'updated_at': pr['updatedAt'],
                        'url': pr['url']
                    })
                except (KeyError, ValueError):
                    continue
            
            return prs
        except json.JSONDecodeError:
            return []
    
    def get_dependabot_alerts(self, repo: str) -> List[Dict]:
        """Get Dependabot security alerts for a repository"""
        # Use gh api to get dependabot alerts
        # Note: Query parameters must be in the URL for GET requests
        output = self._run_gh_command([
            'api',
            f'/repos/{repo}/dependabot/alerts?state=open&per_page=100',
            '--jq', '.[] | {number, severity: .security_advisory.severity, package: .security_vulnerability.package.name, summary: .security_advisory.summary, cve_id: .security_advisory.cve_id, url: .html_url, created_at}'
        ])
        
        if not output:
            return []
        
        alerts = []
        for line in output.strip().split('\n'):
            if line:
                try:
                    alert = json.loads(line)
                    if not alert.get('cve_id'):
                        alert['cve_id'] = 'N/A'
                    alerts.append(alert)
                except json.JSONDecodeError:
                    continue
        
        return alerts
    
    def analyze_repo(self, repo: str, days: int = 7, verbose: bool = True) -> Dict:
        """Analyze a single repository for changes and vulnerabilities"""
        if verbose:
            print(f"  Analyzing {repo}...", end='', flush=True)
        
        commits = self.get_recent_commits(repo, days)
        prs = self.get_recent_prs(repo, days)
        alerts = self.get_dependabot_alerts(repo)
        
        if verbose:
            print(f" ✓ ({len(commits)} commits, {len(prs)} PRs, {len(alerts)} alerts)")
        
        return {
            'repo': repo,
            'recent_commits': commits,
            'recent_prs': prs,
            'dependabot_alerts': alerts,
            'has_activity': len(commits) > 0 or len(prs) > 0,
            'has_vulnerabilities': len(alerts) > 0
        }
    
    def analyze_repos_parallel(self, repos: List[str], days: int = 7, quiet: bool = False) -> List[Dict]:
        """Analyze multiple repositories in parallel"""
        if not quiet:
            print(f"\nAnalyzing {len(repos)} repositories (using {self.max_workers} workers)...", file=sys.stderr)
        
        results = []
        completed = 0
        total = len(repos)
        
        # Create a partial function with fixed days parameter
        analyze_func = partial(self.analyze_repo, days=days, verbose=False)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_repo = {executor.submit(analyze_func, repo): repo for repo in repos}
            
            # Process completed tasks
            for future in concurrent.futures.as_completed(future_to_repo):
                repo = future_to_repo[future]
                completed += 1
                
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Progress indicator
                    if not quiet and (completed % 10 == 0 or completed == total):
                        pct = (completed / total) * 100
                        print(f"  Progress: {completed}/{total} ({pct:.0f}%) - Latest: {repo}", file=sys.stderr)
                
                except Exception as e:
                    if not quiet:
                        print(f"  Error analyzing {repo}: {e}", file=sys.stderr)
                    # Add a failed result
                    results.append({
                        'repo': repo,
                        'recent_commits': [],
                        'recent_prs': [],
                        'dependabot_alerts': [],
                        'has_activity': False,
                        'has_vulnerabilities': False,
                        'error': str(e)
                    })
        
        # Sort results by repo name for consistent output
        results.sort(key=lambda x: x['repo'])
        return results
    
    def generate_report(self, results: List[Dict], days: int = 7) -> str:
        """Generate a formatted report"""
        lines = []
        lines.append("=" * 80)
        lines.append(f"GitHub Repository Monitoring Report (Parallel Mode)")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Monitoring Period: Last {days} days")
        lines.append("=" * 80)
        lines.append("")
        
        # Summary statistics
        total_repos = len(results)
        active_repos = sum(1 for r in results if r['has_activity'])
        vulnerable_repos = sum(1 for r in results if r['has_vulnerabilities'])
        total_alerts = sum(len(r['dependabot_alerts']) for r in results)
        errors = sum(1 for r in results if 'error' in r)
        
        lines.append("📊 SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Total Repositories: {total_repos}")
        lines.append(f"Repos with Recent Activity: {active_repos}")
        lines.append(f"Repos with Vulnerabilities: {vulnerable_repos}")
        lines.append(f"Total Open Dependabot Alerts: {total_alerts}")
        if errors > 0:
            lines.append(f"Errors encountered: {errors}")
        lines.append("")
        
        # Severity breakdown
        severity_counts = defaultdict(int)
        for result in results:
            for alert in result['dependabot_alerts']:
                severity_counts[alert['severity']] += 1
        
        if severity_counts:
            lines.append("🚨 VULNERABILITY SEVERITY BREAKDOWN")
            lines.append("-" * 80)
            for severity in ['critical', 'high', 'medium', 'low']:
                if severity in severity_counts:
                    lines.append(f"  {severity.upper()}: {severity_counts[severity]}")
            lines.append("")
        
        # Repos with both activity and vulnerabilities (HIGH PRIORITY)
        high_priority = [r for r in results if r['has_activity'] and r['has_vulnerabilities']]
        if high_priority:
            lines.append("🔥 HIGH PRIORITY: Active Repos with Vulnerabilities")
            lines.append("-" * 80)
            for result in sorted(high_priority, key=lambda x: len(x['dependabot_alerts']), reverse=True):
                lines.append(f"\n📦 {result['repo']}")
                lines.append(f"   Activity: {len(result['recent_commits'])} commits, {len(result['recent_prs'])} PRs")
                lines.append(f"   Vulnerabilities: {len(result['dependabot_alerts'])} open alerts")
                
                # Show recent PRs with links
                if result['recent_prs']:
                    lines.append(f"   📝 Recent PRs:")
                    for pr in result['recent_prs'][:3]:  # Show top 3
                        state_emoji = "✅" if pr['state'] == 'MERGED' else "🔵" if pr['state'] == 'OPEN' else "❌"
                        lines.append(f"      {state_emoji} #{pr['number']}: {pr['title'][:60]}...")
                        lines.append(f"         {pr['url']}")
                
                # Show critical/high alerts
                critical_alerts = [a for a in result['dependabot_alerts'] 
                                 if a['severity'] in ['critical', 'high']]
                if critical_alerts:
                    lines.append(f"   ⚠️  Critical/High Severity Alerts:")
                    for alert in critical_alerts[:3]:  # Show top 3
                        lines.append(f"      - [{alert['severity'].upper()}] {alert['package']}: {alert['summary']}")
                        lines.append(f"        {alert['url']}")
                
                # Show all other alerts (medium/low)
                other_alerts = [a for a in result['dependabot_alerts'] 
                               if a['severity'] not in ['critical', 'high']]
                if other_alerts:
                    lines.append(f"   📋 Other Alerts ({len(other_alerts)}):")
                    for alert in other_alerts[:3]:  # Show top 3
                        lines.append(f"      - [{alert['severity'].upper()}] {alert['package']}: {alert['summary']}")
                        lines.append(f"        {alert['url']}")
            lines.append("")
        
        # Repos with vulnerabilities only
        vulnerable_only = [r for r in results if r['has_vulnerabilities'] and not r['has_activity']]
        if vulnerable_only:
            lines.append("⚠️  REPOS WITH VULNERABILITIES (No Recent Activity)")
            lines.append("-" * 80)
            for result in sorted(vulnerable_only, key=lambda x: len(x['dependabot_alerts']), reverse=True):
                lines.append(f"\n📦 {result['repo']}")
                lines.append(f"   Vulnerabilities: {len(result['dependabot_alerts'])} open alerts")
                
                # Group by severity
                by_severity = defaultdict(int)
                for alert in result['dependabot_alerts']:
                    by_severity[alert['severity']] += 1
                severity_str = ', '.join([f"{sev}: {count}" for sev, count in sorted(by_severity.items())])
                lines.append(f"   Severity breakdown: {severity_str}")
                
                # Show top critical/high alerts
                critical_alerts = [a for a in result['dependabot_alerts'] 
                                 if a['severity'] in ['critical', 'high']]
                if critical_alerts:
                    lines.append(f"   Top alerts:")
                    for alert in critical_alerts[:2]:
                        lines.append(f"      - [{alert['severity'].upper()}] {alert['package']}: {alert['summary']}")
            lines.append("")
        
        # Active repos without vulnerabilities
        active_clean = [r for r in results if r['has_activity'] and not r['has_vulnerabilities']]
        if active_clean:
            lines.append("✅ ACTIVE REPOS (No Vulnerabilities)")
            lines.append("-" * 80)
            for result in active_clean:
                lines.append(f"\n📦 {result['repo']}: {len(result['recent_commits'])} commits, {len(result['recent_prs'])} PRs")
                # Show PR links for active repos
                if result['recent_prs']:
                    for pr in result['recent_prs'][:2]:  # Show top 2
                        state_emoji = "✅" if pr['state'] == 'MERGED' else "🔵" if pr['state'] == 'OPEN' else "❌"
                        lines.append(f"   {state_emoji} #{pr['number']}: {pr['title'][:60]}... - {pr['url']}")
            lines.append("")
        
        # Quiet repos (no activity, no vulnerabilities)
        quiet_repos = [r for r in results if not r['has_activity'] and not r['has_vulnerabilities'] and 'error' not in r]
        if quiet_repos:
            lines.append(f"😴 QUIET REPOS (No Activity, No Vulnerabilities): {len(quiet_repos)} repos")
            lines.append("-" * 80)
            for result in quiet_repos[:10]:  # Show first 10
                lines.append(f"  {result['repo']}")
            if len(quiet_repos) > 10:
                lines.append(f"  ... and {len(quiet_repos) - 10} more")
            lines.append("")
        
        lines.append("=" * 80)
        
        return '\n'.join(lines)
    
    def run(self, days: int = 7, output_file: Optional[str] = None, 
            filter_repos: Optional[List[str]] = None, parallel: bool = True,
            json_output: bool = False, quiet: bool = False) -> None:
        """Run the monitoring process"""
        if not quiet:
            print(f"Starting GitHub Repository Monitor (using gh CLI - {'Parallel' if parallel else 'Sequential'} Mode)...", file=sys.stderr)
            print(file=sys.stderr)
        
        # Get all repos
        repos = self.get_all_repos()
        
        # Filter repos if specified
        if filter_repos:
            repos = [r for r in repos if any(f in r for f in filter_repos)]
        
        if not quiet:
            print(f"\nFound {len(repos)} repositories to monitor", file=sys.stderr)
        
        # Analyze repos
        if parallel:
            results = self.analyze_repos_parallel(repos, days, quiet=quiet)
        else:
            # Sequential fallback
            if not quiet:
                print(file=sys.stderr)
            results = []
            for repo in repos:
                result = self.analyze_repo(repo, days, verbose=not quiet)
                results.append(result)
        
        if not quiet:
            print(file=sys.stderr)
        
        # Output JSON to stdout if requested (agent-friendly)
        if json_output:
            print(json.dumps(results, indent=2))
            return
        
        # Generate human-readable report
        report = self.generate_report(results, days)
        
        # Save to file if requested, otherwise print to stdout
        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            if not quiet:
                print(f"📄 Report saved to: {output_file}", file=sys.stderr)
            
            # Also save JSON data alongside
            json_file = output_file.replace('.txt', '.json')
            with open(json_file, 'w') as f:
                json.dump(results, f, indent=2)
            if not quiet:
                print(f"📄 JSON data saved to: {json_file}", file=sys.stderr)
        else:
            # Print report to stdout
            print(report)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Monitor GitHub repositories for changes and vulnerabilities (using gh CLI)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor repos and output report to STDOUT (default)
  python github_repo_watcher.py
  
  # Output JSON to STDOUT (agent-friendly)
  python github_repo_watcher.py --json
  
  # Quiet mode - only results, no progress messages
  python github_repo_watcher.py --json --quiet
  
  # Monitor with 20 parallel workers for faster execution
  python github_repo_watcher.py --workers 20
  
  # Save report to file instead of STDOUT
  python github_repo_watcher.py --output report.txt
  
  # Sequential mode (slower but more conservative)
  python github_repo_watcher.py --no-parallel
  
  # Monitor repos for last 14 days
  python github_repo_watcher.py --days 14
  
  # Filter specific repos
  python github_repo_watcher.py --filter data-dragons --filter cdp-tools

Requirements:
  - GitHub CLI (gh) must be installed and authenticated
  - Run 'gh auth login' if not already authenticated
  - Requires permissions to read repos and security alerts

Performance:
  - Parallel mode (default): ~15-30 seconds for 120 repos
  - Sequential mode: ~2 minutes for 120 repos
  - Workers: Default 10, increase for faster processing (but watch API limits)
        """
    )
    
    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to look back for recent activity (default: 7)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output file for the report (default: stdout only)'
    )
    
    parser.add_argument(
        '--filter',
        type=str,
        action='append',
        dest='filter_repos',
        help='Filter repos by name substring (can be used multiple times)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=10,
        help='Number of parallel workers (default: 10, max recommended: 20)'
    )
    
    parser.add_argument(
        '--no-parallel',
        action='store_true',
        help='Disable parallel processing (slower but more conservative)'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON to STDOUT instead of human-readable report (agent-friendly)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Quiet mode - suppress progress messages (only output results)'
    )
    
    args = parser.parse_args()
    
    try:
        monitor = GitHubRepoMonitor(max_workers=args.workers)
        monitor.run(
            days=args.days, 
            output_file=args.output, 
            filter_repos=args.filter_repos,
            parallel=not args.no_parallel,
            json_output=args.json,
            quiet=args.quiet
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nMonitoring interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
