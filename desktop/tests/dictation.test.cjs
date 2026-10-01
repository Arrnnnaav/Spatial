const test = require('node:test');
const assert = require('node:assert/strict');
const { clean, format } = require('../ui/dictation.js');

test('dictation cleanup handles voice punctuation, filler and local dictionary', () => {
  assert.equal(
    clean('um I, I think call Sam period new paragraph uh tomorrow question mark', 'Sam|Samantha'),
    'I think call Samantha.\n\ntomorrow?',
  );
});

test('dictation cleanup leaves ordinary text alone', () => {
  assert.equal(clean('Please send the draft today.', ''), 'Please send the draft today.');
});

test('dictation turns an explicit todo list with spoken ordinals into editable bullets', () => {
  assert.equal(
    format('create a todo list first submit the form then second review the answers', ''),
    'To-do list:\n- submit the form\n- review the answers',
  );
});

test('dictation formats counted enumerations and spoken paragraph commands', () => {
  assert.equal(
    format('three things: speed, accuracy and clarity new paragraph done', ''),
    'Three things:\n1. speed\n2. accuracy\n3. clarity\n\ndone',
  );
});

test('dictation removes an explicit scratch-that restart and applies dictionary after cleanup', () => {
  assert.equal(
    format('we will meet Monday scratch that Tuesday period', 'Spay-shull|Spatial'),
    'we will meet Tuesday.',
  );
});

test('protected targets are never saved to the dictation log', () => {
  const { shouldSaveEntry } = require('../ui/dictation.js');
  assert.equal(shouldSaveEntry(true, ''), true);
  assert.equal(shouldSaveEntry(false, 'focus_changed'), true);
  assert.equal(shouldSaveEntry(false, ''), true);
  for (const reason of ['protected_window', 'protected_field', 'unsupported_field', 'unsupported']) {
    assert.equal(shouldSaveEntry(false, reason), false, reason);
  }
});
