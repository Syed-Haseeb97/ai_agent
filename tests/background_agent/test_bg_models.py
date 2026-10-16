import itertools
import json
import unittest

import helpers  # noqa: F401
from background_agent import (BackgroundTask, FailureCode, InvalidTransitionError, TaskError,
                              TaskLimits, TaskStatus, TERMINAL_STATUSES)
from background_agent.models import ALLOWED_TRANSITIONS


class TaskModelTests(unittest.TestCase):
    def new(self):
        return BackgroundTask("goal", TaskLimits())

    def test_new_task_fields(self):
        t = self.new()
        self.assertEqual(len(t.id), 32)
        self.assertEqual(t.status, TaskStatus.CREATED)
        self.assertEqual(t.goal, "goal")
        self.assertIsNotNone(t.created_at)
        self.assertIsNone(t.started_at)
        self.assertIsNone(t.completed_at)
        self.assertFalse(t.cancel_requested)

    def test_ids_are_unique(self):
        self.assertEqual(len({self.new().id for _ in range(500)}), 500)

    def test_transition_table_is_enforced_exhaustively(self):
        for src, dst in itertools.product(TaskStatus, TaskStatus):
            t = self.new()
            t._status = src  # force the starting state
            ok = t.try_transition(dst)
            self.assertEqual(ok, dst in ALLOWED_TRANSITIONS[src], f"{src} -> {dst}")

    def test_terminal_states_have_no_exits(self):
        for s in TERMINAL_STATUSES:
            self.assertEqual(ALLOWED_TRANSITIONS[s], frozenset())

    def test_first_terminal_transition_wins(self):
        t = self.new()
        t.transition(TaskStatus.QUEUED)
        self.assertTrue(t.try_transition(TaskStatus.CANCELLED))
        self.assertFalse(t.try_transition(TaskStatus.FAILED, error=TaskError(FailureCode.WORKER_EXCEPTION, "x")))
        self.assertEqual(t.status, TaskStatus.CANCELLED)
        self.assertIsNone(t.error)

    def test_invalid_transition_raises(self):
        with self.assertRaises(InvalidTransitionError):
            self.new().transition(TaskStatus.COMPLETED)

    def test_timestamps_set_on_run_and_finish(self):
        t = self.new()
        t.transition(TaskStatus.QUEUED)
        t.transition(TaskStatus.RUNNING)
        self.assertIsNotNone(t.started_at)
        t.transition(TaskStatus.FAILED, error=TaskError(FailureCode.BACKEND_FAILURE, "boom"))
        self.assertIsNotNone(t.completed_at)
        self.assertTrue(t.wait(0))

    def test_progress_ignored_after_terminal(self):
        t = self.new()
        t.transition(TaskStatus.CANCELLED)
        t.add_progress("late")
        self.assertEqual(len(t.progress), 0)

    def test_snapshot_is_json_safe_and_has_no_observation_data(self):
        t = self.new()
        t.transition(TaskStatus.QUEUED)
        t.add_progress("Step 1: fs.write out.txt - ok")
        t.track_output("/ws/out.txt")
        snap = json.loads(json.dumps(t.snapshot()))
        self.assertEqual(snap["status"], "queued")
        self.assertEqual(snap["outputs"][0], {"path": "/ws/out.txt", "size_bytes": None, "verified": False})
        self.assertEqual(set(snap) & {"screenshot", "observations", "history"}, set())

    def test_limits_validation(self):
        for bad in ({"max_actions": 0}, {"max_runtime_seconds": -1}, {"max_repeated_actions": 1}):
            with self.assertRaises(ValueError):
                TaskLimits(**bad)


if __name__ == "__main__":
    unittest.main()
