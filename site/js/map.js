// Mapa (Leaflet, via window.L). Funcoes puras exportadas sao testadas em Node.

export function themeMode() {
  const forced = globalThis.document?.documentElement?.dataset?.theme;
  if (forced === 'dark' || forced === 'light') return forced;
  return globalThis.matchMedia && globalThis.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function createMap(el, { tiles = false } = {}) {
  const L = globalThis.L;
  const map = L.map(el, { zoomSnap: 0.25, scrollWheelZoom: false });
  if (tiles) {
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
  }
  return map;
}

// Coropletico: fill(feature) -> cor; tooltip(feature) -> html ja escapado; onClick(feature).
export function choropleth(map, geojson, { fill, tooltip, onClick, surface }) {
  const L = globalThis.L;
  const layer = L.geoJSON(geojson, {
    style: (f) => ({ fillColor: fill(f), fillOpacity: 1, color: surface, weight: 1 }),
    onEachFeature: (f, lyr) => {
      lyr.bindTooltip(tooltip(f), { sticky: true });
      lyr.on('mouseover', () => lyr.setStyle({ weight: 3 }));
      lyr.on('mouseout', () => lyr.setStyle({ weight: 1 }));
      if (onClick) lyr.on('click', () => onClick(f));
    },
  }).addTo(map);
  map.fitBounds(layer.getBounds(), { padding: [8, 8] });
  return layer;
}
