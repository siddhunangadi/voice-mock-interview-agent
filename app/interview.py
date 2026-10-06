import re
from difflib import SequenceMatcher
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=1200)]
MAX_QUESTIONS = 18
MAX_DEPTH = 2
OPENING = 'Hi, welcome to your mock interview. We will start with your background, then discuss your experience and some role-related problems. To begin, tell me about yourself.'
CLOSING = 'Thank you. Your interview is complete. Your feedback will appear on screen.'


def stale_question(spoken: str, questions: list[str]) -> bool:
    words = re.findall(r'\w+', spoken.lower())
    if len(words) < 4 or len(questions) < 2:
        return False
    scores = [SequenceMatcher(None, words, re.findall(r'\w+', q.lower()), autojunk=False).ratio()
              for q in questions]
    # Only reject positive evidence of an older question; speech transcripts are not exact IDs.
    return max(scores[:-1]) >= .65 and max(scores[:-1]) > scores[-1] + .1


def requests_repeat(answer: str) -> bool:
    text = re.sub(r'[^a-z ]', '', answer.lower()).strip()
    return text in {'repeat', 'repeat please', 'please repeat', 'repeat the question',
                    'please repeat the question', 'can you repeat the question',
                    'could you repeat the question', 'say that again', 'please say that again'}


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Topic(Contract):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    evidence: Text
    project: bool = False
    priority: int = Field(ge=1, le=7)


class Context(Contract):
    skills: list[Text]
    projects: list[Text]
    experience: list[Text]
    education: list[Text]
    responsibilities: list[Text]
    required_skills: list[Text]
    preferred_skills: list[Text]
    overlaps: list[Text]
    gaps: list[Text]
    topics: list[Topic] = Field(min_length=2, max_length=7)
    first_question: Annotated[str, Field(min_length=10, max_length=500)]


class State(Contract):
    topic: int = Field(default=0, ge=0, le=6)
    depth: int = Field(default=0, ge=0, le=MAX_DEPTH)
    question_count: int = Field(default=1, ge=1, le=MAX_QUESTIONS)
    covered: list[int] = Field(default_factory=list)
    wrapping_up: bool = False
    stage: Literal["introduction", "motivation", "discussion"] = "discussion"


class Decision(Contract):
    answers_question: bool = True
    action: Literal['followup', 'advance', 'finish']
    topic: int = Field(ge=0, le=6)
    question: Annotated[str, Field(min_length=1, max_length=500)]
    assessment: Text
    evidence: Text
    score: int | None = Field(ge=0, le=4)


class TopicFeedback(Contract):
    topic: Text
    score: int | None = Field(ge=0, le=4)
    evidence: Text
    feedback: Text


class Evaluation(Contract):
    summary: Text
    overall_score: int | None = Field(ge=0, le=100)
    strengths: list[Text] = Field(max_length=6)
    improvements: list[Text] = Field(max_length=6)
    topics: list[TopicFeedback] = Field(min_length=2, max_length=7)
    recommendations: list[Text] = Field(max_length=6)


def plan_projects(context: Context) -> None:
    for topic in context.topics:
        topic.project = False
    if not context.experience and context.projects:
        projects = list(dict.fromkeys(context.projects))[:5]
        context.topics = [Topic(name=f'Project {i + 1}: {project.split(':', 1)[0][:100]}', evidence=project,
                               priority=i + 1, project=True) for i, project in enumerate(projects)] + context.topics[:2]


def allowed_topics(context: Context, state: State) -> list[int]:
    if state.stage != "discussion":
        return [0]
    if state.question_count >= MAX_QUESTIONS:
        return []
    remaining = len(context.topics) - state.topic - 1
    allowed = []
    if state.depth < MAX_DEPTH and MAX_QUESTIONS - state.question_count > remaining:
        allowed.append(state.topic)
    if remaining:
        allowed.append(state.topic + 1)
    return allowed


def repeated(question: str, previous: list[str]) -> bool:
    words = set(re.findall(r'\w+', question.lower()))
    # ponytail: lexical similarity misses semantic paraphrases; add semantic checks only if observed in interviews.
    return any(len(words & old) / max(1, len(words | old)) >= .8
               for old in (set(re.findall(r'\w+', q.lower())) for q in previous))


def choose_question(context: Context, state: State, decision: Decision,
                    previous: list[str]) -> tuple[str | None, State]:
    state = state.model_copy(deep=True)
    if state.stage != "discussion":
        if state.stage == "introduction":
            question = 'Thank you for introducing yourself. What interested you in this role?'
            state.stage = 'motivation'
        else:
            question = (f'Let us start with {context.topics[0].name}. Could you give me a high-level overview of what you built?'
                        if context.topics[0].project else
                        'Could you give me a high-level overview of one academic, personal, or work project relevant to this role?')
            state.stage = 'discussion'
        state.question_count += 1
        return question, state
    if not decision.answers_question and not state.wrapping_up and state.question_count < MAX_QUESTIONS:
        question = decision.question
        if decision.topic != state.topic or repeated(question, previous):
            question = 'Work experience is not required. Could you describe one academic or personal project you have worked on?'
        state.question_count += 1
        return question, state
    if state.topic not in state.covered:
        state.covered.append(state.topic)
    allowed = allowed_topics(context, state)
    if state.wrapping_up:
        return None, state
    if not allowed or (decision.action == 'finish' and state.topic == len(context.topics) - 1):
        state.wrapping_up = True
        return 'Before we finish, is there anything relevant to this role that you would like to add or clarify?', state
    topic = decision.topic
    valid = topic in allowed and decision.action == ('followup' if topic == state.topic else 'advance')
    question = decision.question
    if not valid or repeated(question, previous):
        topic = allowed[-1]
        name = context.topics[topic].name
        question = (f'Let us explore {name}. Can you describe a relevant example from your experience?'
                    if topic != state.topic else
                    f'What was your own contribution to the example you described about {name}?')
        if repeated(question, previous):
            question = f'What would you do differently next time regarding {name}?' 
    if topic != state.topic and context.topics[topic].project:
        question = f'Let us move to {context.topics[topic].name}. What problem were you trying to solve?'
    state.depth = state.depth + 1 if topic == state.topic else 0
    state.topic = topic
    state.question_count += 1
    return question, state
