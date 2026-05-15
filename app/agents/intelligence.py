"""AI Intelligence agent for workload analysis."""
import json
from typing import Any, Optional

import structlog

from app.agents.llm_provider import call_llm, call_llm_structured

logger = structlog.get_logger(__name__)


class WorkloadIntelligenceAgent:
    """AI agent for intelligent workload analysis."""

    # Prompt templates
    URGENCY_DETECTION_PROMPT = """
    Analyze the following work item and determine its urgency score (0.0-1.0).
    Consider: deadlines, keywords like "urgent", "ASAP", "blocker", mentions, etc.
    
    Work Item:
    {title}
    {description}
    
    Return JSON: {{"urgency": <0-1>, "reasoning": "<reason>"}}
    """

    ACTION_EXTRACTION_PROMPT = """
    Extract specific actions from this work item. Identify what concrete steps are needed.
    
    Work Item:
    {title}
    {description}
    
    Return JSON: {{"actions": [<list of action steps>], "confidence": <0-1>}}
    """

    EFFORT_ESTIMATION_PROMPT = """
    Estimate the effort required for this work item in minutes.
    Consider complexity, scope, dependencies.
    
    Work Item:
    {title}
    {description}
    
    Return JSON: {{"estimated_minutes": <number>, "confidence": <0-1>, "reasoning": "<reason>"}}
    """

    DEPENDENCY_DETECTION_PROMPT = """
    Identify any dependencies or blockers mentioned in this work item.
    
    Work Item:
    {title}
    {description}
    
    Return JSON: {{"has_dependencies": <bool>, "dependency_types": [<list>], "blockers": [<list>]}}
    """

    CATEGORIZATION_PROMPT = """
    Categorize this work item. Is it deep work, shallow work, meeting, reactive, review, etc?
    
    Work Item:
    {title}
    {description}
    
    Return JSON: {{"category": "<category>", "is_deep_work": <bool>, "requires_focus": <bool>}}
    """

    async def detect_urgency(
        self,
        title: str,
        description: Optional[str] = None,
    ) -> tuple[float, str]:
        """Detect urgency from work item.

        Returns:
            Tuple of (urgency_score, reasoning)
        """
        try:
            prompt = self.URGENCY_DETECTION_PROMPT.format(
                title=title,
                description=description or "",
            )

            result = await call_llm_structured(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "urgency": {"type": "number"},
                        "reasoning": {"type": "string"},
                    },
                },
            )

            urgency = float(result.get("urgency", 0.5))
            urgency = max(0.0, min(1.0, urgency))  # Clamp to 0-1
            reasoning = result.get("reasoning", "")

            logger.info("Urgency detected", urgency=urgency, title=title[:50])
            return urgency, reasoning

        except Exception as e:
            logger.error("Urgency detection failed", error=str(e))
            return 0.5, ""  # Default to medium urgency

    async def extract_actions(
        self,
        title: str,
        description: Optional[str] = None,
    ) -> tuple[list[str], float]:
        """Extract actionable items from work item.

        Returns:
            Tuple of (actions, confidence_score)
        """
        try:
            prompt = self.ACTION_EXTRACTION_PROMPT.format(
                title=title,
                description=description or "",
            )

            result = await call_llm_structured(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "actions": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                    },
                },
            )

            actions = result.get("actions", [])
            confidence = float(result.get("confidence", 0.7))
            confidence = max(0.0, min(1.0, confidence))

            logger.info("Actions extracted", count=len(actions), title=title[:50])
            return actions, confidence

        except Exception as e:
            logger.error("Action extraction failed", error=str(e))
            return [], 0.5

    async def estimate_effort(
        self,
        title: str,
        description: Optional[str] = None,
    ) -> tuple[int, float]:
        """Estimate effort required in minutes.

        Returns:
            Tuple of (estimated_minutes, confidence_score)
        """
        try:
            prompt = self.EFFORT_ESTIMATION_PROMPT.format(
                title=title,
                description=description or "",
            )

            result = await call_llm_structured(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "estimated_minutes": {"type": "integer"},
                        "confidence": {"type": "number"},
                        "reasoning": {"type": "string"},
                    },
                },
            )

            minutes = int(result.get("estimated_minutes", 60))
            minutes = max(5, min(480, minutes))  # Clamp to 5 min - 8 hours
            confidence = float(result.get("confidence", 0.7))
            confidence = max(0.0, min(1.0, confidence))

            logger.info(
                "Effort estimated",
                minutes=minutes,
                confidence=confidence,
                title=title[:50],
            )
            return minutes, confidence

        except Exception as e:
            logger.error("Effort estimation failed", error=str(e))
            return 60, 0.5  # Default to 1 hour

    async def detect_dependencies(
        self,
        title: str,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        """Detect dependencies and blockers.

        Returns:
            Dictionary with dependency info
        """
        try:
            prompt = self.DEPENDENCY_DETECTION_PROMPT.format(
                title=title,
                description=description or "",
            )

            result = await call_llm_structured(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "has_dependencies": {"type": "boolean"},
                        "dependency_types": {"type": "array", "items": {"type": "string"}},
                        "blockers": {"type": "array", "items": {"type": "string"}},
                    },
                },
            )

            logger.info(
                "Dependencies detected",
                has_deps=result.get("has_dependencies"),
                title=title[:50],
            )
            return result

        except Exception as e:
            logger.error("Dependency detection failed", error=str(e))
            return {
                "has_dependencies": False,
                "dependency_types": [],
                "blockers": [],
            }

    async def categorize_work(
        self,
        title: str,
        description: Optional[str] = None,
    ) -> dict[str, Any]:
        """Categorize work item type.

        Returns:
            Dictionary with category info
        """
        try:
            prompt = self.CATEGORIZATION_PROMPT.format(
                title=title,
                description=description or "",
            )

            result = await call_llm_structured(
                prompt=prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "is_deep_work": {"type": "boolean"},
                        "requires_focus": {"type": "boolean"},
                    },
                },
            )

            logger.info(
                "Work categorized",
                category=result.get("category"),
                title=title[:50],
            )
            return result

        except Exception as e:
            logger.error("Work categorization failed", error=str(e))
            return {
                "category": "task",
                "is_deep_work": False,
                "requires_focus": False,
            }

    async def enrich_work_item(self, work_item: dict[str, Any]) -> dict[str, Any]:
        """Enrich work item with AI analysis.

        Runs all analysis methods and updates the work item.
        """
        logger.info("Enriching work item", source_id=work_item.get("source_id"))

        try:
            # Run analyses in parallel if needed (simplified version)
            urgency, urgency_reason = await self.detect_urgency(
                work_item["title"],
                work_item.get("description"),
            )

            effort, effort_confidence = await self.estimate_effort(
                work_item["title"],
                work_item.get("description"),
            )

            category_info = await self.categorize_work(
                work_item["title"],
                work_item.get("description"),
            )

            deps_info = await self.detect_dependencies(
                work_item["title"],
                work_item.get("description"),
            )

            # Update work item
            enriched = work_item.copy()
            enriched["urgency"] = urgency
            enriched["estimated_effort_minutes"] = effort
            enriched["category"] = category_info.get("category", work_item.get("category"))
            enriched["requires_deep_work"] = category_info.get("is_deep_work", False)
            enriched["confidence_score"] = min(
                urgency_confidence := 0.8,  # Placeholder
                effort_confidence,
                0.85,  # Default
            )
            enriched["metadata"]["ai_analysis"] = {
                "urgency_reason": urgency_reason,
                "has_blockers": deps_info.get("has_dependencies", False),
            }

            logger.info("Work item enriched", source_id=work_item.get("source_id"))
            return enriched

        except Exception as e:
            logger.error("Work item enrichment failed", error=str(e))
            return work_item  # Return original on error
