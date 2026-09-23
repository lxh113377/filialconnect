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
    initPrintButtons();
    initSmoothScroll();
  });

  /* ============================================================
     i18n — Language Toggle (EN / ZH)
     ============================================================ */
  var LANG_KEY = 'filialconnect-lang';
  var SUPPORTED_LANGS = ['en', 'zh'];

  function getCurrentLang() {
    var stored = localStorage.getItem(LANG_KEY);
    if (stored && SUPPORTED_LANGS.indexOf(stored) !== -1) {
      return stored;
    }
    return 'en';
  }

  function applyTranslations(lang) {
    if (typeof I18N === 'undefined' || !I18N[lang]) return;

    var dict = I18N[lang];

    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      if (dict[key] !== undefined) {
        var val = dict[key];
        if (/<[a-z][\s\S]*>/i.test(val)) {
          el.innerHTML = val;
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
      toggleBtn.setAttribute('aria-label', lang === 'en' ? 'Switch to Chinese' : 'Switch to English');
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
        localStorage.setItem(LANG_KEY, newLang);
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
      if (e.key === 'Escape' && links.classList.contains('open')) {
        links.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
        toggle.focus();
      }
    });
  }

  /* ============================================================
     Active Navigation State
     ============================================================ */
  function initActiveNav() {
    var currentPath = window.location.pathname;
    var navLinks = document.querySelectorAll('.nav-links a');

    navLinks.forEach(function (link) {
      var href = link.getAttribute('href');
      if (!href) return;

      if (currentPath.endsWith(href) ||
          (href === 'index.html' && (currentPath.endsWith('/') || currentPath.endsWith('index.html')))) {
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

    function checkVisibility() {
      animatedElements.forEach(function (el) {
        var rect = el.getBoundingClientRect();
        var windowHeight = window.innerHeight || document.documentElement.clientHeight;
        if (rect.top < windowHeight * 0.85 && rect.bottom > 0) {
          el.classList.add('visible');
        }
      });
    }

    checkVisibility();

    var ticking = false;
    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(function () {
          checkVisibility();
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
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
        });
        if (!isOpen) {
          item.classList.add('open');
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
    toast.innerHTML = '<span>' + message + '</span>';
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
     Print Buttons
     ============================================================ */
  function initPrintButtons() {
    var printBtns = document.querySelectorAll('.print-btn');

    printBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        window.print();
      });
    });
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
