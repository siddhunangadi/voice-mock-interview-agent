import unittest
from pydantic import ValidationError
from app.interview import Context, Decision, State, allowed_topics, choose_question, repeated


def context():
    return Context(
        skills=['Python'], projects=['RAG search'], experience=['Search engineer'], education=['BSc'],
        responsibilities=['Build search'], required_skills=['retrieval'], preferred_skills=['SQL'],
        overlaps=['Python'], gaps=['SQL'],
        topics=[dict(name=name, evidence='RAG search project; JD requires retrieval', priority=i + 1)
                for i, name in enumerate(['retrieval', 'evaluation', 'deployment', 'SQL'])],
        first_question='How did you design retrieval for your RAG search project?')


class ControllerTests(unittest.TestCase):
    def test_warmup_cannot_jump_to_technical_questions(self):
        from app.interview import OPENING
        self.assertIn('tell me about yourself', OPENING)
        ctx, state = context(), State(stage='introduction')
        decision = Decision(topic=3, action='finish', question='Explain BM25 scoring?',
                            assessment='Introduction', evidence='background', score=None)
        question, state = choose_question(ctx, state, decision, [OPENING])
        self.assertIn('interested you', question)
        self.assertEqual(state.covered, [])
        question, state = choose_question(ctx, state, decision, [OPENING, question])
        self.assertIn('high-level overview', question)
        self.assertEqual(state.stage, 'discussion')
        self.assertEqual(state.depth, 0)
        self.assertEqual(state.covered, [])

    def test_fresher_clarification_does_not_consume_project_coverage(self):
        state = State()
        decision = Decision(answers_question=False, action='advance', topic=1,
            question='Tell me about your next project.', assessment='Clarifies no employment',
            evidence='I am a fresher', score=0)
        question, updated = choose_question(context(), state, decision, [])
        self.assertIn('academic or personal project', question)
        self.assertEqual(updated.topic, 0)
        self.assertEqual(updated.covered, [])
        self.assertEqual(updated.depth, 0)

    def test_spoken_question_matching_tolerates_transcription_changes(self):
        from app.interview import OPENING, stale_question
        spoken = 'Hi. Welcome to your mock interview. We will start with your background, then discuss your experience and some role related problems. Begin, tell me about yourself.'
        self.assertFalse(stale_question(spoken, [OPENING]))
        motivation = 'Thank you for introducing yourself. What interested you in this role?'
        self.assertTrue(stale_question(spoken, [OPENING, motivation]))
        self.assertFalse(stale_question('Thank you for introducing yourself. Interested you in this role?', [OPENING, motivation]))
        self.assertFalse(stale_question('Unrecognized partial speech', [OPENING, motivation]))

    def test_fresher_projects_are_separate_and_visited_in_order(self):
        from app.interview import plan_projects
        ctx = context()
        ctx.experience = []
        ctx.projects = ['Search', 'Chatbot', 'Forecast', 'Portfolio', 'Scheduler']
        plan_projects(ctx)
        self.assertEqual(len(ctx.topics), 7)
        self.assertTrue(all(t.project for t in ctx.topics[:5]))
        state = State(question_count=3)
        for target in range(1, 5):
            decision = Decision(action='advance', topic=target, question='Skip the projects?',
                                assessment='Answered', evidence='test', score=2)
            question, state = choose_question(ctx, state, decision, [])
            self.assertIn(ctx.projects[target], question)
            self.assertEqual(state.topic, target)
        employed = context()
        plan_projects(employed)
        self.assertFalse(any(t.project for t in employed.topics))

    def test_depth_and_coverage_reservation(self):
        ctx = context()
        self.assertEqual(allowed_topics(ctx, State()), [0, 1])
        self.assertEqual(allowed_topics(ctx, State(depth=2)), [1])
        self.assertEqual(allowed_topics(ctx, State(question_count=15)), [1])
        self.assertEqual(allowed_topics(ctx, State(question_count=18)), [])

    def test_novel_contextual_followup(self):
        ctx, state = context(), State()
        decision = Decision(topic=0, action='followup', question='Why did hybrid retrieval outperform vector similarity in your project?',
                            assessment='Named hybrid retrieval without justification.', evidence='hybrid retrieval', score=2)
        question, updated = choose_question(ctx, state, decision, [ctx.first_question])
        self.assertIn('hybrid', question)
        self.assertEqual(updated.depth, 1)
        self.assertEqual(updated.question_count, 2)
        self.assertEqual(state.question_count, 1)

    def test_invalid_topic_and_duplicate_advance_safely(self):
        ctx, state = context(), State(depth=2)
        decision = Decision(topic=0, action='followup', question=ctx.first_question,
                            assessment='Vague', evidence='search', score=1)
        question, updated = choose_question(ctx, state, decision, [ctx.first_question])
        self.assertNotEqual(question, ctx.first_question)
        self.assertEqual(updated.topic, 1)
        self.assertEqual(updated.depth, 0)

    def test_completion_and_no_endless_last_topic_followups(self):
        ctx = context()
        decision = Decision(topic=3, action='followup', question='Why?', assessment='Partial', evidence='SQL', score=2)
        question, state = choose_question(ctx, State(topic=3, depth=2, question_count=7), decision, [])
        self.assertIn("Before we finish", question)
        self.assertTrue(state.wrapping_up)
        self.assertIsNone(choose_question(ctx, state, decision, [question])[0])

    def test_early_finish_cannot_skip_uncovered_competencies(self):
        ctx = context()
        decision = Decision(topic=0, action='finish', question='End now',
                            assessment='Detailed', evidence='example', score=3)
        question, state = choose_question(ctx, State(), decision, [ctx.first_question])
        self.assertIsNotNone(question)
        self.assertEqual(state.topic, 1)
        self.assertFalse(state.wrapping_up)

    def test_followups_are_optional_and_not_a_fixed_quota(self):
        ctx = context()
        for depth in (0, 1):
            decision = Decision(topic=1, action='advance', question='How did you validate search quality?',
                                assessment='Sufficient evidence', evidence='measured results', score=3)
            _, state = choose_question(ctx, State(depth=depth), decision, [])
            self.assertEqual(state.topic, 1)
        decision = Decision(topic=3, action='finish', question='Done',
                            assessment='Sufficient evidence', evidence='example', score=3)
        question, state = choose_question(ctx, State(topic=3, question_count=6), decision, [])
        self.assertTrue(state.wrapping_up)
        self.assertIn('add or clarify', question)

    def test_repetition_ignores_case_punctuation(self):
        self.assertTrue(repeated('HOW did you design retrieval?', ['How did you design retrieval.']))
        self.assertFalse(repeated('How did you measure latency?', ['Why did you choose BM25?']))

    def test_structured_contract_rejects_invalid_scores_and_empty_question(self):
        with self.assertRaises(ValidationError):
            Decision(topic=0, action='followup', question='', assessment='a', evidence='b', score=8)


if __name__ == '__main__':
    unittest.main()

class RepeatRequestTests(unittest.TestCase):
    def test_repeat_request_does_not_match_technical_answers(self):
        from app.interview import requests_repeat
        self.assertTrue(requests_repeat('Can you repeat the question?'))
        self.assertFalse(requests_repeat('We repeat retrieval evaluations every week.'))
