const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('../ui/dashboard-model.js');

const memory = () => { const m = {}; return { load: (k, f) => (k in m ? m[k] : f), save: (k, v) => { if (v) m[k] = v; else delete m[k]; } }; };

test('activity keeps newest first, caps at 40 and stores kinds only', () => {
  const s = memory();
  for (let i = 0; i < 45; i++) D.recordActivity(s, 'event ' + i, new Date(2026, 9, 1, 0, i));
  const list = D.readActivity(s);
  assert.equal(list.length, 40);
  assert.equal(list[0].kind, 'event 44');
  assert.deepEqual(Object.keys(list[0]).sort(), ['at', 'kind']);
});

test('corrupt activity storage reads as empty and recovers', () => {
  const s = memory(); s.save(D.ACTIVITY_KEY, '{not json');
  assert.deepEqual(D.readActivity(s), []);
  D.recordActivity(s, 'ok');
  assert.equal(D.readActivity(s)[0].kind, 'ok');
});

test('status cards say Needs attention when the server is down', () => {
  const cards = Object.fromEntries(D.statusCards(null, false));
  assert.equal(cards['Server'], 'Needs attention');
  assert.equal(cards['Answer provider'], 'Not configured');
  assert.equal(cards['Speech to text'], 'Needs attention');
});

test('status cards reflect a healthy server and snooze', () => {
  const health = { providers: [{ configured: true }], audio: { backend: 'local', stt: { installed: true }, tts: { installed: true, enabled: true, voice: 'system' } } };
  const cards = Object.fromEntries(D.statusCards(health, true));
  assert.equal(cards['Server'], 'Ready');
  assert.equal(cards['Answer provider'], 'Configured');
  assert.equal(cards['Speech to text'], 'Ready · local');
  assert.equal(cards['Text to speech'], 'Ready · Windows voice');
  assert.equal(cards['Ask shortcut'], 'Snoozed');
});

test('history card falls back gracefully and keeps hostile text as plain strings', () => {
  const card = D.historyCard({ id: 'a', updated_at: '2026-10-01T10:00:00+00:00', question: 'q', page: { title: '<img src=x onerror=alert(1)>' }, answer: { history: [{ question: 'last?' }] }, turns: 2 });
  assert.equal(card.title, '<img src=x onerror=alert(1)>');
  assert.equal(card.question, 'last?');
  assert.equal(typeof card.when, 'string');
  assert.equal(D.historyCard({ id: 'b', updated_at: '2026-10-01T10:00:00+00:00', page: {}, answer: {} }).title, 'Spatial Ask');
});

test('dictation card keeps hostile text as plain strings and omits unknown source', () => {
  const card = D.dictationCard({ id: 'd1', created_at: '2026-10-01T10:00:00+00:00', title: '<b>x</b>', summary: 's', text: 't', source_app: '', source_title: '', stt_provider: 'local', cleanup_provider: 'local cleanup' });
  assert.equal(card.title, '<b>x</b>');
  assert.equal(card.source, '');
  assert.equal(card.providers, 'local · local cleanup');
  const known = D.dictationCard({ id: 'd2', created_at: '2026-10-01T10:00:00+00:00', title: 't', summary: '', text: 'x', source_app: 'Notepad', source_title: 'notes.txt', stt_provider: '', cleanup_provider: '' });
  assert.equal(known.source, 'Notepad · notes.txt');
  assert.equal(known.providers, '');
});

test('status cards report a shortcut another app already owns', () => {
  const cards = Object.fromEntries(D.statusCards(null, false, { ask: true, dictate: true }));
  assert.equal(cards['Ask shortcut'], 'Unavailable · see Settings');
  assert.equal(cards['Dictation'], 'Shortcut unavailable · use the Dictate button');
  const fine = Object.fromEntries(D.statusCards(null, false, {}));
  assert.equal(fine['Ask shortcut'], 'Alt+Shift+S enabled');
});

test('quick reminder times are timezone-aware ISO strings in the future', () => {
  const now = new Date(2026, 9, 1, 15, 30, 0);
  assert.equal(new Date(D.quickDue('10m', now)).getTime() - now.getTime(), 10 * 60000);
  assert.equal(new Date(D.quickDue('1h', now)).getTime() - now.getTime(), 3600000);
  const tomorrow = new Date(D.quickDue('tomorrow9', now));
  assert.equal(tomorrow.getDate(), 2);
  assert.equal(tomorrow.getHours(), 9);
  assert.match(D.quickDue('10m', now), /Z$|[+-]\d\d:\d\d$/);
  assert.throws(() => D.quickDue('nope', now));
});

test('local datetime input converts to a zoned ISO string and rejects garbage', () => {
  assert.match(D.localInputToIso('2026-10-01T18:45'), /Z$/);
  assert.equal(D.localInputToIso(''), null);
  assert.equal(D.localInputToIso('not a date'), null);
});

test('reminder and task cards keep text plain and label state', () => {
  const now = new Date('2026-10-01T10:00:00Z');
  const up = D.reminderCard({ id: 'r', text: '<b>Call</b>', due_at: '2026-10-01T11:00:00+00:00', fired_at: null }, now);
  assert.equal(up.text, '<b>Call</b>'); assert.equal(up.state, 'Upcoming');
  assert.equal(D.reminderCard({ id: 'r', text: 'x', due_at: '2026-10-01T09:00:00+00:00', fired_at: null }, now).state, 'Overdue');
  assert.equal(D.reminderCard({ id: 'r', text: 'x', due_at: '2026-10-01T09:00:00+00:00', fired_at: '2026-10-01T09:00:05+00:00' }, now).state, 'Done');
  assert.deepEqual(D.taskCard({ id: 't', text: 'Milk', note: 'n', done: true }), { id: 't', text: 'Milk', note: 'n', done: true });
});
