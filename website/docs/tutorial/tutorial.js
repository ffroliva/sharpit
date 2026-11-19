/* sharpit interactive tutorial controller
   Vanilla JS, no dependencies, no external calls, keyboard accessible.
   Integrated with Material for MkDocs instant navigation (document$).
*/

(function () {
  'use strict';

  var teardownTutorial = null;

  function initTutorial() {
    // Teardown previous listeners if navigating back or re-running
    if (teardownTutorial) {
      teardownTutorial();
      teardownTutorial = null;
    }

    var container = document.getElementById('tutorial-walkthrough');
    if (!container) {
      return;
    }

    var steps = container.querySelectorAll('.tutorial-step');
    var tabs = container.querySelectorAll('.tutorial-tab');
    var prevBtn = document.getElementById('tutorial-prev');
    var nextBtn = document.getElementById('tutorial-next');
    var progressFill = container.querySelector('.tutorial-progress-fill');
    var progressTrack = container.querySelector('.tutorial-progress-track');
    var stepCounter = document.getElementById('step-counter');

    var totalSteps = steps.length;
    var currentStep = 1;

    // Read initial step from URL hash if valid and on tutorial page
    if (window.location.pathname.indexOf('tutorial') !== -1) {
      var hashMatch = window.location.hash.match(/^#step-(\d+)$/);
      if (hashMatch) {
        var parsed = parseInt(hashMatch[1], 10);
        if (parsed >= 1 && parsed <= totalSteps) {
          currentStep = parsed;
        }
      }
    }

    // Enable interactive mode
    container.classList.add('is-interactive');

    function showStep(stepNum, shouldFocus) {
      if (!document.getElementById('tutorial-walkthrough')) {
        return;
      }
      if (stepNum < 1) stepNum = 1;
      if (stepNum > totalSteps) stepNum = totalSteps;
      currentStep = stepNum;

      // Update steps visibility
      for (var i = 0; i < steps.length; i++) {
        var step = steps[i];
        var num = parseInt(step.getAttribute('data-step'), 10);
        if (num === currentStep) {
          step.classList.add('is-active');
          step.setAttribute('aria-hidden', 'false');
          if (shouldFocus) {
            step.focus();
          }
        } else {
          step.classList.remove('is-active');
          step.setAttribute('aria-hidden', 'true');
        }
      }

      // Update tabs
      for (var j = 0; j < tabs.length; j++) {
        var tab = tabs[j];
        var tabNum = parseInt(tab.getAttribute('data-step'), 10);
        if (tabNum === currentStep) {
          tab.classList.add('is-active');
          tab.setAttribute('aria-current', 'step');
        } else {
          tab.classList.remove('is-active');
          tab.removeAttribute('aria-current');
        }
      }

      // Update progress bar & metadata
      var percentage = Math.round((currentStep / totalSteps) * 100);
      if (progressFill) {
        progressFill.style.width = percentage + '%';
      }
      if (progressTrack) {
        progressTrack.setAttribute('aria-valuenow', currentStep);
      }
      if (stepCounter) {
        stepCounter.textContent = 'Step ' + currentStep + ' of ' + totalSteps;
      }

      // Update button states
      if (prevBtn) {
        prevBtn.disabled = currentStep === 1;
      }
      if (nextBtn) {
        if (currentStep === totalSteps) {
          nextBtn.textContent = 'Start over \u21ba';
        } else {
          nextBtn.textContent = 'Next \u2192';
        }
      }

      // Update URL hash ONLY on the tutorial page
      if (window.location.pathname.indexOf('tutorial') !== -1 && history.replaceState) {
        history.replaceState(null, '', '#step-' + currentStep);
      }
    }

    // Tab click handlers
    var tabCleanups = [];
    for (var k = 0; k < tabs.length; k++) {
      (function (tab) {
        var onTabClick = function () {
          var targetStep = parseInt(tab.getAttribute('data-step'), 10);
          showStep(targetStep, true);
        };
        tab.addEventListener('click', onTabClick);
        tabCleanups.push(function () {
          tab.removeEventListener('click', onTabClick);
        });
      })(tabs[k]);
    }

    // Prev / Next button handlers
    var onPrevClick = function () {
      if (currentStep > 1) {
        showStep(currentStep - 1, true);
      }
    };
    if (prevBtn) {
      prevBtn.addEventListener('click', onPrevClick);
    }

    var onNextClick = function () {
      if (currentStep < totalSteps) {
        showStep(currentStep + 1, true);
      } else {
        showStep(1, true);
      }
    };
    if (nextBtn) {
      nextBtn.addEventListener('click', onNextClick);
    }

    // Keyboard navigation:
    // Handled ONLY while focus is inside the tutorial widget (container).
    // Never register on window beyond the tutorial page!
    // Never call preventDefault otherwise.
    var onKeyDown = function (e) {
      if (!container.contains(document.activeElement) && !container.contains(e.target)) {
        return;
      }

      // Do not intercept keystrokes if the user is typing in an input
      var tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (e.target && e.target.isContentEditable)) {
        return;
      }

      if (e.key === 'ArrowRight') {
        if (currentStep < totalSteps) {
          e.preventDefault();
          showStep(currentStep + 1, true);
        }
      } else if (e.key === 'ArrowLeft') {
        if (currentStep > 1) {
          e.preventDefault();
          showStep(currentStep - 1, true);
        }
      } else if (e.key === 'Home') {
        e.preventDefault();
        showStep(1, true);
      } else if (e.key === 'End') {
        e.preventDefault();
        showStep(totalSteps, true);
      }
    };

    container.addEventListener('keydown', onKeyDown);

    teardownTutorial = function () {
      container.removeEventListener('keydown', onKeyDown);
      if (prevBtn) {
        prevBtn.removeEventListener('click', onPrevClick);
      }
      if (nextBtn) {
        nextBtn.removeEventListener('click', onNextClick);
      }
      for (var l = 0; l < tabCleanups.length; l++) {
        tabCleanups[l]();
      }
    };

    // Initial render
    showStep(currentStep, false);
  }

  // MkDocs Material navigation.instant support:
  // Subscribe to document$ observable for instant page changes
  if (typeof document$ !== 'undefined') {
    document$.subscribe(initTutorial);
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      if (typeof document$ !== 'undefined') {
        document$.subscribe(initTutorial);
      } else {
        initTutorial();
      }
    });
  } else {
    initTutorial();
  }
})();
