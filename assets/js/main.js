/**
 * FilialConnect (XiaoXinLian) — Main JavaScript
 * Navigation, interactions, animations, i18n, and accessibility
 */
(function () {
  'use strict';

  /* ============================================================
     DOM Ready
     ============================================================ */
  function ready(fn) {
    if (document.readyState !== 'loading') {
      fn();
    } else {
      document.addEventListener('DOMContentLoaded', fn);
    }
  }

  ready(function () {
    initI18n();
    initMobileNav();
    initActiveNav();
    initScrollAnimations();
    initBackToTop();
    initFraudAccordion();
    initTutorialFilter();
    initCallHelp();
    initHelpForm();
    initFamilyForm();
    initRemoteCode();
    initLinkCheck();
    initSmoothScroll();
    initFontScale();
    initReadAloud();
  });

  /* ============================================================
     Reading aids — font scale (适老化放大设置) and text-to-speech
     ============================================================ */
  var FONTSIZE_KEY = 'filialconnect-fontscale';
  var FONT_LEVELS = ['base', 'lg', 'xl'];

  function currentFontScale() {
    var v = storageGet(FONTSIZE_KEY);
    return FONT_LEVELS.indexOf(v) !== -1 ? v : 'base';
  }

  function applyFontScale(level) {
    var root = document.documentElement;
    if (level === 'base') root.removeAttribute('data-fontscale');
    else root.setAttribute('data-fontscale', level);
  }

  function initFontScale() {
    var btns = document.querySelectorAll('.font-btn');
    if (btns.length === 0) return;

    function paint(level) {
      btns.forEach(function (b) {
        b.setAttribute('aria-pressed', b.getAttribute('data-fontscale') === level ? 'true' : 'false');
      });
    }

    applyFontScale(currentFontScale());
    paint(currentFontScale());

    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        var level = b.getAttribute('data-fontscale');
        storageSet(FONTSIZE_KEY, level);
        applyFontScale(level);
        paint(level);
        if (window.speechSynthesis) window.speechSynthesis.cancel();
      });
    });
  }

  function initReadAloud() {
    var btn = document.querySelector('.read-btn');
    if (!btn) return;
    if (!('speechSynthesis' in window)) {
      btn.hidden = true;
      return;
    }

    var speaking = false;

    function t(key) {
      var lang = getCurrentLang();
      return (typeof I18N !== 'undefined' && I18N[lang] && I18N[lang][key]) ? I18N[lang][key] : key;
    }

    function stop() {
      speaking = false;
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = t('read.btn');
    }

    btn.addEventListener('click', function () {
      if (speaking) {
        window.speechSynthesis.cancel();
        stop();
        return;
      }
      var main = document.getElementById('main-content');
      if (!main) return;
      var parts = [];
      main.querySelectorAll('h1, h2, h3, p, li').forEach(function (el) {
        if (el.closest('.nav-links, .footer-links, script, style')) return;
        var txt = el.textContent.trim();
        if (txt) parts.push(txt);
      });
      if (parts.length === 0) return;
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(parts.join('. '));
      u.lang = getCurrentLang() === 'zh' ? 'zh-CN' : 'en-US';
      u.rate = 0.9;
      u.onend = stop;
      u.onerror = stop;
      speaking = true;
      btn.setAttribute('aria-pressed', 'true');
      btn.textContent = t('read.stop');
      window.speechSynthesis.speak(u);
    });

    window.addEventListener('pagehide', function () { window.speechSynthesis.cancel(); });

    readBtnRef = btn;
  }

  var readBtnRef = null;

  // Keep the JS-owned label in sync when the language changes mid-session.
  function refreshReadBtn() {
    if (!readBtnRef || readBtnRef.getAttribute('aria-pressed') === 'true') return;
    readBtnRef.textContent = t('read.btn');
  }

  /* ============================================================
     i18n — Language Toggle (EN / ZH)
     ============================================================ */
  var LANG_KEY = 'filialconnect-lang';
  var SUPPORTED_LANGS = ['en', 'zh'];

  // Browsers in private mode may throw on any localStorage access; language
  // choice then degrades to per-session detection instead of breaking initI18n.
  function storageGet(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }

  function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ }
  }

  function detectBrowserLang() {
    var nav = (navigator.languages && navigator.languages[0]) ||
              navigator.language || navigator.userLanguage || 'en';
    return String(nav).toLowerCase().indexOf('zh') === 0 ? 'zh' : 'en';
  }

  function getCurrentLang() {
    var stored = storageGet(LANG_KEY);
    if (stored && SUPPORTED_LANGS.indexOf(stored) !== -1) {
      return stored;
    }
    // No explicit choice yet: follow the browser language
    return detectBrowserLang();
  }

  function applyTranslations(lang) {
    if (typeof I18N === 'undefined' || !I18N[lang]) return;

    var dict = I18N[lang];

    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      if (dict[key] !== undefined) {
        var val = dict[key];
        if (val.indexOf('<br>') !== -1) {
          // Safe line-break rendering: only literal <br> is honored,
          // everything else is inserted as text (no HTML injection).
          el.textContent = '';
          val.split('<br>').forEach(function (part, i) {
            if (i > 0) el.appendChild(document.createElement('br'));
            el.appendChild(document.createTextNode(part));
          });
        } else {
          el.textContent = val;
        }
      }
    });

    [['placeholder', 'data-i18n-placeholder'],
     ['aria-label', 'data-i18n-aria-label'],
     ['alt', 'data-i18n-alt']].forEach(function (pair) {
      var attr = pair[0], marker = pair[1];
      document.querySelectorAll('[' + marker + ']').forEach(function (el) {
        var key = el.getAttribute(marker);
        if (dict[key] !== undefined) {
          el.setAttribute(attr, dict[key]);
        }
      });
    });

    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';

    var toggleBtn = document.querySelector('.lang-toggle');
    if (toggleBtn) {
      toggleBtn.querySelector('.lang-toggle-label').textContent = lang === 'en' ? 'ZH' : 'EN';
      toggleBtn.setAttribute('aria-label', lang === 'en' ? t('lang.to.zh') : t('lang.to.en'));
    }
  }

  function initI18n() {
    var lang = getCurrentLang();
    applyTranslations(lang);

    var toggleBtn = document.querySelector('.lang-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', function () {
        var currentLang = getCurrentLang();
        var newLang = currentLang === 'en' ? 'zh' : 'en';
        storageSet(LANG_KEY, newLang);
        applyTranslations(newLang);
        updateCallHint();
        refreshReadBtn();
      });
    }
  }

  /* ============================================================
     Mobile Navigation Toggle
     ============================================================ */
  function initMobileNav() {
    var toggle = document.querySelector('.nav-toggle');
    var links = document.querySelector('.nav-links');

    if (!toggle || !links) return;

    toggle.addEventListener('click', function () {
      var isOpen = links.classList.toggle('open');
      toggle.classList.toggle('open');
      toggle.setAttribute('aria-expanded', isOpen);
      document.body.style.overflow = isOpen ? 'hidden' : '';
    });

    links.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        links.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
      });
    });

    document.addEventListener('keydown', function (e) {
      if (!links.classList.contains('open')) return;

      if (e.key === 'Escape') {
        links.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
        toggle.focus();
        return;
      }

      if (e.key === 'Tab') {
        // Keep Tab cycling inside the open menu so focus never escapes behind it
        var focusables = [toggle].concat(Array.prototype.slice.call(links.querySelectorAll('a')));
        var first = focusables[0];
        var last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });
  }

  /* ============================================================
     Active Navigation State
     ============================================================ */
  function initActiveNav() {
    var currentPath = window.location.pathname;
    var isTutorialDetail = /\/tutorial-.+\.html$/.test(currentPath);
    var navLinks = document.querySelectorAll('.nav-links a');

    navLinks.forEach(function (link) {
      var href = link.getAttribute('href');
      if (!href) return;

      if (currentPath.endsWith(href) ||
          (href === 'index.html' && (currentPath.endsWith('/') || currentPath.endsWith('index.html'))) ||
          (href === 'tutorials.html' && isTutorialDetail)) {
        link.classList.add('active');
      }
    });
  }

  /* ============================================================
     Scroll-Triggered Animations
     ============================================================ */
  function initScrollAnimations() {
    var animatedElements = document.querySelectorAll('.animate-in, .stagger-children');

    if (animatedElements.length === 0) return;

    if ('IntersectionObserver' in window) {
      // rootMargin -15% bottom reproduces the old "top < 85% viewport" trigger
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
          }
        });
      }, { rootMargin: '0px 0px -15% 0px' });

      animatedElements.forEach(function (el) {
        // Elements already inside the viewport at load never fire an
        // intersection change under the negative bottom margin on tall
        // viewports; reveal them directly.
        var rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight && rect.bottom > 0) {
          el.classList.add('visible');
        } else {
          observer.observe(el);
        }
      });
      return;
    }

    // Fallback: reveal everything immediately
    animatedElements.forEach(function (el) { el.classList.add('visible'); });
  }

  /* ============================================================
     Motion preference — smooth scrolling must yield to it
     ============================================================ */
  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function scrollToEl(el, block) {
    if (!el || !el.scrollIntoView) return;
    el.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: block || 'start' });
  }

  /* ============================================================
     Back to Top Button
     ============================================================ */
  function initBackToTop() {
    var btn = document.querySelector('.back-to-top');
    if (!btn) return;

    var ticking = false;

    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(function () {
          if (window.scrollY > 400) {
            btn.classList.add('visible');
          } else {
            btn.classList.remove('visible');
          }
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });

    btn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
    });
  }

  /* ============================================================
     Fraud Database Accordion
     ============================================================ */
  function initFraudAccordion() {
    var items = document.querySelectorAll('.fraud-item');
    if (items.length === 0) return;

    items.forEach(function (item) {
      var summary = item.querySelector('.fraud-summary');
      if (!summary) return;

      summary.addEventListener('click', function () {
        var isOpen = item.classList.contains('open');
        items.forEach(function (other) {
          other.classList.remove('open');
          var otherSummary = other.querySelector('.fraud-summary');
          if (otherSummary) otherSummary.setAttribute('aria-expanded', 'false');
        });
        if (!isOpen) {
          item.classList.add('open');
          summary.setAttribute('aria-expanded', 'true');
        }
      });

      summary.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          summary.click();
        }
      });
    });
  }

  /* ============================================================
     Tutorial library — topic filter + text search share one state
     ============================================================ */
  function initTutorialFilter() {
    var filterTags = document.querySelectorAll('.filter-tag');
    var tutorialCards = document.querySelectorAll('.tutorial-card');

    if (filterTags.length === 0 || tutorialCards.length === 0) return;

    var searchInput = document.getElementById('tutorial-search-input');
    var live = document.querySelector('.filter-status');
    var category = 'all';

    function apply() {
      var q = ((searchInput && searchInput.value) || '').trim().toLowerCase();
      var shown = 0;

      tutorialCards.forEach(function (card) {
        var hitCat = category === 'all' || card.getAttribute('data-category') === category;
        var hitText = !q || card.textContent.toLowerCase().indexOf(q) !== -1;
        var show = hitCat && hitText;
        card.style.display = show ? '' : 'none';
        if (show) shown += 1;
      });

      if (live) {
        live.textContent = shown === 0
          ? t('search.none').replace('{q}', q || t('search.allword'))
          : (shown === 1 ? t('filter.count.one') : t('filter.count').replace('{n}', String(shown)));
      }
    }

    filterTags.forEach(function (tag) {
      tag.addEventListener('click', function () {
        filterTags.forEach(function (t0) {
          t0.classList.remove('active');
          t0.setAttribute('aria-pressed', 'false');
        });
        tag.classList.add('active');
        tag.setAttribute('aria-pressed', 'true');
        category = tag.getAttribute('data-filter');
        apply();
      });
    });

    if (searchInput) {
      var timer = null;
      searchInput.addEventListener('input', function () {
        // Debounced so a slow typist never triggers a reflow per keystroke
        window.clearTimeout(timer);
        timer = window.setTimeout(apply, 200);
      });
      searchInput.addEventListener('search', apply);
    }
  }

  /* ============================================================
     Family contact (stored on this device only) — the help tools below
     hand off to the phone's own dialer / SMS / mail app. Nothing is sent
     to any server, and no message leaves the device until the user presses
     send in their own app.
     ============================================================ */
  var FAMILY_KEY = 'filialconnect-family';

  function getFamily() {
    var raw = storageGet(FAMILY_KEY);
    if (!raw) return {};
    try { return JSON.parse(raw) || {}; } catch (e) { return {}; }
  }

  function digitsOnly(v) {
    return String(v || '').replace(/[^\d+]/g, '');
  }

  function t(key) {
    var lang = getCurrentLang();
    return (typeof I18N !== 'undefined' && I18N[lang] && I18N[lang][key]) ? I18N[lang][key] : key;
  }

  function initFamilyForm() {
    var form = document.getElementById('family-form');
    if (!form) return;
    var nameEl = document.getElementById('family-name');
    var phoneEl = document.getElementById('family-phone');
    var mailEl = document.getElementById('family-email');
    var f = getFamily();
    if (nameEl) nameEl.value = f.name || '';
    if (phoneEl) phoneEl.value = f.phone || '';
    if (mailEl) mailEl.value = f.email || '';

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var data = {
        name: (nameEl && nameEl.value || '').trim().slice(0, 40),
        phone: digitsOnly(phoneEl && phoneEl.value).slice(0, 20),
        email: (mailEl && mailEl.value || '').trim().slice(0, 120)
      };
      if (!data.phone && !data.email) {
        showToast(t('family.need'), 'error');
        return;
      }
      storageSet(FAMILY_KEY, JSON.stringify(data));
      showToast(t('family.saved'), 'success');
      updateCallHint();
    });
  }

  function updateCallHint() {
    var hint = document.querySelector('.family-state');
    if (!hint) return;
    var f = getFamily();
    var who = f.name || t('family.unnamed');
    if (f.phone || f.email) {
      hint.textContent = t('family.ready').replace('{name}', who);
    } else {
      hint.textContent = t('family.notset');
    }
  }

  /* ============================================================
     Help Request Form -> SMS / mail draft hand-off (no server)
     ============================================================ */
  function initHelpForm() {
    var form = document.getElementById('help-request-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var f = getFamily();
      var topicSel = form.querySelector('select');
      var msgEl = form.querySelector('textarea');
      var urgSel = document.getElementById('help-urgency');
      var topic = topicSel && topicSel.selectedIndex > 0 ? topicSel.options[topicSel.selectedIndex].text : '';
      var urg = urgSel && urgSel.selectedIndex >= 0 ? urgSel.options[urgSel.selectedIndex].text : '';
      var body = [t('form.tag'), topic ? '[' + topic + ']' : '', urg,
                  (msgEl && msgEl.value || '').trim()].filter(Boolean).join('\n');

      var phone = digitsOnly(f.phone);
      var href = null;
      if (phone) href = 'sms:' + phone + '?&body=' + encodeURIComponent(body);
      else if (f.email) href = 'mailto:' + f.email + '?subject=' + encodeURIComponent(t('form.subject')) + '&body=' + encodeURIComponent(body);

      if (!href) {
        showToast(t('family.need'), 'error');
        var settings = document.getElementById('family-form');
        if (settings) scrollToEl(settings, 'center');
        return;
      }
      window.location.href = href;
      showToast(t('toast.draft-opened'), 'success');
    });
  }

  /* ============================================================
     Call Help — real dial through the device phone app
     ============================================================ */
  function initCallHelp() {
    var callBtn = document.querySelector('.call-button');
    var statusEl = document.querySelector('.call-status');
    if (!callBtn || !statusEl) return;

    updateCallHint();

    callBtn.addEventListener('click', function () {
      var f = getFamily();
      var phone = digitsOnly(f.phone);
      var line = statusEl.querySelector('.call-status-line');
      if (!phone) {
        if (line) line.textContent = t('call.nofamily');
        statusEl.classList.add('visible', 'is-warn');
        var form = document.getElementById('family-form');
        if (form) scrollToEl(form, 'center');
        return;
      }
      if (line) {
        line.textContent = t('call.dialing').replace('{name}', f.name || t('family.unnamed')).replace('{phone}', phone);
      }
      statusEl.classList.add('visible');
      statusEl.classList.remove('is-warn');
      window.location.href = 'tel:' + phone;
    });
  }

  /* ============================================================
     Suspicious Link Self-Check (offline destroylist data)
     ============================================================ */
  function initLinkCheck() {
    var input = document.getElementById('link-check-input');
    var btn = document.getElementById('link-check-btn');
    var out = document.getElementById('link-check-result');
    if (!input || !btn || !out) return;

    function t(key) {
      var lang = getCurrentLang();
      return (typeof I18N !== 'undefined' && I18N[lang] && I18N[lang][key]) ? I18N[lang][key] : key;
    }

    var set = null;
    var loading = null;

    // silent = background pre-warm: never touches the live status region
    function loadDomains(cb, silent) {
      if (set) { cb(set); return; }
      if (loading) { loading.push(cb); return; }
      loading = [cb];
      if (!silent) out.textContent = t('linkcheck.loading');
      fetch('../assets/data/destroylist-domains.txt')
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.text(); })
        .then(function (txt) {
          set = new Set(txt.split(/\r?\n/).filter(Boolean));
          var wait = loading; loading = null;
          wait.forEach(function (fn) { fn(set); });
        })
        .catch(function () {
          loading = null;
          if (!silent) {
            out.textContent = t('linkcheck.errload');
            out.className = 'link-check-result is-unknown';
          }
        });
    }

    // The list is 532 KB gzipped; fetching it while the visitor reads the page
    // removes the wait from the moment they actually press 检查.
    function prewarm() {
      var conn = navigator.connection || {};
      if (conn.saveData || /2g/.test(conn.effectiveType || '')) return;
      loadDomains(function () {}, true);
    }

    if (window.requestIdleCallback) window.requestIdleCallback(prewarm, { timeout: 4000 });
    else window.setTimeout(prewarm, 1500);

    function hostOf(raw) {
      var m = raw.match(/^(?:https?|ftp):\/\/(?:[^@/]*@)?([^/?#:]+)/i) || raw.match(/^([a-z0-9][a-z0-9.-]*\.[a-z]{2,})(?:[/:?#]|$)/i);
      return m ? m[1].toLowerCase() : null;
    }

    function check() {
      loadDomains(function (s) {
        var raw = input.value.trim().toLowerCase();
        var host = hostOf(raw);
        if (!host) {
          out.textContent = t('linkcheck.parse');
          out.className = 'link-check-result is-unknown';
          return;
        }
        var parts = host.split('.');
        var root = parts.length > 2 ? parts.slice(-2).join('.') : host;
        var bad = s.has(host) || s.has(root) || s.has(raw);
        out.textContent = bad ? t('linkcheck.bad') : t('linkcheck.ok');
        out.className = 'link-check-result ' + (bad ? 'is-bad' : 'is-ok');
      });
    }

    btn.addEventListener('click', check);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        check();
      }
    });
  }

  /* ============================================================
     Toast Notifications
     ============================================================ */
  function showToast(message, type) {
    var existingToast = document.querySelector('.toast');
    if (existingToast) {
      existingToast.remove();
    }

    var toast = document.createElement('div');
    toast.className = 'toast ' + (type === 'error' ? 'toast-error' : '');
    toast.setAttribute('role', 'alert');
    var toastSpan = document.createElement('span');
    toastSpan.textContent = message;
    toast.appendChild(toastSpan);
    document.body.appendChild(toast);

    requestAnimationFrame(function () {
      toast.classList.add('visible');
    });

    setTimeout(function () {
      toast.classList.remove('visible');
      setTimeout(function () {
        toast.remove();
      }, 300);
    }, 4000);
  }

  /* ============================================================
     Remote Assist Session Code (per-visit generation; static HTML value
     is the no-JS fallback) — print buttons stay inline onclick by design
     ============================================================ */
  function initRemoteCode() {
    var codeEl = document.querySelector('.connection-code');
    if (!codeEl) return;

    var chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no confusable I/O/0/1
    var code = '';
    for (var i = 0; i < 6; i++) {
      code += chars.charAt(Math.floor(Math.random() * chars.length));
      if (i === 2) code += ' ';
    }
    codeEl.textContent = code;
    codeEl.setAttribute('aria-label', t('remote.code.aria').replace('{code}', code));
  }

  /* ============================================================
     Smooth Scroll for Anchor Links
     ============================================================ */
  function initSmoothScroll() {
    document.addEventListener('click', function (e) {
      var link = e.target.closest('a[href^="#"]');
      if (!link) return;

      var targetId = link.getAttribute('href').substring(1);
      if (!targetId) return;

      var target = document.getElementById(targetId);
      if (!target) return;

      e.preventDefault();
      scrollToEl(target, 'start');

      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    });
  }

})();
