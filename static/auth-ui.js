/* Accessible authentication controls. Forms remain server-side for email/password. */
(() => {
  'use strict';
  const initialize = () => {
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
  };
  initialize();
  document.addEventListener('mindcare:login-mounted', initialize);
})();
