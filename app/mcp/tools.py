"""
MCP Tools — all data comes from real integrations.

Data sources:
  • Slack   → messages & DMs from bot-accessible channels  (SLACK_BOT_TOKEN)
  • Jira    → open issues assigned to you                  (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN)
  • Gmail   → unread emails in inbox                       (GOOGLE_ACCESS_TOKEN + GOOGLE_REFRESH_TOKEN)
  • Calendar→ upcoming meetings in next 7 days             (GOOGLE_ACCESS_TOKEN + GOOGLE_REFRESH_TOKEN)
"""
import asyncio
from datetime import date, datetime, timezone
from typing import Any

from app.connectors.jira import JiraConnector
from app.connectors.slack import SlackConnector
from app.core import get_logger
from app.core.config import settings

logger = get_logger("mcp.tools")


# ---------------------------------------------------------------------------
# Tool: test_connections
# ---------------------------------------------------------------------------

async def test_connections(arguments: dict[str, Any]) -> dict[str, Any]:
    """Test connectivity to all configured integrations."""
    results: dict[str, dict] = {}

    # Slack
    if settings.SLACK_BOT_TOKEN:
        try:
            slack = SlackConnector(settings.SLACK_BOT_TOKEN, "test")
            ok = await slack.test_connection()
            results["slack"] = {"status": "ok" if ok else "auth_failed", "token_set": True}
        except Exception as e:
            results["slack"] = {"status": "error", "error": str(e)}
    else:
        results["slack"] = {"status": "not_configured", "missing": "SLACK_BOT_TOKEN"}

    # Jira
    jira_url = settings.JIRA_URL
    jira_email = settings.JIRA_EMAIL
    jira_token = settings.JIRA_API_TOKEN
    if jira_url and jira_email and jira_token:
        try:
            jira = JiraConnector(jira_url, jira_email, jira_token)
            ok = await jira.test_connection()
            results["jira"] = {"status": "ok" if ok else "auth_failed", "url": jira_url}
        except Exception as e:
            results["jira"] = {"status": "error", "error": str(e)}
    else:
        missing = [k for k, v in {"JIRA_URL": jira_url, "JIRA_EMAIL": jira_email, "JIRA_API_TOKEN": jira_token}.items() if not v]
        results["jira"] = {"status": "not_configured", "missing": missing}

    # Gmail
    google_token = settings.GOOGLE_ACCESS_TOKEN
    if google_token:
        try:
            from app.connectors.gmail import GmailConnector
            gmail = GmailConnector(google_token, "test", settings.GOOGLE_REFRESH_TOKEN or None)
            ok = await gmail.test_connection()
            results["gmail"] = {"status": "ok" if ok else "auth_failed"}
        except Exception as e:
            results["gmail"] = {"status": "error", "error": str(e)}
    else:
        results["gmail"] = {
            "status": "not_configured",
            "missing": "GOOGLE_ACCESS_TOKEN",
            "fix": "Run: python scripts/get_google_token.py",
        }

    # Calendar (shares token with Gmail)
    if google_token:
        try:
            from app.connectors.calendar import CalendarConnector
            cal = CalendarConnector(google_token, "test", settings.GOOGLE_REFRESH_TOKEN or None)
            ok = await cal.test_connection()
            results["calendar"] = {"status": "ok" if ok else "auth_failed"}
        except Exception as e:
            results["calendar"] = {"status": "error", "error": str(e)}
    else:
        results["calendar"] = {"status": "not_configured", "fix": "Same token as Gmail"}

    overall_ok = all(r.get("status") == "ok" for r in results.values())
    return {
        "overall": "all_ok" if overall_ok else "partial",
        "integrations": results,
    }



