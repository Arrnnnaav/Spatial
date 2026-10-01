/* Dashboard view logic with no DOM access, so it can be unit-tested in Node. Activity is content-free (kind + time). */
(function (root) {
  'use strict';
  const ACTIVITY_KEY = 'spatial.activity';
  const MAX_ACTIVITY = 40;

  function readActivity(storage) {
    try {
      const list = JSON.parse(storage.load(ACTIVITY_KEY, '[]'));
      return Array.isArray(list) ? list.filter((e) => e && typeof e.kind === 'string' && typeof e.at === 'string') : [];
    } catch (_) { return []; }
  }

  function recordActivity(storage, kind, now) {
    const events = readActivity(storage);
    events.unshift({ at: (now || new Date()).toISOString(), kind: String(kind) });
    storage.save(ACTIVITY_KEY, JSON.stringify(events.slice(0, MAX_ACTIVITY)));
  }

  function statusCards(health, snoozed, issues) {
    const problem = issues || {};
    const audio = (health && health.audio) || {};
    const providers = (health && health.providers) || [];
    const stt = audio.stt && audio.stt.installed;
    const tts = audio.tts && audio.tts.installed && audio.tts.enabled;
    const voice = audio.backend === 'nvidia' ? 'NVIDIA' : audio.tts && audio.tts.voice === 'system' ? 'Windows voice' : 'local voice';
    return [
      ['Server', health ? 'Ready' : 'Needs attention'],
      ['Answer provider', providers.some((p) => p.configured) ? 'Configured' : 'Not configured'],
      ['Speech to text', stt ? 'Ready · ' + (audio.backend || 'local') : 'Needs attention'],
      ['Text to speech', tts ? 'Ready · ' + voice : 'Needs attention'],
      ['Ask shortcut', problem.ask ? 'Unavailable · see Settings' : snoozed ? 'Snoozed' : 'Alt+Shift+S enabled'],
      ['Dictation', problem.dictate ? 'Shortcut unavailable · use the Dictate button' : 'Alt+Shift+D · Dictate button'],
    ];
  }

  function historyCard(context) {
    const page = context.page || {};
    const turns = (context.answer && context.answer.history) || [];
    const latest = turns[turns.length - 1] || {};
    return {
      id: String(context.id),
      title: String(page.title || page.surface || 'Spatial Ask'),
      when: new Date(context.updated_at).toLocaleString() + ' · ' + (context.turns || 1) + ' turn(s)',
      question: String(latest.question || context.question || 'Saved question'),
    };
  }

  function dictationCard(entry) {
    const source = [entry.source_app, entry.source_title].filter(Boolean).join(' · ');
    return {
      id: String(entry.id),
      title: String(entry.title || 'Dictation'),
      summary: String(entry.summary || ''),
      when: new Date(entry.created_at).toLocaleString(),
      source,
      providers: [entry.stt_provider, entry.cleanup_provider].filter(Boolean).join(' · '),
    };
  }

  /* Reminder times are always sent as timezone-aware ISO strings (the server rejects naive times). */
  function quickDue(kind, now) {
    const base = now || new Date();
    if (kind === '10m') return new Date(base.getTime() + 10 * 60000).toISOString();
    if (kind === '1h') return new Date(base.getTime() + 3600000).toISOString();
    if (kind === 'tomorrow9') {
      const next = new Date(base.getFullYear(), base.getMonth(), base.getDate() + 1, 9, 0, 0);
      return next.toISOString();
    }
    throw new Error('unknown quick time: ' + kind);
  }

  function localInputToIso(value) {
    if (!value) return null;
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }

  function taskCard(task) {
    return { id: String(task.id), text: String(task.text), note: String(task.note || ''), done: Boolean(task.done) };
  }

  function reminderCard(reminder, now) {
    const due = new Date(reminder.due_at);
    const state = reminder.fired_at ? 'Done' : due.getTime() <= (now || new Date()).getTime() ? 'Overdue' : 'Upcoming';
    return { id: String(reminder.id), text: String(reminder.text), when: due.toLocaleString(), state };
  }

  root.SpatialDashboard = { ACTIVITY_KEY, MAX_ACTIVITY, readActivity, recordActivity, statusCards, historyCard, dictationCard, quickDue, localInputToIso, taskCard, reminderCard };
  if (typeof module !== 'undefined') module.exports = root.SpatialDashboard;
})(typeof window === 'undefined' ? globalThis : window);
