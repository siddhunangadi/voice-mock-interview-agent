const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
const handlers = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {hidden: false, textContent: '', addEventListener(event, handler){ handlers.set(`${id}:${event}`, handler); }, replaceChildren(){}});
  return elements.get(id);
};
const context = vm.createContext({
  document: {getElementById: element, createElement: () => ({append(){}})},
  localStorage: {getItem: () => null}, setInterval(){},
});
vm.runInContext(readFileSync('frontend/app.js','utf8').replace(/^import .*;\n/,''),context);
vm.runInContext(`
voice = {};
voiceState = 'Interviewer speaking';
$('question').textContent = 'Currently spoken question';
error('Audio failed');
render({status:'active', state:{question_count:2,topic:0}, context:{topics:[{name:'Project'}]}, turns:[{role:'assistant', content:'Next saved question'}]});
`,context);
assert.equal(element('question').textContent,'Currently spoken question');
vm.runInContext(`questionRevealPending = true; render({status:'active', state:{question_count:2,topic:0}, context:{topics:[{name:'Project'}]}, turns:[{role:'assistant',content:'Next saved question'}]});`,context);
assert.equal(element('question').textContent,'Next saved question');
assert.equal(element('progress').textContent,'Discussion · Project');
assert.equal(element('status').textContent,'Interviewer speaking');
assert.equal(element('error').hidden,false);
console.log('Frontend polling updates full question and progress, preserves, voice status and errors.');
vm.runInContext(`
(async () => {
  interviewId = 'test';
  const pending = [];
  api = () => new Promise(resolve => pending.push(resolve));
  let rendered;
  render = data => { rendered = data; };
  const old = refresh(), latest = refresh();
  pending[1]('new'); await latest;
  pending[0]('old'); await old;
  if (rendered !== 'new') throw Error('Stale refresh replaced latest question');
})()
`, context).then(() => console.log('Out-of-order refresh cannot replace the latest question.'), error => { console.error(error); process.exitCode = 1; });

(async () => {
  // Wait for the independent refresh regression before replacing its API stub.
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext("api = async () => ({text: 'Extracted candidate resume text ready for review.'})", context);
  element('resume-file').files = [{name:'candidate.docx',size:100}];
  await handlers.get('resume-file:change')();
  assert.equal(element('resume').value,'Extracted candidate resume text ready for review.');
  assert.equal(element('prepare').disabled,false);
  vm.runInContext("api = async () => { throw Error('Unreadable document'); }", context);
  await handlers.get('resume-file:change')();
  assert.equal(element('resume').value,'Extracted candidate resume text ready for review.');
  assert.equal(element('resume').readOnly,false);
  assert.equal(element('error').textContent,'Unreadable document');
  console.log('Upload fills editable resume text; failed extraction preserves previous text and unlocks form.');
})().catch(error => {console.error(error); process.exitCode=1;});
