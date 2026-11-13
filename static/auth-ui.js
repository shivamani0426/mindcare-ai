/* Accessible authentication controls. Forms remain server-side for email/password. */
(() => {
  'use strict';
  const tabs = [...document.querySelectorAll('[data-auth-tab]')];
  const panels = [...document.querySelectorAll('[data-auth-panel]')];
  function selectMethod(method) {
    tabs.forEach(tab => tab.setAttribute('aria-pressed', String(tab.dataset.authTab === method)));
    panels.forEach(panel => {panel.hidden = panel.dataset.authPanel !== method;});
  }
  tabs.forEach(tab => tab.addEventListener('click', () => selectMethod(tab.dataset.authTab)));
  document.querySelectorAll('[data-auth-return-email]').forEach(btn =>
    btn.addEventListener('click', () => selectMethod('email')));

  document.querySelectorAll('.auth-password-visibility').forEach(button =>
    button.addEventListener('click', () => {
      const target = document.getElementById(button.getAttribute('aria-controls'));
      if (!target) return;
      const showing = target.type === 'password';
      target.type = showing ? 'text' : 'password';
      button.textContent = showing ? 'Hide' : 'Show';
      button.setAttribute('aria-pressed', String(showing));
    }));
  const choices = [...document.querySelectorAll('.auth-role-selector input[name="role"]')];
  const patientFields = [...document.querySelectorAll('.auth-patient-fields')];
  function updateRole() {
    const role = choices.find(c => c.checked)?.value || 'patient';
    patientFields.forEach(node => {
      node.hidden = role !== 'patient';
      node.querySelectorAll('input,select').forEach(input => {input.disabled = role !== 'patient';});
    });
  }
  choices.forEach(choice => choice.addEventListener('change', updateRole));
  updateRole();
})();
