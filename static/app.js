"use strict";

document.querySelectorAll("form[data-confirm]").forEach(form => {
  form.addEventListener("submit", event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

document.querySelectorAll("[data-copy]").forEach(button => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copy);
    try {
      await navigator.clipboard.writeText(target.value);
      button.textContent = "Odkaz skopírovaný";
    } catch (_) {
      target.focus(); target.select();
      button.textContent = "Označené - skopírujte odkaz";
    }
  });
});

const clientForm = document.querySelector("[data-wizard]");
if (clientForm) {
  const steps = [...clientForm.querySelectorAll("[data-step]")];
  const labels = [...clientForm.querySelectorAll("[data-step-label]")];
  const previous = clientForm.querySelector("[data-prev]");
  const next = clientForm.querySelector("[data-next]");
  const submit = clientForm.querySelector("[data-submit]");
  let current = 0;
  clientForm.noValidate = true;
  const show = index => {
    current = index;
    steps.forEach((section, i) => { section.hidden = i !== current; });
    labels.forEach((label, i) => {
      label.classList.toggle("current", i === current);
      if (i === current) label.setAttribute("aria-current", "step");
      else label.removeAttribute("aria-current");
    });
    previous.hidden = current === 0;
    next.hidden = current === steps.length - 1;
    submit.hidden = current !== steps.length - 1;
    clientForm.querySelector("[data-step-count]").textContent = `${current + 1} / ${steps.length}`;
  };
  const validate = index => {
    const section = steps[index];
    if (index === 3 && !clientForm.querySelector("input[name=goals]:checked")) {
      const checkbox = section.querySelector("input[name=goals]");
      checkbox.setCustomValidity("Vyberte aspoň jeden cieľ.");
      checkbox.reportValidity();
      checkbox.addEventListener("change", () => checkbox.setCustomValidity(""), {once:true});
      return false;
    }
    section.querySelectorAll("input[name=goals]").forEach(x => x.setCustomValidity(""));
    for (const field of section.querySelectorAll("input,select,textarea")) {
      if (!field.checkValidity()) { field.reportValidity(); return false; }
    }
    return true;
  };
  const focusStep = () => {
    steps[current].scrollIntoView({behavior:"smooth",block:"start"});
    steps[current].querySelector("input,select,textarea")?.focus({preventScroll:true});
  };
  next.addEventListener("click", () => { if (validate(current)) { show(current + 1); focusStep(); } });
  previous.addEventListener("click", () => { show(current - 1); focusStep(); });
  clientForm.addEventListener("submit", event => {
    for (let i = 0; i < steps.length; i++) {
      if (!validate(i)) { event.preventDefault(); show(i); focusStep(); return; }
    }
    if (current < steps.length - 1) { event.preventDefault(); show(current + 1); focusStep(); }
    else { submit.disabled = true; submit.textContent = "Ukladám údaje…"; }
  });
  show(0);
  const debtList = document.getElementById("debt-list");
  clientForm.querySelector("[data-add-debt]").addEventListener("click", () => {
    if (debtList.children.length >= 30) { window.alert("Povolených je najviac 30 záväzkov."); return; }
    debtList.append(document.getElementById("debt-template").content.cloneNode(true));
    debtList.lastElementChild.querySelector("select").focus();
  });
  debtList.addEventListener("click", event => {
    const button = event.target.closest("[data-remove-debt]");
    if (button) button.closest(".debt-row").remove();
  });
}
