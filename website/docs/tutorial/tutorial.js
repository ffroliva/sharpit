/* sharpit interactive tutorial controller
   Vanilla JS, no dependencies, no external calls, keyboard accessible.
*/

(function () {
  'use strict';

  function initTutorial() {
    var container = document.getElementById('tutorial-walkthrough');
    if (!container) return;

    var steps = container.querySelectorAll('.tutorial-step');
    var tabs = container.querySelectorAll('.tutorial-tab');
    var prevBtn = document.getElementById('tutorial-prev');
    var nextBtn = document.getElementById('tutorial-next');
    var progressFill = container.querySelector('.tutorial-progress-fill');
    var progressTrack = container.querySelector('.tutorial-progress-track');
    var stepCounter = document.getElementById('step-counter');

    var totalSteps = steps.length;
    var currentStep = 1;

    // Read initial step from URL hash if valid
    var hashMatch = window.location.hash.match(/^#step-(\d+)$/);
    if (hashMatch) {
      var parsed = parseInt(hashMatch[1], 10);
      if (parsed >= 1 && parsed <= totalSteps) {
        currentStep = parsed;
      }
    }

    // Enable interactive mode
    container.classList.add('is-interactive');

    function showStep(stepNum, shouldFocus) {
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

      // Update URL hash without jumping page scroll
      if (history.replaceState) {
        history.replaceState(null, '', '#step-' + currentStep);
      }
    }

    // Tab click handlers
    for (var k = 0; k < tabs.length; k++) {
      (function (tab) {
        tab.addEventListener('click', function () {
          var targetStep = parseInt(tab.getAttribute('data-step'), 10);
          showStep(targetStep, true);
        });
      })(tabs[k]);
    }

    // Prev / Next button handlers
    if (prevBtn) {
      prevBtn.addEventListener('click', function () {
        if (currentStep > 1) {
          showStep(currentStep - 1, true);
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener('click', function () {
        if (currentStep < totalSteps) {
          showStep(currentStep + 1, true);
        } else {
          showStep(1, true);
        }
      });
    }

    // Keyboard navigation
    window.addEventListener('keydown', function (e) {
      // Do not intercept keystrokes if the user is typing in an input
      var tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) {
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
    });

    // Initial render
    showStep(currentStep, false);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTutorial);
  } else {
    initTutorial();
  }
})();