async def _fetch_all_work_items(limit_per_source: int = 20) -> tuple[list[dict], list[str], list[str]]:
    """Fetch work items from all configured integrations.

    Returns:
        (items, active_sources, errors)
    """
    tasks: list[dict] = []
    active_sources: list[str] = []
    errors: list[str] = []

    # ── 1. Slack ──────────────────────────────────────────────────────────────
    if settings.SLACK_BOT_TOKEN:
        try:
            logger.info("Connecting to Slack…")
            slack = SlackConnector(settings.SLACK_BOT_TOKEN, "mcp_user")
            items, _ = await slack.get_normalized_items(limit=limit_per_source)
            tasks.extend(items)
            active_sources.append("slack")
            logger.info("Slack fetch complete", count=len(items))
        except Exception as e:
            msg = f"Slack: {e}"
            logger.error("Slack fetch failed", error=str(e))
            errors.append(msg)
    else:
        errors.append("Slack: SLACK_BOT_TOKEN not set")

    # ── 2. Jira ───────────────────────────────────────────────────────────────
    jira_url = settings.JIRA_URL
    jira_email = settings.JIRA_EMAIL
    jira_token = settings.JIRA_API_TOKEN

    if jira_url and jira_email and jira_token:
        try:
            logger.info("Connecting to Jira…", url=jira_url)
            jira = JiraConnector(jira_url, jira_email, jira_token)
            items, _ = await jira.get_normalized_items(limit=limit_per_source)
            tasks.extend(items)
            active_sources.append("jira")
            logger.info("Jira fetch complete", count=len(items))
        except Exception as e:
            msg = f"Jira: {e}"
            logger.error("Jira fetch failed", error=str(e))
            errors.append(msg)
    else:
        missing = []
        if not jira_url:
            missing.append("JIRA_URL")
        if not jira_email:
            missing.append("JIRA_EMAIL")
        if not jira_token:
            missing.append("JIRA_API_TOKEN")
        errors.append(f"Jira: missing env vars → {', '.join(missing)}")

    # ── 3. Gmail ──────────────────────────────────────────────────────────────
    google_token = settings.GOOGLE_ACCESS_TOKEN
    google_refresh = settings.GOOGLE_REFRESH_TOKEN

    if google_token:
        try:
            # Import here so the rest of the module loads even if google libs are missing
            from app.connectors.gmail import GmailConnector
            logger.info("Connecting to Gmail…")
            gmail = GmailConnector(
                access_token=google_token,
                user_id="mcp_user",
                refresh_token=google_refresh or None,
            )
            items, _ = await gmail.get_normalized_items(limit=limit_per_source)
            tasks.extend(items)
            active_sources.append("gmail")
            logger.info("Gmail fetch complete", count=len(items))
        except Exception as e:
            msg = f"Gmail: {e}"
            logger.error("Gmail fetch failed", error=str(e))
            errors.append(msg)
    else:
        errors.append("Gmail: GOOGLE_ACCESS_TOKEN not set — run `python scripts/get_google_token.py`")

    # ── 4. Google Calendar (meetings) ─────────────────────────────────────────
    if google_token:
        try:
            from app.connectors.calendar import CalendarConnector
            logger.info("Connecting to Google Calendar…")
            cal = CalendarConnector(
                access_token=google_token,
                user_id="mcp_user",
                refresh_token=google_refresh or None,
            )
            items, _ = await cal.get_normalized_items(limit=limit_per_source)
            tasks.extend(items)
            if "calendar" not in active_sources:
                active_sources.append("calendar")
            logger.info("Calendar fetch complete", count=len(items))
        except Exception as e:
            msg = f"Calendar: {e}"
            logger.error("Calendar fetch failed", error=str(e))
            errors.append(msg)

    return tasks, active_sources, errors


# ---------------------------------------------------------------------------
# Tool: get_workload
# ---------------------------------------------------------------------------

async def get_workload(arguments: dict[str, Any]) -> dict[str, Any]:
    """Fetch ALL open work for the developer — Slack, Jira, Gmail, Calendar."""
    user_id = arguments.get("user_id", "developer")

    logger.info("get_workload called", user_id=user_id)
    tasks, active_sources, errors = await _fetch_all_work_items(limit_per_source=20)

    # Summarise by category
    by_source: dict[str, int] = {}
    for t in tasks:
        src = t.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    response: dict[str, Any] = {
        "status": "success" if tasks else "partial",
        "user": user_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "active_sources": active_sources,
        "total_items": len(tasks),
        "by_source": by_source,
        "items": tasks,
    }
    if errors:
        response["integration_warnings"] = errors
    if not tasks:
        response["setup_guide"] = (
            "No items found. Check your .env:\n"
            "  • SLACK_BOT_TOKEN  — bot token from api.slack.com/apps\n"
            "  • JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN\n"
            "  • Run 'python scripts/get_google_token.py' for Gmail/Calendar"
        )
    return response


# ---------------------------------------------------------------------------
# Tool: schedule_day
# ---------------------------------------------------------------------------

