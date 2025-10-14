#!/usr/bin/env python3
"""
Jira Board Watcher for SRE Team

This script monitors the CDPSUPPORT Jira board for daily triage meetings.
It identifies:
- New cards that need triage and sizing
- In-progress items and their current state
- Stale items (not updated in >1 day)
- Unacknowledged customer comments
- Recently closed items for celebration

Uses Jira REST API to interact with Atlassian Jira.
"""

import json
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
import yaml


@dataclass
class TriageReport:
    """Data structure for triage meeting report"""
    triage_items: List[Dict[str, Any]]
    todo_items: List[Dict[str, Any]]
    in_progress_items: List[Dict[str, Any]]
    waiting_for_customer_items: List[Dict[str, Any]]
    stale_items: List[Dict[str, Any]]
    unacknowledged_comments: List[Dict[str, Any]]
    recently_closed: List[Dict[str, Any]]
    items_by_comment_activity: List[Dict[str, Any]]


class JiraBoardWatcher:
    """Watches a Jira board and generates triage reports"""
    
    def __init__(self, jira_url: str, email: str, api_token: str, project_key: str, board_id: str = "404", team_name: Optional[str] = None, team_members: Optional[List[str]] = None):
        """
        Initialize the board watcher
        
        Args:
            jira_url: Base URL for Jira instance (e.g., 'https://cirium.atlassian.net')
            email: User email for authentication
            api_token: API token for authentication
            project_key: Jira project key (e.g., 'CDPSUPPORT')
            board_id: Jira board ID (default: '404')
            team_name: Team name for identifying team members (e.g., 'Data Dragons')
            team_members: Optional list of team member emails for manual configuration
        """
        self.jira_url = jira_url.rstrip('/')
        self.project_key = project_key
        self.board_id = board_id
        self.team_name = team_name
        self.team_id = None
        self.manual_team_members = team_members or []
        self.auth = HTTPBasicAuth(email, api_token)
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.staleness_threshold = timedelta(days=1)
        self.recently_closed_window = timedelta(days=1)
        self._team_members = None  # Cache for team members
        self._team_member_account_ids = None  # Cache for account IDs
        
        # Look up team ID from team name if provided
        if self.team_name:
            self.team_id = self._lookup_team_id(self.team_name)
    
    def _lookup_team_id(self, team_name: str) -> Optional[str]:
        """
        Look up team ID from team name using project roles
        This uses a special indicator to tell _get_team_members to use project role lookup
        
        Args:
            team_name: Name of the team/project (e.g., 'Data Dragons' or project key)
            
        Returns:
            "project:<key>" to indicate project-based lookup should be used
        """
        # For project-based team member lookup, we'll use the project key from config
        # Return a special indicator that tells _get_team_members to use project roles
        print(f"[INFO] Using project role-based team member lookup for project: {self.project_key}", file=sys.stderr)
        return f"project:{self.project_key}"
    
    def _get_org_id(self) -> Optional[str]:
        """
        Get the Atlassian organization ID from the cloud resources
        
        Note: This endpoint requires OAuth authentication, which may not be available
        with API token authentication. If it fails, team lookup will fallback to group lookup.
        
        Returns:
            Organization ID if found, None otherwise
        """
        url = "https://api.atlassian.com/oauth/token/accessible-resources"
        
        try:
            response = requests.get(url, auth=self.auth, headers=self.headers)
            
            # If we get 401, the API token doesn't work for this endpoint
            # This is expected - Teams API requires OAuth, not API token
            if response.status_code == 401:
                print(f"[INFO] Teams API requires OAuth (API token not supported), will use group-based lookup", file=sys.stderr)
                return None
            
            response.raise_for_status()
            
            resources = response.json()
            if resources:
                # Get the first resource's ID (usually the cloud ID)
                cloud_id = resources[0].get('id')
                print(f"[API] Found cloud/org ID: {cloud_id}", file=sys.stderr)
                return cloud_id
            
        except requests.exceptions.RequestException as e:
            print(f"[INFO] Could not access Teams API (OAuth required): {e}", file=sys.stderr)
        
        return None
    
    def _get_team_members(self) -> List[str]:
        """
        Get list of team member account IDs from the team
        Uses project roles to determine team membership
        
        Returns:
            List of account IDs for team members
        """
        if self._team_members is not None:
            return self._team_members
        
        if not self.team_id:
            print("[WARN] No team ID configured, cannot identify team members", file=sys.stderr)
            self._team_members = []
            return self._team_members
        
        # Check if this is a project-based lookup
        if self.team_id.startswith('project:'):
            project_key = self.team_id[8:]  # Remove 'project:' prefix
            return self._get_project_members(project_key)
        
        # Check if this is a group-based lookup (fallback)
        if self.team_id.startswith('group:'):
            group_name = self.team_id[6:]  # Remove 'group:' prefix
            return self._get_group_members(group_name)
        
        # Use the Atlassian Teams Public API (requires OAuth - likely won't work)
        org_id = self._get_org_id()
        if not org_id:
            print(f"[WARN] Cannot fetch team members without organization ID", file=sys.stderr)
            self._team_members = []
            return self._team_members
        
        base_url = "https://api.atlassian.com"
        url = f"{base_url}/public/teams/v1/org/{org_id}/teams/{self.team_id}/members"
        
        all_members = []
        cursor = None
        
        try:
            print(f"[API] Fetching team members for team ID: {self.team_id}", file=sys.stderr)
            
            while True:
                # POST request with pagination
                payload = {'size': 100}
                if cursor:
                    payload['cursor'] = cursor
                
                response = requests.post(url, auth=self.auth, headers=self.headers, json=payload)
                response.raise_for_status()
                
                data = response.json()
                members = data.get('entities', [])
                
                for member in members:
                    account_id = member.get('accountId')
                    if account_id:
                        all_members.append(account_id)
                
                # Check for next page
                cursor = data.get('cursor')
                if not cursor:
                    break
            
            self._team_members = all_members
            print(f"[API] Found {len(self._team_members)} team members", file=sys.stderr)
            return self._team_members
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to get team members: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ERROR] Response body: {e.response.text[:500]}", file=sys.stderr)
            self._team_members = []
            return self._team_members
    
    def _get_project_members(self, project_key: str) -> List[str]:
        """
        Get list of account IDs for members of a Jira project using project roles
        Only includes users with 'Member' or 'Administrator' roles to identify core team
        
        This is a three-phase approach:
        1. Get all role URLs for the project
        2. Fetch members from 'Member' and 'Administrator' roles only
        3. Filter out bots/apps (no email address), keeping only real users
        
        Args:
            project_key: The Jira project key (e.g., 'CDPSUPPORT')
            
        Returns:
            List of account IDs for project members (real users only, no bots/apps)
        """
        # Phase 1: Get all project roles
        url = f"{self.jira_url}/rest/api/3/project/{project_key}/role"
        all_account_ids = set()  # Use set to avoid duplicates
        
        # Define which roles to include (core team roles)
        team_roles = ['Member', 'Administrator']
        
        try:
            print(f"[API] Fetching project roles for: {project_key}", file=sys.stderr)
            response = requests.get(url, auth=self.auth, headers=self.headers)
            response.raise_for_status()
            
            roles = response.json()
            print(f"[API] Found {len(roles)} roles in project", file=sys.stderr)
            
            # Phase 2: Fetch members only from team roles (Member, Administrator)
            for role_name, role_url in roles.items():
                # Skip roles that aren't part of the core team
                if role_name not in team_roles:
                    continue
                
                try:
                    print(f"[API] Fetching members for role: {role_name}", file=sys.stderr)
                    role_response = requests.get(role_url, auth=self.auth, headers=self.headers)
                    role_response.raise_for_status()
                    
                    role_data = role_response.json()
                    actors = role_data.get('actors', [])
                    
                    for actor in actors:
                        # Only include users directly assigned to roles
                        # Exclude group-based assignments as they may include other teams
                        actor_type = actor.get('type')
                        if actor_type == 'atlassian-user-role-actor':
                            account_id = actor.get('actorUser', {}).get('accountId')
                            if account_id:
                                all_account_ids.add(account_id)
                        # Skip atlassian-group-role-actor to exclude users from other teams
                    
                except requests.exceptions.RequestException as e:
                    print(f"[WARN] Failed to fetch role {role_name}: {e}", file=sys.stderr)
            
            print(f"[API] Found {len(all_account_ids)} total accounts, filtering out bots/apps...", file=sys.stderr)
            
            # Phase 3: Filter out bots/apps, keep only real users
            # Real users have email addresses, bots/apps don't
            real_users = []
            app_count = 0
            
            for account_id in all_account_ids:
                user_url = f"{self.jira_url}/rest/api/3/user?accountId={account_id}"
                try:
                    user_response = requests.get(user_url, auth=self.auth, headers=self.headers)
                    if user_response.status_code == 200:
                        user = user_response.json()
                        email = user.get('emailAddress')
                        
                        # Only include users with email addresses (real people)
                        # Bots/apps don't have email addresses
                        if email:
                            real_users.append(account_id)
                        else:
                            app_count += 1
                except requests.exceptions.RequestException:
                    # If we can't fetch user details, exclude them to be safe
                    app_count += 1
            
            self._team_members = real_users
            print(f"[API] Found {len(self._team_members)} real users (filtered out {app_count} bots/apps)", file=sys.stderr)
            return self._team_members
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to get project roles: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ERROR] Response body: {e.response.text[:500]}", file=sys.stderr)
            self._team_members = []
            return self._team_members
    
    def _get_group_members(self, group_name: str) -> List[str]:
        """
        Get list of account IDs for members of a Jira group
        
        Args:
            group_name: Name of the group
            
        Returns:
            List of account IDs for group members
        """
        url = f"{self.jira_url}/rest/api/3/group/member"
        params = {'groupname': group_name, 'maxResults': 200}
        all_members = []
        
        try:
            print(f"[API] Fetching members for group: {group_name}", file=sys.stderr)
            
            while True:
                response = requests.get(url, auth=self.auth, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                members = data.get('values', [])
                
                for member in members:
                    account_id = member.get('accountId')
                    if account_id:
                        all_members.append(account_id)
                
                # Check for pagination
                if not data.get('isLast', True):
                    params['startAt'] = params.get('startAt', 0) + len(members)
                else:
                    break
            
            self._team_members = all_members
            print(f"[API] Found {len(self._team_members)} group members", file=sys.stderr)
            return self._team_members
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to get group members: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ERROR] Response body: {e.response.text[:500]}", file=sys.stderr)
            self._team_members = []
            return self._team_members
    
    def _is_team_member(self, account_id: str) -> bool:
        """
        Check if an account ID belongs to a team member
        
        Args:
            account_id: The Jira account ID to check
            
        Returns:
            True if the account is a team member, False otherwise
        """
        team_members = self._get_team_members()
        return account_id in team_members
    
    def _search_jira(self, jql: str, fields: Optional[List[str]] = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Execute a JQL search against Jira API
        
        Args:
            jql: JQL query string
            fields: List of fields to return (None = all fields)
            max_results: Maximum number of results
            
        Returns:
            List of issues matching the query
        """
        url = f"{self.jira_url}/rest/api/3/search/jql"
        
        params = {
            'jql': jql,
            'maxResults': max_results,
            'fields': ','.join(fields) if fields else '*all'
        }
        
        try:
            print(f"[API] Searching Jira with JQL: {jql}", file=sys.stderr)
            response = requests.get(url, auth=self.auth, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            issues = data.get('issues', [])
            print(f"[API] Found {len(issues)} issues", file=sys.stderr)
            return issues
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to search Jira: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ERROR] Response body: {e.response.text[:500]}", file=sys.stderr)
            return []
    
    def get_triage_items(self) -> List[Dict[str, Any]]:
        """
        Get items in Triage status that need triage
        
        JQL: project = CDPSUPPORT AND status = "Triage" ORDER BY created DESC
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status = "Triage" '
            f'ORDER BY created DESC'
        )
        
        return self._search_jira(jql)
    
    def get_todo_items(self) -> List[Dict[str, Any]]:
        """
        Get items in To Do status (ready to be picked up)
        
        JQL: project = CDPSUPPORT AND status = "To Do" ORDER BY created DESC
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status = "To Do" '
            f'ORDER BY created DESC'
        )
        
        return self._search_jira(jql)
    
    def get_in_progress_items(self) -> List[Dict[str, Any]]:
        """
        Get all items currently in progress
        
        JQL: project = CDPSUPPORT AND status = "In Progress" ORDER BY updated DESC
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status = "In Progress" '
            f'ORDER BY updated DESC'
        )
        
        return self._search_jira(jql)
    
    def get_waiting_for_customer_items(self) -> List[Dict[str, Any]]:
        """
        Get items waiting for customer response
        
        JQL: project = CDPSUPPORT AND status = "Waiting for customer" ORDER BY updated ASC
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status = "Waiting for customer" '
            f'ORDER BY updated ASC'
        )
        
        return self._search_jira(jql)
    
    def get_stale_items(self) -> List[Dict[str, Any]]:
        """
        Get in-progress items not updated in >1 day
        
        JQL: project = CDPSUPPORT AND status = "In Progress" AND 
             updated < -1d ORDER BY updated ASC
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status = "In Progress" AND '
            f'updated < -1d '
            f'ORDER BY updated ASC'
        )
        
        return self._search_jira(jql)
    
    def get_recently_closed_items(self) -> List[Dict[str, Any]]:
        """
        Get items closed in the last day (for celebration!)
        
        JQL: project = CDPSUPPORT AND status = Done AND 
             resolved >= -1d ORDER BY resolved DESC
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status in (Done, Closed, Resolved) AND '
            f'resolved >= -1d '
            f'ORDER BY resolved DESC'
        )
        
        return self._search_jira(jql)
    
    def get_items_by_comment_activity(self) -> List[Dict[str, Any]]:
        """
        Get all non-done items and analyze their comment activity.
        Returns items sorted by least recent comment activity first.
        Excludes Triage items since they are new and haven't been reviewed yet.
        
        JQL: project = CDPSUPPORT AND status not in (Done, Cancelled, Resolved, Closed, Triage)
        """
        jql = (
            f'project = {self.project_key} AND '
            f'status not in (Done, Cancelled, Resolved, Closed, Triage) '
            f'ORDER BY updated ASC'
        )
        
        # Get issues with comment field
        fields = ['summary', 'status', 'assignee', 'created', 'updated', 'comment']
        issues = self._search_jira(jql, fields=fields, max_results=200)
        
        items_with_analysis = []
        
        for issue in issues:
            key = issue.get('key', 'N/A')
            summary = issue.get('fields', {}).get('summary', 'No summary')
            status = issue.get('fields', {}).get('status', {}).get('name', 'Unknown')
            assignee = issue.get('fields', {}).get('assignee', {})
            assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
            created = issue.get('fields', {}).get('created', '')
            updated = issue.get('fields', {}).get('updated', '')
            
            comments = issue.get('fields', {}).get('comment', {}).get('comments', [])
            
            last_comment_date = None
            last_comment_author = None
            last_comment_author_account_id = None
            last_comment_by_team = None
            comment_count = len(comments)
            days_since_activity = None
            
            if comments:
                # Get the most recent comment
                last_comment = comments[-1]
                last_comment_date = last_comment.get('created', '')
                last_comment_author = last_comment.get('author', {}).get('displayName', 'Unknown')
                last_comment_author_account_id = last_comment.get('author', {}).get('accountId', '')
                
                # Check if last comment was by a team member
                if last_comment_author_account_id:
                    last_comment_by_team = self._is_team_member(last_comment_author_account_id)
                
                # Calculate days since last comment
                if last_comment_date:
                    last_comment_dt = datetime.fromisoformat(last_comment_date.replace('Z', '+00:00'))
                    days_since_activity = (datetime.now(last_comment_dt.tzinfo) - last_comment_dt).days
            else:
                # No comments - calculate days since created
                if created:
                    created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    days_since_activity = (datetime.now(created_dt.tzinfo) - created_dt).days
            
            items_with_analysis.append({
                'key': key,
                'summary': summary,
                'status': status,
                'assignee': assignee_name,
                'created': created,
                'updated': updated,
                'comment_count': comment_count,
                'last_comment_date': last_comment_date,
                'last_comment_author': last_comment_author,
                'last_comment_by_team': last_comment_by_team,
                'days_since_activity': days_since_activity
            })
        
        # Sort by last comment date (oldest first), with no-comment items first
        def sort_key(item):
            if item['last_comment_date'] is None:
                return ('0', '')  # No comments go first
            return ('1', item['last_comment_date'])
        
        items_with_analysis.sort(key=sort_key)
        
        return items_with_analysis
    
    def check_for_customer_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Check if an issue has unacknowledged customer comments
        
        Args:
            issue_key: The Jira issue key (e.g., 'CDPSUPPORT-123')
            
        Returns:
            List of unacknowledged customer comments
        """
        url = f"{self.jira_url}/rest/api/3/issue/{issue_key}"
        params = {'expand': 'comments'}
        
        try:
            print(f"[API] Checking issue {issue_key} for customer comments", file=sys.stderr)
            response = requests.get(url, auth=self.auth, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            comments = data.get('fields', {}).get('comment', {}).get('comments', [])
            
            # Simple heuristic: look for comments from external users (not @cirium.com)
            # that don't have a reply from internal team
            unacknowledged = []
            for comment in comments:
                author_email = comment.get('author', {}).get('emailAddress', '')
                if author_email and not author_email.endswith('@cirium.com'):
                    # Check if there's a later comment from internal team
                    comment_created = datetime.fromisoformat(comment.get('created', '').replace('Z', '+00:00'))
                    has_reply = False
                    
                    for reply in comments:
                        reply_author_email = reply.get('author', {}).get('emailAddress', '')
                        reply_created = datetime.fromisoformat(reply.get('created', '').replace('Z', '+00:00'))
                        
                        if (reply_author_email.endswith('@cirium.com') and 
                            reply_created > comment_created):
                            has_reply = True
                            break
                    
                    if not has_reply:
                        unacknowledged.append(comment)
            
            return unacknowledged
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Failed to get issue {issue_key}: {e}", file=sys.stderr)
            return []
    
    def generate_triage_report(self) -> TriageReport:
        """
        Generate a comprehensive triage report for the daily standup
        
        Returns:
            TriageReport with all relevant information
        """
        print("[INFO] Generating triage report...", file=sys.stderr)
        
        triage_items = self.get_triage_items()
        todo_items = self.get_todo_items()
        in_progress_items = self.get_in_progress_items()
        waiting_for_customer_items = self.get_waiting_for_customer_items()
        stale_items = self.get_stale_items()
        recently_closed = self.get_recently_closed_items()
        items_by_comment_activity = self.get_items_by_comment_activity()
        
        # Check each in-progress item for unacknowledged customer comments
        unacknowledged = []
        for item in in_progress_items:
            comments = self.check_for_customer_comments(item.get('key', ''))
            if comments:
                unacknowledged.append({
                    'issue': item,
                    'comments': comments
                })
        
        return TriageReport(
            triage_items=triage_items,
            todo_items=todo_items,
            in_progress_items=in_progress_items,
            waiting_for_customer_items=waiting_for_customer_items,
            stale_items=stale_items,
            unacknowledged_comments=unacknowledged,
            recently_closed=recently_closed,
            items_by_comment_activity=items_by_comment_activity
        )
    
    def format_report(self, report: TriageReport) -> str:
        """
        Format the triage report as markdown for easy reading
        
        Args:
            report: The TriageReport to format
            
        Returns:
            Markdown-formatted report string
        """
        output = []
        output.append("# 🎯 Daily Triage Report")
        output.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        output.append(f"\n**Board:** {self.project_key} (Board #{self.board_id})\n")
        
        # Items in Triage status
        output.append("## � Triage Status (Need Review & Sizing)")
        if report.triage_items:
            output.append(f"\n**Count:** {len(report.triage_items)} items need triage\n")
            for item in report.triage_items:
                key = item.get('key', 'N/A')
                summary = item.get('fields', {}).get('summary', 'No summary')
                created = item.get('fields', {}).get('created', 'N/A')
                assignee = item.get('fields', {}).get('assignee', {})
                assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
                output.append(f"- **{key}**: {summary}")
                output.append(f"  - Created: {created}")
                output.append(f"  - Assignee: {assignee_name}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n✅ No items in triage!\n")
        
        # Items in To Do status
        output.append("\n## 📋 To Do Status (Ready to Work)")
        if report.todo_items:
            output.append(f"\n**Count:** {len(report.todo_items)} items ready to be picked up\n")
            for item in report.todo_items:
                key = item.get('key', 'N/A')
                summary = item.get('fields', {}).get('summary', 'No summary')
                created = item.get('fields', {}).get('created', 'N/A')
                assignee = item.get('fields', {}).get('assignee', {})
                assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
                output.append(f"- **{key}**: {summary}")
                output.append(f"  - Created: {created}")
                output.append(f"  - Assignee: {assignee_name}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n✅ No items in to do!\n")
        
        # In-progress items
        output.append("\n## 🚧 In Progress Status")
        if report.in_progress_items:
            output.append(f"\n**Count:** {len(report.in_progress_items)} items currently active\n")
            for item in report.in_progress_items:
                key = item.get('key', 'N/A')
                summary = item.get('fields', {}).get('summary', 'No summary')
                assignee = item.get('fields', {}).get('assignee', {})
                assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
                status = item.get('fields', {}).get('status', {}).get('name', 'Unknown')
                updated = item.get('fields', {}).get('updated', 'N/A')
                
                output.append(f"- **{key}**: {summary}")
                output.append(f"  - Status: {status}")
                output.append(f"  - Assignee: {assignee_name}")
                output.append(f"  - Last Updated: {updated}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n✅ No items in progress.\n")
        
        # Waiting for customer items
        output.append("\n## ⏳ Waiting for Customer Status")
        if report.waiting_for_customer_items:
            output.append(f"\n**Count:** {len(report.waiting_for_customer_items)} items waiting for customer response\n")
            for item in report.waiting_for_customer_items:
                key = item.get('key', 'N/A')
                summary = item.get('fields', {}).get('summary', 'No summary')
                assignee = item.get('fields', {}).get('assignee', {})
                assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
                updated = item.get('fields', {}).get('updated', 'N/A')
                
                output.append(f"- **{key}**: {summary}")
                output.append(f"  - Assignee: {assignee_name}")
                output.append(f"  - Last Updated: {updated}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n✅ No items waiting for customer.\n")
        
        # Stale items (ALERT!)
        output.append("\n## ⚠️  Stale Items (Not Updated >1 Day)")
        if report.stale_items:
            output.append(f"\n**Count:** {len(report.stale_items)} items may be blocked!\n")
            for item in report.stale_items:
                key = item.get('key', 'N/A')
                summary = item.get('fields', {}).get('summary', 'No summary')
                assignee = item.get('fields', {}).get('assignee', {})
                assignee_name = assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'
                updated = item.get('fields', {}).get('updated', 'N/A')
                
                output.append(f"- **🚨 {key}**: {summary}")
                output.append(f"  - Assignee: {assignee_name}")
                output.append(f"  - Last Updated: {updated}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n✅ No stale items!\n")
        
        # Unacknowledged customer comments
        output.append("\n## 💬 Unacknowledged Customer Comments")
        if report.unacknowledged_comments:
            output.append(f"\n**Count:** {len(report.unacknowledged_comments)} items need attention!\n")
            for item in report.unacknowledged_comments:
                issue = item.get('issue', {})
                key = issue.get('key', 'N/A')
                summary = issue.get('fields', {}).get('summary', 'No summary')
                comment_count = len(item.get('comments', []))
                
                output.append(f"- **{key}**: {summary}")
                output.append(f"  - Unacknowledged comments: {comment_count}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n✅ All customer comments acknowledged!\n")
        
        # Recently closed items (CELEBRATION!)
        output.append("\n## 🎉 Recently Closed Items (Celebrate!)")
        if report.recently_closed:
            output.append(f"\n**Count:** {len(report.recently_closed)} items completed!\n")
            for item in report.recently_closed:
                key = item.get('key', 'N/A')
                summary = item.get('fields', {}).get('summary', 'No summary')
                assignee = item.get('fields', {}).get('assignee', {})
                assignee_name = assignee.get('displayName', 'Team') if assignee else 'Team'
                resolved = item.get('fields', {}).get('resolutiondate', 'N/A')
                
                output.append(f"- **{key}**: {summary}")
                output.append(f"  - Resolved by: {assignee_name}")
                output.append(f"  - Resolved: {resolved}")
                output.append(f"  - Link: https://cirium.atlassian.net/browse/{key}")
        else:
            output.append("\n📊 No items closed recently.\n")
        
        # Comment Activity Analysis
        output.append("\n## 🗨️  Comment Activity Analysis (Least Recent First)")
        if report.items_by_comment_activity:
            output.append(f"\n**Count:** {len(report.items_by_comment_activity)} active items analyzed\n")
            
            # Show top 10 items needing attention
            items_needing_attention = [
                item for item in report.items_by_comment_activity
                if item['comment_count'] == 0 or (item['days_since_activity'] and item['days_since_activity'] > 3)
            ]
            
            if items_needing_attention:
                output.append(f"**⚠️  Items needing attention:** {len(items_needing_attention)} items with no comments or >3 days since last comment\n")
                for idx, item in enumerate(items_needing_attention[:10], 1):
                    output.append(f"{idx}. **{item['key']}**: {item['summary'][:60]}")
                    output.append(f"   - Status: {item['status']} | Assignee: {item['assignee']}")
                    output.append(f"   - Created: {item['created'][:10]}")
                    
                    if item['comment_count'] == 0:
                        output.append(f"   - Comments: ❌ NO COMMENTS ({item['days_since_activity']} days old)")
                    else:
                        # Determine who made the last comment
                        last_comment_by = ""
                        if item['last_comment_by_team'] is True:
                            last_comment_by = " 👥 [TEAM]"
                        elif item['last_comment_by_team'] is False:
                            last_comment_by = " 👤 [CUSTOMER]"
                        
                        output.append(f"   - Comments: {item['comment_count']} total")
                        output.append(f"   - Last comment: {item['last_comment_date'][:10]} ({item['days_since_activity']} days ago) by {item['last_comment_author']}{last_comment_by}")
                    
                    output.append(f"   - Link: https://cirium.atlassian.net/browse/{item['key']}")
                
                if len(items_needing_attention) > 10:
                    output.append(f"\n*...and {len(items_needing_attention) - 10} more items needing attention*")
            else:
                output.append("\n✅ All items have recent comment activity!\n")
            
            # Summary stats
            no_comment_count = sum(1 for i in report.items_by_comment_activity if i['comment_count'] == 0)
            customer_last_comment_count = sum(1 for i in report.items_by_comment_activity if i.get('last_comment_by_team') is False)
            output.append(f"\n**Summary:**")
            output.append(f"- Total active issues: {len(report.items_by_comment_activity)}")
            output.append(f"- Issues with NO comments: {no_comment_count}")
            output.append(f"- Issues where CUSTOMER commented last: {customer_last_comment_count}")
            output.append(f"- Issues needing attention: {len(items_needing_attention)}")
        else:
            output.append("\n✅ No active items to analyze.\n")
        
        output.append("\n---")
        output.append("\n*Report generated by SRE Board Watcher*")
        
        return "\n".join(output)


def main():
    """Main entry point for the board watcher script"""
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Load configuration from config.yaml
    config = {}
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        print(f"[INFO] Loaded configuration from {config_path}", file=sys.stderr)
    except FileNotFoundError:
        print(f"[WARN] Configuration file not found: {config_path}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] Error loading configuration: {e}", file=sys.stderr)
    
    # Get configuration from environment (takes precedence over config file)
    JIRA_URL = os.getenv('JIRA_URL')
    JIRA_EMAIL = os.getenv('JIRA_EMAIL')
    JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')
    PROJECT_KEY = os.getenv('JIRA_PROJECT') or config.get('project', {}).get('key', 'CDPSUPPORT')
    BOARD_ID = os.getenv('JIRA_BOARD_ID') or config.get('project', {}).get('board_id', '404')
    TEAM_NAME = os.getenv('JIRA_TEAM_NAME') or config.get('team', {}).get('name')
    
    # Validate required environment variables
    if not all([JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
        print("[ERROR] Missing required environment variables!", file=sys.stderr)
        print("[ERROR] Please ensure JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN are set in .env", file=sys.stderr)
        return 1
    
    print("[INFO] Starting Jira Board Watcher...", file=sys.stderr)
    print(f"[INFO] Board: {PROJECT_KEY} (#{BOARD_ID})", file=sys.stderr)
    print(f"[INFO] Jira URL: {JIRA_URL}", file=sys.stderr)
    if TEAM_NAME:
        print(f"[INFO] Team Name: {TEAM_NAME}", file=sys.stderr)
    
    # Initialize the watcher
    watcher = JiraBoardWatcher(
        jira_url=JIRA_URL,
        email=JIRA_EMAIL,
        api_token=JIRA_API_TOKEN,
        project_key=PROJECT_KEY,
        board_id=BOARD_ID,
        team_name=TEAM_NAME
    )
    
    # Generate the report
    report = watcher.generate_triage_report()
    
    # Format and print the report
    formatted_report = watcher.format_report(report)
    print(formatted_report)
    
    # Return appropriate exit code
    if report.stale_items or report.unacknowledged_comments or report.triage_items:
        print("\n[WARN] Action required: stale items, unacknowledged comments, or items need triage!", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
