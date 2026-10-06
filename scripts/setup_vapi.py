"""Create the saved Vapi assistant and its two authenticated server routes."""
import os
import secrets
from pathlib import Path

import httpx
from dotenv import load_dotenv, set_key

root = Path(__file__).resolve().parent.parent
load_dotenv(root / '.env')
settings = root / '.env'
private_key = os.getenv('VAPI_PRIVATE_KEY')
base_url = (os.getenv('PUBLIC_BASE_URL') or '').rstrip('/')
if not private_key or not base_url.startswith('https://'):
    raise SystemExit('Set VAPI_PRIVATE_KEY and an HTTPS PUBLIC_BASE_URL in .env first.')


def save(name, value):
    set_key(settings, name, value)
    os.environ[name] = value


def request(path, data, method="POST"):
    with httpx.Client(base_url='https://api.vapi.ai', timeout=20,
                      headers={'Authorization': f'Bearer {private_key}'}) as client:
        response = client.request(method, path, json=data)
        if response.is_error:
            raise SystemExit(f'Vapi setup failed at {path}: HTTP {response.status_code}. Check the Vapi dashboard logs.')
        return response.json()


token = os.getenv('VAPI_SERVER_TOKEN')
if not token:
    token = secrets.token_urlsafe(40)
    save('VAPI_SERVER_TOKEN', token)

model_credential = os.getenv('VAPI_MODEL_CREDENTIAL_ID')
if not model_credential:
    model_credential = request('/credential', {
        'provider': 'custom-llm', 'name': 'Mock Interview custom LLM', 'apiKey': token,
    })['id']
    save('VAPI_MODEL_CREDENTIAL_ID', model_credential)

webhook_credential = os.getenv('VAPI_WEBHOOK_CREDENTIAL_ID')
if not webhook_credential:
    webhook_credential = request('/credential', {
        'provider': 'custom-credential', 'name': 'Mock Interview webhook',
        'authenticationPlan': {'type': 'bearer', 'token': token,
                               'headerName': 'Authorization', 'bearerPrefixEnabled': True},
    })['id']
    save('VAPI_WEBHOOK_CREDENTIAL_ID', webhook_credential)

assistant_id = os.getenv('VAPI_ASSISTANT_ID')
assistant = request(f'/assistant/{assistant_id}' if assistant_id else '/assistant', {
        'name': 'Voice Mock Interview',
        'model': {'provider': 'custom-llm', 'model': 'interview-controller',
                  'url': f'{base_url}/vapi', 'metadataSendMode': 'variable',
                  'timeoutSeconds': 60, 'temperature': 0,
                  'messages': [{'role': 'system', 'content': 'Follow the interview controller responses.'}]},
        'credentialIds': [model_credential],
        'voice': {'provider': 'vapi', 'voiceId': 'Godfrey', 'version': 2},
        'transcriber': {'provider': 'deepgram', 'model': 'nova-3', 'language': 'en'},
        'startSpeakingPlan': {'waitSeconds': 0.3,
            'transcriptionEndpointingPlan': {'onPunctuationSeconds': 2.5,
                                            'onNoPunctuationSeconds': 3.0, 'onNumberSeconds': 2.5}},
        'stopSpeakingPlan': {'numWords': 0, 'voiceSeconds': 0.2, 'backoffSeconds': 1.5},
        'firstMessageMode': 'assistant-speaks-first',
        'server': {'url': f'{base_url}/vapi/events', 'credentialId': webhook_credential,
                   'headers': {'Authorization': f'Bearer {token}'}},
        'serverMessages': ['end-of-call-report', 'status-update'],
        'analysisPlan': {'summaryPlan': {'enabled': False},
                         'successEvaluationPlan': {'enabled': False},
                         'structuredDataPlan': {'enabled': False}},
        'artifactPlan': {'recordingEnabled': False},
        'endCallPhrases': ['Your interview is complete.'],
    }, method='PATCH' if assistant_id else 'POST')
save('VAPI_ASSISTANT_ID', assistant['id'])

print('Vapi credentials and saved assistant are configured. No secrets printed.')