async def schedule_day(arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a time-blocked schedule for the day using real work items."""
    target_date = arguments.get("date", date.today().isoformat())
    preferences = arguments.get("preferences", {})

    logger.info("schedule_day called", date=target_date)
    tasks, active_sources, errors = await _fetch_all_work_items(limit_per_source=30)

    # Separate meetings (fixed time) vs. tasks (flexible)
    meetings = [t for t in tasks if t.get("category") in ("meeting", "calendar_event")]
    actionable = [t for t in tasks if t.get("category") not in ("meeting", "calendar_event", "message")]

    # Sort actionable by urgency × importance (Eisenhower matrix score)
    actionable.sort(
        key=lambda x: x.get("urgency", 0.5) * x.get("importance", 0.5),
        reverse=True,
    )

    schedule_blocks = []

    # Fixed meeting blocks
    for m in meetings:
        meta = m.get("metadata", {})
        schedule_blocks.append({
            "type": "meeting",
            "start": meta.get("start_time", "TBD"),
            "end": meta.get("end_time", "TBD"),
            "title": m.get("title"),
            "source": m.get("source"),
        })

    # Fill remaining time with highest-priority tasks (90-min focus blocks)
    work_start = preferences.get("work_start", "09:00")
    for i, task in enumerate(actionable[:5]):
        schedule_blocks.append({
            "type": "focus_block",
            "slot": f"Block {i + 1}",
            "title": task.get("title"),
            "source": task.get("source"),
            "urgency": task.get("urgency"),
            "estimated_effort_minutes": task.get("estimated_effort_minutes") or 90,
        })

    return {
        "status": "success",
        "date": target_date,
        "active_sources": active_sources,
        "total_meetings": len(meetings),
        "total_tasks_scheduled": min(len(actionable), 5),
        "schedule": schedule_blocks,
        "integration_warnings": errors or [],
    }


# ---------------------------------------------------------------------------
# Tool: prioritize_tasks
# ---------------------------------------------------------------------------

async def prioritize_tasks(arguments: dict[str, Any]) -> dict[str, Any]:
    """Rank all open work by urgency × importance (Eisenhower matrix)."""
    logger.info("prioritize_tasks called")
    tasks, active_sources, errors = await _fetch_all_work_items(limit_per_source=30)

    def _score(t: dict) -> float:
        return t.get("urgency", 0.5) * t.get("importance", 0.5)

    prioritized = sorted(tasks, key=_score, reverse=True)

    # Tag each item with a priority tier
    result = []
    for t in prioritized:
        score = _score(t)
        tier = "P1-Critical" if score >= 0.7 else ("P2-High" if score >= 0.4 else "P3-Normal")
        result.append({
            "title": t.get("title"),
            "source": t.get("source"),
            "category": t.get("category"),
            "score": round(score, 3),
            "priority_tier": tier,
            "requires_response": t.get("requires_response"),
            "due_date": t.get("due_date"),
        })

    return {
        "status": "success",
        "active_sources": active_sources,
        "total": len(result),
        "prioritized_tasks": result,
        "integration_warnings": errors or [],
    }


# ---------------------------------------------------------------------------
# Tool: estimate_effort
# ---------------------------------------------------------------------------

async def estimate_effort(arguments: dict[str, Any]) -> dict[str, Any]:
    """Estimate effort for a given task description (heuristic model)."""
    task_description = arguments.get("task_description", "")

    desc_lower = task_description.lower()

    # Simple keyword-based heuristic
    if any(k in desc_lower for k in ["bug", "fix", "crash", "error"]):
        hours, confidence = 1.5, 0.80
    elif any(k in desc_lower for k in ["feature", "implement", "build", "create"]):
        hours, confidence = 4.0, 0.70
    elif any(k in desc_lower for k in ["review", "pr", "code review"]):
        hours, confidence = 1.0, 0.90
    elif any(k in desc_lower for k in ["meeting", "call", "sync", "standup"]):
        hours, confidence = 0.5, 0.95
    elif any(k in desc_lower for k in ["refactor", "cleanup", "migration"]):
        hours, confidence = 3.0, 0.65
    elif any(k in desc_lower for k in ["docs", "documentation", "readme"]):
        hours, confidence = 1.0, 0.85
    else:
        hours, confidence = 2.0, 0.60

    return {
        "status": "success",
        "task": task_description,
        "estimated_hours": hours,
        "estimated_minutes": int(hours * 60),
        "confidence": confidence,
        "model": "keyword_heuristic_v1",
    }


# ---------------------------------------------------------------------------
# Tool: detect_blockers
# ---------------------------------------------------------------------------

async def detect_blockers(arguments: dict[str, Any]) -> dict[str, Any]:
    """Detect potential blockers by looking for 'blocked', 'waiting', 'pending' in work items."""
    logger.info("detect_blockers called")
    tasks, active_sources, errors = await _fetch_all_work_items(limit_per_source=30)

    blocker_keywords = ["block", "wait", "depend", "need", "pending", "stall", "stuck", "hold"]
    response_overdue = [
        t for t in tasks
        if t.get("requires_response") and t.get("urgency", 0) > 0.6
    ]
    keyword_matches = [
        t for t in tasks
        if any(k in (t.get("title", "") + " " + (t.get("description") or "")).lower() for k in blocker_keywords)
    ]

    blockers = []
    for t in response_overdue:
        blockers.append({
            "item": t.get("title"),
            "source": t.get("source"),
            "type": "response_overdue",
            "urgency": t.get("urgency"),
        })
    for t in keyword_matches:
        if t not in response_overdue:
            blockers.append({
                "item": t.get("title"),
                "source": t.get("source"),
                "type": "keyword_match",
                "urgency": t.get("urgency"),
            })

    return {
        "status": "success",
        "active_sources": active_sources,
        "blockers_detected": len(blockers),
        "blockers": blockers,
        "integration_warnings": errors or [],
    }


# ---------------------------------------------------------------------------
# Tool: summarize_context
# ---------------------------------------------------------------------------

async def summarize_context(arguments: dict[str, Any]) -> dict[str, Any]:
    """Summarize the developer's current work context from all integrations."""
    logger.info("summarize_context called")
    tasks, active_sources, errors = await _fetch_all_work_items(limit_per_source=20)

    meetings = [t for t in tasks if t.get("category") in ("meeting", "calendar_event")]
    jira_issues = [t for t in tasks if t.get("source") == "jira"]
    slack_msgs = [t for t in tasks if t.get("source") == "slack"]
    emails = [t for t in tasks if t.get("source") == "gmail"]
    urgent = [t for t in tasks if t.get("urgency", 0) >= 0.7]

    lines = [f"📊 Context as of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"]
    lines.append(f"Sources active: {', '.join(active_sources) or 'none'}")
    lines.append("")
    if jira_issues:
        lines.append(f"🎫 Jira — {len(jira_issues)} open issue(s):")
        for t in jira_issues[:5]:
            lines.append(f"  • {t['title']}")
    if slack_msgs:
        lines.append(f"💬 Slack — {len(slack_msgs)} recent message(s)")
    if emails:
        lines.append(f"📧 Gmail — {len(emails)} unread email(s)")
    if meetings:
        lines.append(f"📅 Calendar — {len(meetings)} upcoming event(s):")
        for m in meetings[:3]:
            meta = m.get("metadata", {})
            lines.append(f"  • {m['title']} @ {meta.get('start_time', 'TBD')}")
    if urgent:
        lines.append(f"\n🔥 {len(urgent)} urgent item(s) need attention now:")
        for t in urgent[:3]:
            lines.append(f"  • [{t['source'].upper()}] {t['title']}")

    return {
        "status": "success",
        "active_sources": active_sources,
        "total_items": len(tasks),
        "summary": "\n".join(lines),
        "counts": {
            "jira": len(jira_issues),
            "slack": len(slack_msgs),
            "gmail": len(emails),
            "meetings": len(meetings),
            "urgent": len(urgent),
        },
        "integration_warnings": errors or [],
    }


# ---------------------------------------------------------------------------
# Tool: detect_overload
# ---------------------------------------------------------------------------

async def detect_overload(arguments: dict[str, Any]) -> dict[str, Any]:
    """Assess burnout risk based on volume and urgency of real work items."""
    user_id = arguments.get("user_id", "developer")
    logger.info("detect_overload called", user_id=user_id)
    tasks, active_sources, errors = await _fetch_all_work_items(limit_per_source=30)

    # Simple scoring model
    total = len(tasks)
    urgent_count = sum(1 for t in tasks if t.get("urgency", 0) >= 0.7)
    response_needed = sum(1 for t in tasks if t.get("requires_response"))
    meetings = sum(1 for t in tasks if t.get("category") in ("meeting", "calendar_event"))

    # Score: more items + more urgency = higher risk
    raw_score = min(1.0, (total * 0.02) + (urgent_count * 0.05) + (meetings * 0.03))
    if raw_score >= 0.7:
        risk_level = "high"
    elif raw_score >= 0.4:
        risk_level = "moderate"
    else:
        risk_level = "low"

    recommendations = []
    if urgent_count > 3:
        recommendations.append("🔥 Focus on urgent items first — defer everything else")
    if response_needed > 5:
        recommendations.append("📬 Batch your responses — set aside 30min reply block")
    if meetings > 4:
        recommendations.append("📅 Many meetings today — protect at least one 2-hour focus block")
    if total > 20:
        recommendations.append("📋 High task count — consider delegating or deferring lower priority items")
    if not recommendations:
        recommendations.append("✅ Load looks manageable — stay focused and take breaks")

    return {
        "status": "success",
        "user_id": user_id,
        "active_sources": active_sources,
        "burnout_risk_score": round(raw_score, 2),
        "risk_level": risk_level,
        "metrics": {
            "total_items": total,
            "urgent_items": urgent_count,
            "responses_needed": response_needed,
            "meetings_today": meetings,
        },
        "recommendations": recommendations,
        "integration_warnings": errors or [],
    }
