"""Run with LIVE_DATABASE=1; uses and removes only the synthetic rows it creates."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, db
from app.interview import Decision, Evaluation
from test_interview import context


@unittest.skipUnless(os.getenv('LIVE_DATABASE') == '1', 'requires configured Supabase')
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {'VAPI_SERVER_TOKEN': 'synthetic-provider-token',
                                          'VAPI_ASSISTANT_ID': str(uuid4())})
        self.env.start()
        self.call_id = str(uuid4())
        with patch('app.main.gemini', return_value=context()):
            result = self.client.post('/api/interviews', json={
                'resume': 'Synthetic candidate built a Python RAG retrieval project.',
                'job_description': 'Synthetic role requires retrieval, evaluation, deployment and SQL.'})
        self.assertEqual(result.status_code, 200)
        self.interview_id = result.json()['id']
        self.assertIn('tell me about yourself', result.json()['question'])
        with db() as conn:
            conn.execute("update interviews set state=jsonb_set(state,'{stage}', '\"discussion\"') where id=%s", (self.interview_id,))
        with patch('app.main.vapi_request', return_value={
            'id': self.call_id, 'webCallUrl': 'https://synthetic.daily.co/test',
            'privateKey': 'must-never-reach-browser', 'assistant': {'credentials': 'private'}}):
            call = self.client.post('/voice/call/web', json={'assistantId': self.interview_id})
        self.assertEqual(call.status_code, 200)
        self.assertEqual(set(call.json()), {'id', 'webCallUrl'})
        self.decision = Decision(topic=0, action='followup',
            question='Why did you choose hybrid retrieval instead of vector similarity alone?',
            assessment='Named a retrieval strategy but not its tradeoffs.', evidence='hybrid retrieval', score=2)
        self.body = {'metadata': {'interview_id': self.interview_id},
                     'call': {'id': self.call_id},
                     'messages': [{'role': 'assistant', 'content': result.json()['question']},
                                  {'role': 'user', 'content': 'We used hybrid retrieval.'}]}

    def tearDown(self):
        with db() as conn:
            conn.execute('delete from interviews where id=%s', (self.interview_id,))
        self.env.stop()

    def reply(self, body=None):
        return self.client.post('/vapi/chat/completions', json=body or self.body,
            headers={'Authorization': 'Bearer synthetic-provider-token'})

    def snapshot(self):
        return self.client.get(f'/api/interviews/{self.interview_id}').json()

    def test_successful_retry_is_not_a_second_answer(self):
        with patch('app.main.gemini', return_value=self.decision):
            first = self.reply()
            second = self.reply()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.json()['choices'], first.json()['choices'])
        self.assertEqual(len(self.snapshot()['turns']), 3)
        self.assertEqual(self.snapshot()['state']['question_count'], 2)

    def test_transcribed_opening_accepts_answer_and_advances(self):
        with db() as conn:
            conn.execute("update interviews set state=jsonb_set(state,'{stage}', '\"introduction\"') where id=%s", (self.interview_id,))
        body = {**self.body, 'messages': [
            {'role': 'assistant', 'content': 'Hi. Welcome to your mock interview. We will start with your background, then discuss your experience and some role related problems. Begin, tell me about yourself.'},
            {'role': 'user', 'content': 'I am a recent graduate who built a retrieval project in Python.'}]}
        with patch('app.main.gemini', return_value=self.decision) as generate:
            result = self.reply(body)
            retry = self.reply(body)
            generate.assert_not_called()
        self.assertEqual(result.status_code, 200)
        self.assertIn('interested you in this role', result.json()['choices'][0]['message']['content'])
        self.assertEqual(result.json()['choices'], retry.json()['choices'])
        self.assertEqual(self.snapshot()['state']['stage'], 'motivation')
        self.assertEqual(len(self.snapshot()['turns']), 3)

    def test_answer_to_old_question_cannot_answer_new_question(self):
        with patch('app.main.gemini', return_value=self.decision) as generate:
            self.reply()
            stale = {**self.body, 'messages': self.body['messages'] + [
                {'role': 'user', 'content': 'I am still explaining my background, not a project.'}]}
            self.assertEqual(self.reply(stale).status_code, 200)
            generate.assert_called_once()
        self.assertEqual(len(self.snapshot()['turns']), 3)

    def test_provider_failure_preserves_answer_and_retry_completes_it(self):
        with patch('app.main.gemini', side_effect=HTTPException(502, 'Synthetic provider failure')):
            failed = self.reply()
        self.assertEqual(failed.status_code, 502)
        self.assertEqual(len(self.snapshot()['turns']), 2)
        with patch('app.main.gemini', return_value=self.decision):
            self.assertEqual(self.reply().status_code, 200)
        self.assertEqual(len(self.snapshot()['turns']), 3)

    def test_repeated_words_in_a_later_answer_are_a_new_turn(self):
        with patch('app.main.gemini', return_value=self.decision):
            self.reply()
            new_body = {**self.body, 'messages': self.body['messages'] + [
                {'role': 'assistant', 'content': self.decision.question},
                {'role': 'user', 'content': 'We used hybrid retrieval.'}]}
            self.assertEqual(self.reply(new_body).status_code, 200)
        self.assertEqual(len(self.snapshot()['turns']), 5)

    def test_continued_speech_preserves_pending_answer(self):
        with patch('app.main.gemini', side_effect=HTTPException(502, 'Synthetic failure')):
            self.reply()
        continued = {**self.body, 'messages': self.body['messages'] + [
            {'role': 'user', 'content': 'We combined BM25 and embeddings.'}]}
        with patch('app.main.gemini', return_value=self.decision) as generate:
            self.assertEqual(self.reply(continued).status_code, 200)
        answer = generate.call_args.args[2]['answer']
        self.assertIn('hybrid retrieval', answer)
        self.assertIn('BM25', answer)
        self.assertEqual(len(self.snapshot()['turns']), 3)

    def test_repeat_does_not_consume_question_budget(self):
        body = {**self.body, 'messages': [{'role': 'user', 'content': 'Can you repeat the question?'}]}
        with patch('app.main.gemini') as generate:
            self.assertEqual(self.reply(body).status_code, 200)
            generate.assert_not_called()
        self.assertEqual(len(self.snapshot()['turns']), 1)

    def test_empty_interview_has_no_invented_score_and_finish_is_idempotent(self):
        evaluation = Evaluation(summary='Invented assessment', overall_score=0, strengths=['Invented'],
            improvements=['Invented'], recommendations=['Invented'], topics=[
                {'topic': t.name, 'score': 0, 'evidence': 'Invented', 'feedback': 'Invented'}
                for t in context().topics])
        with patch('app.main.gemini', return_value=evaluation) as generate:
            first = self.client.post(f'/api/interviews/{self.interview_id}/finish')
            second = self.client.post(f'/api/interviews/{self.interview_id}/finish')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertIsNone(first.json()['overall_score'])
        self.assertTrue(all(t['score'] is None for t in first.json()['topics']))
        generate.assert_called_once()

    def test_old_call_and_foreign_browser_cannot_access_interview(self):
        wrong = {**self.body, 'call': {'id': str(uuid4())}}
        self.assertEqual(self.reply(wrong).status_code, 404)
        with TestClient(app) as foreign:
            self.assertIn(foreign.get(f'/api/interviews/{self.interview_id}').status_code, (401, 404))
        self.assertEqual(len(self.snapshot()['turns']), 1)

    def test_end_event_is_idempotent_and_prevents_new_answers(self):
        payload = {'message': {'type': 'status-update', 'status': 'ended', 'call': {'id': self.call_id}}}
        for _ in range(2):
            result = self.client.post('/vapi/events', json=payload,
                headers={'Authorization': 'Bearer synthetic-provider-token'})
            self.assertEqual(result.status_code, 200)
        self.assertEqual(self.snapshot()['status'], 'ended')
        self.assertEqual(self.reply().status_code, 200)
        self.assertEqual(len(self.snapshot()['turns']), 1)
