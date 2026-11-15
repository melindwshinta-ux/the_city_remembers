"""Non-blocking Prologue & Mission 1-2 Tutorial state machine backed by world.flags."""

from __future__ import annotations

from typing import Any

from content.prologue import (
    PROLOGUE_BEATS,
    PROLOGUE_CHOICES,
    TUTORIAL_STEPS,
    apply_prologue_choice,
)


class TutorialManager:
    """Manages interactive Prologue and hands-on Mission 1-2 Tutorial state in world.flags."""

    def __init__(self, world: Any) -> None:
        self.world = world
        self._ensure_flags()

    def _ensure_flags(self) -> tuple[dict[str, Any], dict[str, Any]]:
        already_done = bool(getattr(getattr(self.world, "clock", None), "prologue_completed", False))
        if "prologue" not in self.world.flags or not isinstance(self.world.flags["prologue"], dict):
            self.world.flags["prologue"] = {
                "active": not already_done,
                "completed": already_done,
                "skipped": False,
                "step": len(PROLOGUE_BEATS) if already_done else 0,
                "choices_made": {},
                "applied_effects": [],
            }
        else:
            p_flag = self.world.flags["prologue"]
            p_flag.setdefault("active", not already_done)
            p_flag.setdefault("completed", already_done)
            p_flag.setdefault("skipped", False)
            raw_step = p_flag.get("step", len(PROLOGUE_BEATS) if already_done else 0)
            try:
                step_int = int(raw_step)
            except (TypeError, ValueError):
                step_int = 0
            p_flag["step"] = max(0, step_int)
            if not isinstance(p_flag.get("choices_made"), dict):
                p_flag["choices_made"] = {}
            if not isinstance(p_flag.get("applied_effects"), list):
                p_flag["applied_effects"] = []

        if "tutorial" not in self.world.flags or not isinstance(self.world.flags["tutorial"], dict):
            self.world.flags["tutorial"] = {
                "enabled": True,
                "completed": False,
                "skipped": False,
                "completed_steps": [],
            }
        else:
            t_flag = self.world.flags["tutorial"]
            t_flag.setdefault("enabled", True)
            t_flag.setdefault("completed", False)
            t_flag.setdefault("skipped", False)
            if not isinstance(t_flag.get("completed_steps"), list):
                t_flag["completed_steps"] = []

        return self.world.flags["prologue"], self.world.flags["tutorial"]

    # ------------------------------------------------------------------
    # Prologue API
    # ------------------------------------------------------------------
    def get_prologue_state(self) -> dict[str, Any]:
        p_flag, _ = self._ensure_flags()
        step = int(p_flag.get("step", 0))
        total = len(PROLOGUE_BEATS)
        completed = bool(p_flag.get("completed", False))
        beat = PROLOGUE_BEATS[step] if (not completed and 0 <= step < total) else None
        return {
            "active": bool(p_flag.get("active", False)),
            "completed": completed,
            "skipped": bool(p_flag.get("skipped", False)),
            "step": step,
            "total_steps": total,
            "beat": beat,
            "choices_made": dict(p_flag.get("choices_made", {})),
        }

    def advance_prologue(self, choice_id: str | None = None) -> dict[str, Any]:
        p_flag, _ = self._ensure_flags()
        if p_flag.get("completed"):
            return {
                "success": True,
                "message": "Prologue already completed.",
                "state": self.get_prologue_state(),
            }

        step = int(p_flag.get("step", 0))
        total = len(PROLOGUE_BEATS)
        if step >= total:
            p_flag["completed"] = True
            p_flag["active"] = False
            if hasattr(self.world, "clock") and hasattr(self.world.clock, "complete_prologue"):
                self.world.clock.complete_prologue()
            return {
                "success": True,
                "message": "Prologue completed.",
                "state": self.get_prologue_state(),
            }

        beat = PROLOGUE_BEATS[step]
        effect_msg = ""
        if beat.get("requires_choice"):
            valid_choices = beat.get("choices", [])
            if not choice_id or choice_id not in valid_choices:
                return {
                    "success": False,
                    "message": f"Choice required for '{beat['title']}'. Valid options: {', '.join(valid_choices)}.",
                    "state": self.get_prologue_state(),
                }
            applied_list = p_flag.setdefault("applied_effects", [])
            if choice_id not in applied_list and self.world.flags.get("prologue_choice") is None:
                res = apply_prologue_choice(self.world, choice_id)
                if not res.get("success"):
                    return {
                        "success": False,
                        "message": res.get("message", "Failed to apply prologue choice."),
                        "state": self.get_prologue_state(),
                    }
                applied_list.append(choice_id)
                effect_msg = res.get("message", "")
            else:
                label = PROLOGUE_CHOICES.get(choice_id, {}).get("label", choice_id)
                effect_msg = f"Selected '{label}'."
            p_flag.setdefault("choices_made", {})[beat["id"]] = choice_id

        p_flag["step"] = step + 1
        if p_flag["step"] >= total:
            p_flag["completed"] = True
            p_flag["active"] = False
            if hasattr(self.world, "clock") and hasattr(self.world.clock, "complete_prologue"):
                self.world.clock.complete_prologue()
            msg = effect_msg or "Prologue complete. Welcome to Veyr — Act I begins."
        else:
            next_beat = PROLOGUE_BEATS[p_flag["step"]]
            msg = f"Prologue ({p_flag['step'] + 1}/{total}): {next_beat['title']}"

        return {
            "success": True,
            "message": msg,
            "state": self.get_prologue_state(),
        }

    def skip_prologue(self) -> dict[str, Any]:
        p_flag, _ = self._ensure_flags()
        p_flag["active"] = False
        p_flag["completed"] = True
        p_flag["skipped"] = True
        p_flag["step"] = len(PROLOGUE_BEATS)
        if hasattr(self.world, "clock") and hasattr(self.world.clock, "complete_prologue"):
            self.world.clock.complete_prologue()
        return {
            "success": True,
            "message": "Prologue skipped. Act I begins in Lowtown.",
            "state": self.get_prologue_state(),
        }

    def replay_prologue(self) -> dict[str, Any]:
        p_flag, _ = self._ensure_flags()
        p_flag["active"] = True
        p_flag["completed"] = False
        p_flag["skipped"] = False
        p_flag["step"] = 0
        p_flag["choices_made"] = {}
        return {
            "success": True,
            "message": f"Prologue restarted (1/{len(PROLOGUE_BEATS)}): {PROLOGUE_BEATS[0]['title']}",
            "state": self.get_prologue_state(),
        }

    # ------------------------------------------------------------------
    # Tutorial API
    # ------------------------------------------------------------------
    def get_tutorial_state(self) -> dict[str, Any]:
        _, t_flag = self._ensure_flags()
        completed_steps = list(t_flag.get("completed_steps", []))
        completed_set = set(completed_steps)

        current_step_info: dict[str, Any] | None = None
        for step_def in TUTORIAL_STEPS:
            if step_def["id"] not in completed_set:
                current_step_info = step_def
                break

        valid_ids = {s["id"] for s in TUTORIAL_STEPS}
        all_done = valid_ids.issubset(completed_set)
        if all_done and not t_flag.get("completed"):
            t_flag["completed"] = True

        done_count = len(completed_set & valid_ids)
        return {
            "enabled": bool(t_flag.get("enabled", True)),
            "completed": bool(t_flag.get("completed", False)),
            "skipped": bool(t_flag.get("skipped", False)),
            "current_step": current_step_info["id"] if current_step_info else None,
            "step_info": current_step_info,
            "completed_steps": completed_steps,
            "progress": (done_count, len(TUTORIAL_STEPS)),
        }

    def advance_tutorial_for_action(
        self,
        action: str,
        target: str = "",
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        _, t_flag = self._ensure_flags()
        if not t_flag.get("enabled", True) or t_flag.get("completed") or t_flag.get("skipped"):
            return None
        if result is not None and not result.get("success", False):
            return None

        completed_steps: list[str] = t_flag.setdefault("completed_steps", [])
        completed_set = set(completed_steps)
        current_step_id = next(
            (s["id"] for s in TUTORIAL_STEPS if s["id"] not in completed_set),
            None,
        )
        matched_idx: int | None = None

        # Find highest matching step (or current/future step)
        for idx, step_def in enumerate(TUTORIAL_STEPS):
            rule = step_def.get("completion_rule", {})
            if rule.get("require_current") and step_def["id"] != current_step_id:
                continue
            actions = rule.get("actions", [])
            targets = rule.get("targets", [])
            if action in actions and (not targets or target in targets):
                matched_idx = idx
                # Prefer the earliest uncompleted matching step if multiple match,
                # unless an out-of-order later step was explicitly completed.
                if step_def["id"] not in completed_steps:
                    break

        if matched_idx is not None:
            # Auto-advance any superseded earlier steps for out-of-order resilience
            for i in range(matched_idx + 1):
                sid = TUTORIAL_STEPS[i]["id"]
                if sid not in completed_steps:
                    completed_steps.append(sid)

        # If Blood in Lowtown was completed via direct API or choose_approach,
        # ensure all Mission 1 steps are marked complete.
        if self.world.flags.get("blood_in_lowtown_completed"):
            for step_def in TUTORIAL_STEPS:
                if step_def["mission_id"] == "quest_blood_in_lowtown":
                    if step_def["id"] not in completed_steps:
                        completed_steps.append(step_def["id"])

        valid_ids = {s["id"] for s in TUTORIAL_STEPS}
        if valid_ids.issubset(set(completed_steps)):
            t_flag["completed"] = True

        return self.get_tutorial_state()

    def skip_tutorial(self) -> dict[str, Any]:
        _, t_flag = self._ensure_flags()
        t_flag["enabled"] = False
        t_flag["skipped"] = True
        return {
            "success": True,
            "message": "Tutorial skipped. You can re-enable it anytime with 'tutorial reset'.",
            "state": self.get_tutorial_state(),
        }

    def reset_tutorial(self) -> dict[str, Any]:
        _, t_flag = self._ensure_flags()
        t_flag["enabled"] = True
        t_flag["completed"] = False
        t_flag["skipped"] = False
        t_flag["completed_steps"] = []
        return {
            "success": True,
            "message": "Tutorial reset to step 1.",
            "state": self.get_tutorial_state(),
        }
