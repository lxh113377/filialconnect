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
    initRemoteCode();
    initLinkCheck();
    initSmoothScroll();
  });

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

    document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
      var key = el.getAttribute('data-i18n-placeholder');
      if (dict[key] !== undefined) {
        el.setAttribute('placeholder', dict[key]);
      }
    });

    document.querySelectorAll('[data-i18n-aria-label]').forEach(function (el) {
      var key = el.getAttribute('data-i18n-aria-label');
      if (dict[key] !== undefined) {
        el.setAttribute('aria-label', dict[key]);
      }
    });

    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';

    var toggleBtn = document.querySelector('.lang-toggle');
    if (toggleBtn) {
      toggleBtn.querySelector('.lang-toggle-label').textContent = lang === 'en' ? 'ZH' : 'EN';
      toggleBtn.setAttribute('aria-label', lang === 'en' ? 'ZH - Switch to Chinese' : 'EN - Switch to English');
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
      window.scrollTo({ top: 0, behavior: 'smooth' });
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
     Tutorial Filter
     ============================================================ */
  function initTutorialFilter() {
    var filterTags = document.querySelectorAll('.filter-tag');
    var tutorialCards = document.querySelectorAll('.tutorial-card');

    if (filterTags.length === 0 || tutorialCards.length === 0) return;

    filterTags.forEach(function (tag) {
      tag.addEventListener('click', function () {
        filterTags.forEach(function (t) {
          t.classList.remove('active');
          t.setAttribute('aria-pressed', 'false');
        });
        tag.classList.add('active');
        tag.setAttribute('aria-pressed', 'true');

        var filter = tag.getAttribute('data-filter');

        tutorialCards.forEach(function (card) {
          if (filter === 'all') {
            card.style.display = '';
            return;
          }
          var cardCategory = card.getAttribute('data-category');
          if (cardCategory === filter) {
            card.style.display = '';
          } else {
            card.style.display = 'none';
          }
        });
      });
    });
  }

  /* ============================================================
     Help Request Form
     ============================================================ */
  function initHelpForm() {
    var form = document.getElementById('help-request-form');
    if (!form) return;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var lang = getCurrentLang();
      var msg = (typeof I18N !== 'undefined' && I18N[lang] && I18N[lang]['toast.help-sent'])
        ? I18N[lang]['toast.help-sent']
        : 'Help request sent!';
      showToast(msg, 'success');
      form.reset();
    });
  }

  /* ============================================================
     Call Help Functionality
     ============================================================ */
  function initCallHelp() {
    var callBtn = document.querySelector('.call-button');
    var statusEl = document.querySelector('.call-status');

    if (!callBtn || !statusEl) return;

    function t(key) {
      var lang = getCurrentLang();
      return (typeof I18N !== 'undefined' && I18N[lang] && I18N[lang][key]) ? I18N[lang][key] : key;
    }

    callBtn.addEventListener('click', function () {
      callBtn.disabled = true;
      callBtn.style.opacity = '0.6';
      callBtn.style.cursor = 'wait';
      callBtn.querySelector('.call-text').textContent = t('call.sending');

      setTimeout(function () {
        statusEl.classList.add('visible');
        callBtn.style.opacity = '1';
        callBtn.style.cursor = 'pointer';
        callBtn.querySelector('.call-text').textContent = t('call.sent');
        callBtn.disabled = false;

        showToast(t('toast.help-sent'), 'success');

        setTimeout(function () {
          callBtn.querySelector('.call-text').textContent = t('call.button');
        }, 5000);
      }, 1500);
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

    function loadDomains(cb) {
      if (set) { cb(set); return; }
      out.textContent = t('linkcheck.loading');
      fetch('../assets/data/destroylist-domains.txt')
        .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.text(); })
        .then(function (txt) {
          set = new Set(txt.split(/\r?\n/).filter(Boolean));
          cb(set);
        })
        .catch(function () {
          out.textContent = t('linkcheck.errload');
          out.className = 'link-check-result is-unknown';
        });
    }

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
    codeEl.setAttribute('aria-label', 'Connection code: ' + code);
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
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });

      target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    });
  }

})();
