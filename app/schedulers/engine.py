"""Scheduling engine for generating optimized daily schedules."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog

from app.core.exceptions import SchedulingError

logger = structlog.get_logger(__name__)


class SchedulingEngine:
    """Generate optimized daily schedules."""

    # Default work hours
    DEFAULT_START_HOUR = 9
    DEFAULT_END_HOUR = 18
    LUNCH_START = 12
    LUNCH_END = 13

    def __init__(
        self,
        work_items: list[dict[str, Any]],
        calendar_events: list[dict[str, Any]],
        user_preferences: Optional[dict[str, Any]] = None,
    ):
        """Initialize scheduler.

        Args:
            work_items: List of normalized work items
            calendar_events: List of calendar events
            user_preferences: User scheduling preferences
        """
        self.work_items = work_items
        self.calendar_events = calendar_events
        self.preferences = user_preferences or {}
        logger.info("Scheduling engine initialized")

    def generate_schedule(self, target_date: datetime) -> dict[str, Any]:
        """Generate optimized schedule for a day.

        Returns:
            Dictionary with schedule, blocks, and metrics
        """
        try:
            logger.info("Generating schedule", date=target_date.date())

            # 1. Extract available time blocks
            available_blocks = self._extract_available_blocks(target_date)
            logger.debug("Available blocks extracted", count=len(available_blocks))

            # 2. Sort and prioritize work items
            sorted_items = self._prioritize_work_items()
            logger.debug("Work items prioritized", count=len(sorted_items))

            # 3. Identify focus time requirements
            focus_blocks = self._identify_focus_blocks(available_blocks)
            logger.debug("Focus blocks identified", count=len(focus_blocks))

            # 4. Allocate work items to available blocks
            scheduled_items, focus_items = self._allocate_items_to_blocks(
                sorted_items,
                available_blocks,
                focus_blocks,
            )

            # 5. Calculate metrics
            metrics = self._calculate_metrics(scheduled_items, available_blocks)

            # 6. Generate confidence score
            confidence = self._calculate_confidence_score(scheduled_items, metrics)

            schedule = {
                "scheduled_date": target_date,
                "work_items": scheduled_items,
                "blocks": available_blocks,
                "focus_blocks": focus_items,
                "metrics": metrics,
                "confidence_score": confidence,
            }

            logger.info("Schedule generated", confidence=confidence, items=len(scheduled_items))
            return schedule

        except Exception as e:
            logger.error("Schedule generation failed", error=str(e))
            raise SchedulingError(f"Failed to generate schedule: {str(e)}")

    def _extract_available_blocks(self, target_date: datetime) -> list[dict[str, Any]]:
        """Extract available time blocks from calendar.

        Removes meeting times and breaks.
        """
        # Normalize to start of day
        day_start = target_date.replace(hour=self.DEFAULT_START_HOUR, minute=0, second=0)
        day_end = target_date.replace(hour=self.DEFAULT_END_HOUR, minute=0, second=0)

        # Get events for this day
        day_events = [
            e
            for e in self.calendar_events
            if e.get("metadata", {}).get("start_time")
            and datetime.fromisoformat(e["metadata"]["start_time"]).date() == target_date.date()
        ]

        # Build available blocks
        blocks = []
        current_time = day_start

        # Add lunch break
        lunch_start = day_start.replace(hour=self.LUNCH_START)
        lunch_end = day_start.replace(hour=self.LUNCH_END)
        day_events.append({
            "metadata": {
                "start_time": lunch_start.isoformat(),
                "end_time": lunch_end.isoformat(),
            },
            "title": "Lunch",
        })

        # Sort events by start time
        day_events.sort(key=lambda e: e.get("metadata", {}).get("start_time", ""))

        for event in day_events:
            try:
                event_start = datetime.fromisoformat(
                    event["metadata"]["start_time"].replace("Z", "+00:00")
                ).astimezone(timezone.utc)
                event_end = datetime.fromisoformat(
                    event["metadata"]["end_time"].replace("Z", "+00:00")
                ).astimezone(timezone.utc)

                # Add free block before event
                if current_time < event_start:
                    duration = int((event_start - current_time).total_seconds() / 60)
                    if duration > 15:  # Only add if > 15 min
                        blocks.append({
                            "start_time": current_time,
                            "end_time": event_start,
                            "duration_minutes": duration,
                            "is_free": True,
                        })

                current_time = event_end

            except (ValueError, KeyError):
                continue

        # Add remaining time until end of day
        if current_time < day_end:
            duration = int((day_end - current_time).total_seconds() / 60)
            if duration > 15:
                blocks.append({
                    "start_time": current_time,
                    "end_time": day_end,
                    "duration_minutes": duration,
                    "is_free": True,
                })

        logger.debug("Extracted available blocks", count=len(blocks))
        return blocks

    def _prioritize_work_items(self) -> list[dict[str, Any]]:
        """Sort work items by priority score.

        Priority = urgency + deadline_proximity + importance - effort_ratio
        """
        scored_items = []

        for item in self.work_items:
            # Calculate priority score
            urgency = item.get("urgency", 0.5)
            importance = item.get("importance", 0.5)

            # Deadline proximity (closer deadline = higher priority)
            deadline_proximity = 0
            if item.get("due_date"):
                due = datetime.fromisoformat(item["due_date"].replace("Z", "+00:00"))
                days_until = (due - datetime.now(timezone.utc)).days
                deadline_proximity = max(0, 1.0 - (days_until / 7))  # 7-day window

            # Effort ratio (effort/importance - prefer high-value tasks)
            effort_minutes = item.get("estimated_effort_minutes", 60)
            effort_ratio = min(1.0, effort_minutes / 480)  # 8 hours = max

            priority_score = (urgency * 0.4 + importance * 0.3 + deadline_proximity * 0.3) - (effort_ratio * 0.1)
            priority_score = max(0, min(1.0, priority_score))

            scored_items.append({
                **item,
                "priority_score": priority_score,
            })

        # Sort by priority descending
        scored_items.sort(key=lambda x: x["priority_score"], reverse=True)
        return scored_items

    def _identify_focus_blocks(self, available_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Identify focus time blocks (90+ min uninterrupted)."""
        focus_blocks = []

        for block in available_blocks:
            if block["duration_minutes"] >= 90:
                focus_blocks.append(block)

        return focus_blocks

    def _allocate_items_to_blocks(
        self,
        items: list[dict[str, Any]],
        blocks: list[dict[str, Any]],
        focus_blocks: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Allocate work items to available time blocks.

        Prioritizes deep work items into focus blocks.
        """
        scheduled = []
        focus_scheduled = []
        remaining_blocks = blocks.copy()
        remaining_focus = focus_blocks.copy()

        for item in items:
            if not remaining_blocks and not remaining_focus:
                break

            effort_minutes = item.get("estimated_effort_minutes", 60)
            is_deep_work = item.get("requires_deep_work", False)

            # Try to fit in appropriate block
            if is_deep_work and remaining_focus:
                # Use focus block
                block = remaining_focus.pop(0)
                scheduled.append({
                    "work_item_id": item.get("source_id"),
                    "title": item.get("title"),
                    "start_time": block["start_time"],
                    "end_time": block["start_time"] + timedelta(minutes=effort_minutes),
                    "duration_minutes": effort_minutes,
                })
                focus_scheduled.append(scheduled[-1])

            elif remaining_blocks:
                # Use regular block
                block = remaining_blocks.pop(0)
                if block["duration_minutes"] >= effort_minutes:
                    scheduled.append({
                        "work_item_id": item.get("source_id"),
                        "title": item.get("title"),
                        "start_time": block["start_time"],
                        "end_time": block["start_time"] + timedelta(minutes=effort_minutes),
                        "duration_minutes": effort_minutes,
                    })

        return scheduled, focus_scheduled

    def _calculate_metrics(
        self,
        scheduled_items: list[dict[str, Any]],
        available_blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Calculate schedule metrics."""
        total_scheduled = sum(item.get("duration_minutes", 0) for item in scheduled_items)
        total_available = sum(block.get("duration_minutes", 0) for block in available_blocks)

        deep_work_items = sum(
            1 for item in self.work_items
            if item.get("requires_deep_work", False)
        )

        metrics = {
            "total_items": len(self.work_items),
            "scheduled_items": len(scheduled_items),
            "total_scheduled_minutes": total_scheduled,
            "total_available_minutes": total_available,
            "utilization_percentage": (
                (total_scheduled / total_available * 100)
                if total_available > 0
                else 0
            ),
            "deep_work_items": deep_work_items,
            "context_switches": self._count_context_switches(scheduled_items),
        }

        return metrics

    def _count_context_switches(self, scheduled_items: list[dict[str, Any]]) -> int:
        """Count context switches in schedule."""
        if len(scheduled_items) <= 1:
            return 0

        # Simplified: count transitions between different item categories
        switches = 0
        for i in range(len(scheduled_items) - 1):
            current_cat = scheduled_items[i].get("category", "")
            next_cat = scheduled_items[i + 1].get("category", "")
            if current_cat != next_cat:
                switches += 1

        return switches

    def _calculate_confidence_score(
        self,
        scheduled_items: list[dict[str, Any]],
        metrics: dict[str, Any],
    ) -> float:
        """Calculate overall schedule confidence (0-1)."""
        # Factors:
        # - Higher utilization (40-80% is good)
        # - Lower context switches
        # - More focus blocks
        # - Higher average item confidence

        utilization = metrics.get("utilization_percentage", 0)
        utilization_score = 1.0 - abs(utilization - 60) / 100  # Peak at 60%

        switch_score = 1.0 - min(1.0, metrics.get("context_switches", 0) / 5)  # Penalize switches

        focus_ratio = (
            len([s for s in scheduled_items if s.get("duration_minutes", 0) >= 90])
            / max(1, len(scheduled_items))
        )

        avg_item_confidence = (
            sum(item.get("confidence_score", 0.7) for item in scheduled_items)
            / max(1, len(scheduled_items))
        )

        confidence = (
            utilization_score * 0.3 +
            switch_score * 0.2 +
            focus_ratio * 0.2 +
            avg_item_confidence * 0.3
        )

        return max(0.0, min(1.0, confidence))
