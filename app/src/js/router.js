let explicitVersion = null;

export function parseHash(hash) {
  const [pathPart, query = ""] = String(hash || "")
    .replace(/^#\/?/, "")
    .split("?");
  const segments = pathPart
    .split("/")
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment));
  const version = Number(new URLSearchParams(query).get("v")) || null;
  return { segments, version };
}

export function currentRoute() {
  const route = parseHash(window.location.hash);
  explicitVersion = route.version;
  return route;
}

export function href(path, version = explicitVersion) {
  return version ? `${path}?v=${version}` : path;
}

export function navigate(path, version = explicitVersion) {
  const target = href(path, version);
  if (window.location.hash === target) {
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = target;
  }
}

export function currentPath() {
  return "#/" + parseHash(window.location.hash).segments.map(encodeURIComponent).join("/");
}

export function replacePath(path) {
  const target = href(path);
  window.history.replaceState(null, "", target);
}

export function startRouter(onRoute) {
  window.addEventListener("hashchange", () => onRoute(currentRoute()));
  onRoute(currentRoute());
}
