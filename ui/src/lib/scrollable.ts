/**
 * Makes a scroll region a tab stop only while it actually overflows (axe `scrollable-region-focusable`), so a short
 * panel adds no empty stop to the Tab order. Re-checked when the region or its content resizes or changes.
 */
export function scrollable(node: HTMLElement) {
  const check = () => {
    const overflows = node.scrollHeight > node.clientHeight || node.scrollWidth > node.clientWidth;
    if (overflows) node.tabIndex = 0;
    else if (document.activeElement !== node) node.removeAttribute('tabindex'); // never pull focus out from under the user
  };
  check();
  if (typeof ResizeObserver === 'undefined') return {}; // jsdom: no layout to measure
  const resize = new ResizeObserver(check);
  const observeAll = () => {
    resize.disconnect();
    resize.observe(node);
    for (const child of node.children) resize.observe(child);
    check();
  };
  const mutation = new MutationObserver(observeAll);
  mutation.observe(node, { childList: true });
  observeAll();
  return {
    destroy() {
      resize.disconnect();
      mutation.disconnect();
    },
  };
}
