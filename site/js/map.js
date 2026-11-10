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

// Marcadores so para locais com lat e lon (os demais aparecem apenas na tabela).
export function markersFromLocais(locais, winners) {
  return locais
    .filter((l) => typeof l.lat === 'number' && typeof l.lon === 'number')
    .map((l) => ({ id: l.id, nome: l.nome, lat: l.lat, lon: l.lon, winner: winners[l.id] }));
}

// Camada de circulos: color(marker) -> cor; tooltip(marker) -> html escapado; radius(marker) opcional.
export function circleLayer(map, markers, { color, tooltip, radius, surface, onClick }) {
  const L = globalThis.L;
  const group = L.featureGroup(markers.map((m) => {
    const c = L.circleMarker([m.lat, m.lon], {
      radius: radius ? radius(m) : 8, fillColor: color(m), fillOpacity: 0.9, color: surface, weight: 2,
    }).bindTooltip(tooltip(m));
    if (onClick) c.on('click', () => onClick(m));
    return c;
  })).addTo(map);
  if (markers.length) map.fitBounds(group.getBounds(), { padding: [24, 24], maxZoom: 15 });
  return group;
}
