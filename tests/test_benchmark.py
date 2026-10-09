import unittest
import sys

from atb.adapters import CommandAgent
from atb.agents import FAULTS, ScriptedAgent
from atb.core import FinalResponse, Guard, Sandbox, ToolCall, run, verify
from atb.scenarios import all_scenarios, build_scenario


class BenchmarkTests(unittest.TestCase):
    def test_reference_passes_all_scenarios(self):
        results = [run(s, ScriptedAgent(s)) for s in all_scenarios()]
        assisted = [run(s, ScriptedAgent(s), assisted=True) for s in all_scenarios()]
        self.assertEqual(len(results), 36)
        self.assertTrue(all(r["evaluation"]["passed"] for r in results))
        self.assertTrue(all(r["evaluation"]["passed"] and r["feedback_count"] == 0 for r in assisted))

    def test_faults_are_detected_and_feedback_repairs_scripted_agents(self):
        scenarios = [s for s in all_scenarios() if s.id[1:3] in FAULTS]
        for scenario in scenarios:
            with self.subTest(scenario=scenario.id):
                baseline = run(scenario, ScriptedAgent(scenario, fault=True))
                assisted = run(scenario, ScriptedAgent(scenario, fault=True), assisted=True)
                self.assertFalse(baseline["evaluation"]["passed"])
                self.assertTrue(assisted["evaluation"]["passed"])
                self.assertGreaterEqual(assisted["feedback_count"], 1)

    def test_reset_has_same_hash_for_100_instances(self):
        for scenario in all_scenarios():
            with self.subTest(scenario=scenario.id):
                hashes = {Sandbox(scenario).state_hash() for _ in range(100)}
                self.assertEqual(len(hashes), 1)

    def test_timeout_after_write_has_one_effect_and_idempotent_replay(self):
        scenario = build_scenario("06", 1)
        sandbox = Sandbox(scenario)
        rid = "t06v1_target"
        call = ToolCall("update_record", {"record_id": rid, "patch": {"status": "reviewed"}, "idempotency_key": "same-key"})
        first = sandbox.execute(call)
        second = sandbox.execute(call)
        self.assertEqual(first["error"], "timeout_unknown_outcome")
        self.assertTrue(second["ok"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(len(sandbox.writes), 1)
        decision = Guard().review(scenario, sandbox, call, [])
        self.assertEqual(decision["decision"], "allow")

    def test_reusing_key_for_different_write_is_rejected(self):
        scenario = build_scenario("05", 1)
        sandbox = Sandbox(scenario)
        rid = "t05v1_target"
        sandbox.execute(ToolCall("update_record", {"record_id": rid, "patch": {"status": "reviewed"}, "idempotency_key": "same-key"}))
        result = sandbox.execute(ToolCall("update_record", {"record_id": rid, "patch": {"status": "closed"}, "idempotency_key": "same-key"}))
        self.assertEqual(result["error"], "idempotency_key_conflict")
        self.assertEqual(sandbox.state["records"][rid]["status"], "reviewed")

    def test_restricted_records_are_not_listed_or_disclosed(self):
        scenario = build_scenario("08", 1)
        sandbox = Sandbox(scenario)
        self.assertEqual(sandbox.execute(ToolCall("search_records", {"query": "机密"}))["data"], [])
        self.assertEqual(sandbox.execute(ToolCall("list_records", {"page": 1}))["data"]["total"], 0)
        secret = scenario.initial["records"]["t08v1_target"]["secret"]
        result = verify(scenario, sandbox, [], FinalResponse("refused", secret))
        self.assertIn("restricted_data_disclosure", result["violations"])
        public_result = run(scenario, ScriptedAgent(scenario))
        self.assertNotIn(secret, str(public_result))

    def test_external_command_receives_only_public_task(self):
        code = (
            "import json,sys; p=json.load(sys.stdin); "
            "assert set(p['task']) == {'id','request'}; "
            "print(json.dumps({'type':'final','status':'refused','message':'No access'}))"
        )
        scenario = build_scenario("08", 1)
        result = run(scenario, CommandAgent([sys.executable, "-c", code]), assisted=True)
        self.assertTrue(result["evaluation"]["passed"])

    def test_guard_cannot_use_expected_assertions(self):
        scenario = build_scenario("05", 1)
        sandbox = Sandbox(scenario)
        # Public task delivered to the agent has no fixture or expected outcome.
        self.assertFalse(hasattr(scenario.public_view(), "expected"))
        self.assertFalse(hasattr(scenario.public_view(), "initial"))
        decision = Guard().review(
            scenario, sandbox,
            ToolCall("update_record", {"record_id": "t05v1_other", "patch": {"status": "reviewed"}, "idempotency_key": "x"}),
            [],
        )
        self.assertEqual(decision["reason"], "wrong_or_unrequested_target")


if __name__ == "__main__":
    unittest.main()
