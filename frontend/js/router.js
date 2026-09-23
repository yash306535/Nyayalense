/**
 * Routing on the URL fragment.
 *
 * Fragments rather than paths, because the whole application is one static
 * page served from one origin and there is no server-side routing to keep in
 * step with it.
 */

/** The views the application has. Anything else falls back to the first. */
export const ROUTES = ['check', 'laws', 'draft', 'help', 'about'];

/**
 * Read the current route from the URL.
 *
 * @returns {string} A known route name.
 */
export function currentRoute() {
  const name = (location.hash.replace('#/', '') || ROUTES[0]).split('?')[0];
  return ROUTES.includes(name) ? name : ROUTES[0];
}

/**
 * Show one view and mark its navigation link as current.
 *
 * @param {string} view The route to show.
 * @returns {string} The route that was shown.
 */
export function showRoute(view) {
  for (const candidate of ROUTES) {
    const node = document.getElementById(`view-${candidate}`);
    if (node) node.hidden = candidate !== view;
  }
  for (const link of document.querySelectorAll('.app-nav a')) {
    if (link.dataset.route === view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  return view;
}
