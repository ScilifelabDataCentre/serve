function initializeAppSelectDropdowns() {
  document.querySelectorAll('select[data-app-dropdown]:not([data-app-dropdown-ready])').forEach(select => {
    select.dataset.appDropdownReady = 'true';
    const label = Array.from(select.labels || [])[0];
    const labelText = label?.textContent.trim() || select.getAttribute('aria-label') || 'Select';
    const wrapper = document.createElement('div');
    wrapper.className = 'dropdown app-select-dropdown';
    select.before(wrapper);
    wrapper.append(select);

    const button = document.createElement('button');
    button.type = 'button';
    button.id = `${select.id}_button`;
    button.className = 'form-select text-start app-select-trigger';
    button.setAttribute('data-bs-toggle', 'dropdown');
    button.setAttribute('aria-expanded', 'false');
    wrapper.append(button);

    const menu = document.createElement('div');
    menu.className = 'dropdown-menu app-select-menu p-2 w-100';
    menu.id = `${select.id}_menu`;
    menu.setAttribute('role', 'listbox');
    button.setAttribute('aria-controls', menu.id);
    wrapper.append(menu);

    const items = Array.from(select.options).map((option, index) => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'dropdown-item rounded text-start';
      item.textContent = option.textContent.trim();
      item.disabled = option.disabled;
      item.setAttribute('role', 'option');
      item.addEventListener('click', () => {
        select.selectedIndex = index;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        updateButton();
        button.focus();
      });
      menu.append(item);
      return item;
    });

    function updateButton() {
      const selected = select.options[select.selectedIndex];
      const placeholder = select.dataset.appDropdownPlaceholder;
      const text = select.selectedIndex === 0 && !selected?.value && placeholder
        ? placeholder : selected?.textContent.trim() || placeholder || 'Select';
      button.textContent = text;
      button.setAttribute('aria-label', `${labelText}: ${text}`);
      button.classList.toggle('is-invalid', select.classList.contains('is-invalid'));
      button.disabled = select.disabled;
      for (const attr of ['aria-invalid', 'aria-describedby']) {
        if (select.hasAttribute(attr)) button.setAttribute(attr, select.getAttribute(attr));
        else button.removeAttribute(attr);
      }
      items.forEach((item, index) => item.setAttribute('aria-selected', String(index === select.selectedIndex)));
    }

    select.style.display = 'none';
    select.setAttribute('aria-hidden', 'true');
    select.tabIndex = -1;
    if (label) label.htmlFor = button.id;
    select.addEventListener('change', updateButton);
    new MutationObserver(updateButton).observe(select, {
      attributes: true,
      attributeFilter: ['class', 'aria-invalid', 'aria-describedby', 'disabled'],
    });
    updateButton();
  });
}

document.addEventListener('DOMContentLoaded', initializeAppSelectDropdowns);
document.addEventListener('htmx:beforeSwap', event => {
  const select = event.detail.target;
  if (event.detail.shouldSwap === false || !select?.matches?.('select[data-app-dropdown]')) return;
  const wrapper = select.parentElement;
  if (!wrapper?.classList.contains('app-select-dropdown')) return;
  const label = document.querySelector(`label[for="${select.id}_button"]`);
  if (label) label.htmlFor = select.id;
  select.style.removeProperty('display');
  select.removeAttribute('aria-hidden');
  select.removeAttribute('tabindex');
  wrapper.replaceWith(select);
});
document.addEventListener('htmx:afterSwap', initializeAppSelectDropdowns);
