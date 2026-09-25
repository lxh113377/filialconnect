/* Full-text search panel for the tutorial library.
 *
 * Sits alongside the existing filter in main.js rather than replacing it: that filter narrows
 * the six cards by topic and substring, this one searches the whole site body. The two answer
 * different questions, and the substring filter is also the fallback here.
 *
 * The index is two single-language builds (pagefind/en from the real pages, pagefind/zh from a
 * generated corpus) because this Pagefind build exposes no setLanguage. A Chinese reader gets
 * nothing from the English-only index, which is the reason the corpus exists at all.
 */
(function () {
  'use strict';

  var MIN_CHARS = 2;
  var MAX_RESULTS = 5;
  var loaded = null;   // { lang, api } once an index has been imported
  var timer = null;
  var seq = 0;
  // Latched the first time an index cannot be loaded, so a browser that refuses file:// fetches
  // (a reader double-clicking the offline ZIP) stops retrying on every keystroke. Guessing this
  // from the protocol string was tried and dropped: the local harness runs Chrome with file access
  // enabled, where file:// fetch *succeeds*, so a protocol check would switch the feature off for
  // readers it works for. Failing once and remembering is correct in either browser.
  var degraded = false;

  function rootUrl() {
    // Pages live one level below the site root, which is also true under file://.
    return new URL('../', window.location.href);
  }

  function panel() { return document.getElementById('fulltext-results'); }
  function listEl() { return document.getElementById('fulltext-list'); }
  function statusEl() { return document.getElementById('fulltext-status'); }

  function lang() {
    return (document.documentElement.lang || '').toLowerCase().indexOf('zh') === 0 ? 'zh' : 'en';
  }

  function loadIndex(want) {
    if (loaded && loaded.lang === want) return Promise.resolve(loaded.api);
    var base = rootUrl().href + 'pagefind/' + want + '/';
    return import(base + 'pagefind.js').then(function (api) {
      return api.init({ baseUrl: base }).then(function () {
        loaded = { lang: want, api: api };
        return api;
      });
    });
  }

  function hrefFor(link, fallback) {
    var target = link || fallback || '';
    if (!target) return null;
    if (/^https?:/.test(target) || target.charAt(0) === '#') return target;
    // Corpus metadata is site-relative; the panel renders from a page in pages/.
    return target.indexOf('pages/') === 0 || target.indexOf('assets/') === 0
      ? '../' + target
      : target;
  }

  function render(results) {
    var list = listEl();
    var status = statusEl();
    var box = panel();
    if (!list || !box) return;
    list.textContent = '';
    if (!results.length) {
      box.hidden = true;
      if (status) status.textContent = '';
      return;
    }
    results.forEach(function (r) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      var link = null;
      // meta.link points at the real page plus the step anchor; url is the corpus page,
      // which must never be offered to a visitor.
      var pending = r.data().then(function (d) {
        link = hrefFor(d.meta && d.meta.link, d.url);
        a.textContent = String((d.meta && d.meta.title) || d.url || '');
        if (!a.textContent) a.textContent = String(d.url || '');
        if (link) a.setAttribute('href', link);
        if (!link) a.removeAttribute('href');
        return d;
      });
      li.appendChild(a);
      list.appendChild(li);
      return pending;
    });
    box.hidden = false;
    if (status) status.textContent = String(results.length);
  }

  function clear() {
    var box = panel();
    var list = listEl();
    var status = statusEl();
    if (list) list.textContent = '';
    if (status) status.textContent = '';
    if (box) box.hidden = true;
  }

  function run(api, term, ticket) {
    return api.search(term).then(function (res) {
      if (ticket !== seq) return;            // a newer keystroke already superseded this one
      var results = (res && res.results ? res.results : []).slice(0, MAX_RESULTS);
      if (!results.length) { clear(); return; }
      render(results);
    });
  }

  function onInput(input) {
    var term = (input.value || '').trim();
    if (degraded || term.length < MIN_CHARS) { clear(); return; }
    var want = lang();
    var ticket = ++seq;
    if (loaded && loaded.lang !== want) {
      // Index selection follows the UI language, so reload it and retry this term once.
      loaded = null;
    }
    loadIndex(want).then(function (api) {
      if (ticket !== seq) return;
      return run(api, term, ticket);
    })['catch'](function () {
      // A missing index, a blocked dynamic import, or a browser that refuses file:// fetches
      // (the offline ZIP). Latch it: the substring filter in main.js still works, so the box
      // stays closed and no further keystroke re-attempts a load that already failed.
      degraded = true;
      var box = panel();
      if (box) box.setAttribute('data-fulltext', 'unavailable');
      if (ticket === seq) clear();
    });
  }

  function init() {
    var input = document.getElementById('tutorial-search-input');
    var box = panel();
    if (!input || !box) return;
    box.hidden = true;
    // Observable, not just implied: a test can read this instead of inferring from the panel
    // staying closed, which is how the last round ended up unverifiable. Starts optimistically
    // and latches to 'unavailable' the first time an index load fails.
    box.setAttribute('data-fulltext', 'ready');
    input.addEventListener('input', function () {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(function () { onInput(input); }, 250);
    });
    input.addEventListener('search', function () { onInput(input); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
