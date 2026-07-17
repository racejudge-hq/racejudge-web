// Real geographic coordinates of the F1 circuits (public facts, [lng, lat]).
// Keyed by OpenF1 / FIA circuit_short_name (and common aliases).
export interface Circuit {
  name: string;
  country: string;
  lngLat: [number, number];
}

export const CIRCUITS: Record<string, Circuit> = {
  Sakhir: { name: "Bahrain International Circuit", country: "Bahrain", lngLat: [50.5106, 26.0325] },
  Jeddah: { name: "Jeddah Corniche Circuit", country: "Saudi Arabia", lngLat: [39.1044, 21.6319] },
  Melbourne: { name: "Albert Park Circuit", country: "Australia", lngLat: [144.968, -37.8497] },
  Suzuka: { name: "Suzuka International Racing Course", country: "Japan", lngLat: [136.541, 34.8431] },
  Shanghai: { name: "Shanghai International Circuit", country: "China", lngLat: [121.22, 31.3389] },
  Miami: { name: "Miami International Autodrome", country: "United States", lngLat: [-80.2389, 25.9581] },
  Imola: { name: "Autodromo Enzo e Dino Ferrari", country: "Italy", lngLat: [11.7167, 44.3439] },
  Monaco: { name: "Circuit de Monaco", country: "Monaco", lngLat: [7.4206, 43.7347] },
  Montreal: { name: "Circuit Gilles Villeneuve", country: "Canada", lngLat: [-73.5228, 45.5] },
  Catalunya: { name: "Circuit de Barcelona-Catalunya", country: "Spain", lngLat: [2.2611, 41.57] },
  Barcelona: { name: "Circuit de Barcelona-Catalunya", country: "Spain", lngLat: [2.2611, 41.57] },
  Spielberg: { name: "Red Bull Ring", country: "Austria", lngLat: [14.7647, 47.2197] },
  Silverstone: { name: "Silverstone Circuit", country: "United Kingdom", lngLat: [-1.0169, 52.0786] },
  Hungaroring: { name: "Hungaroring", country: "Hungary", lngLat: [19.2486, 47.5789] },
  "Spa-Francorchamps": { name: "Circuit de Spa-Francorchamps", country: "Belgium", lngLat: [5.9714, 50.4372] },
  Spa: { name: "Circuit de Spa-Francorchamps", country: "Belgium", lngLat: [5.9714, 50.4372] },
  Zandvoort: { name: "Circuit Zandvoort", country: "Netherlands", lngLat: [4.5409, 52.3888] },
  Monza: { name: "Autodromo Nazionale Monza", country: "Italy", lngLat: [9.2811, 45.6156] },
  Baku: { name: "Baku City Circuit", country: "Azerbaijan", lngLat: [49.8533, 40.3725] },
  Singapore: { name: "Marina Bay Street Circuit", country: "Singapore", lngLat: [103.864, 1.2914] },
  "Marina Bay": { name: "Marina Bay Street Circuit", country: "Singapore", lngLat: [103.864, 1.2914] },
  Austin: { name: "Circuit of the Americas", country: "United States", lngLat: [-97.6411, 30.1328] },
  "Mexico City": { name: "Autódromo Hermanos Rodríguez", country: "Mexico", lngLat: [-99.0907, 19.4042] },
  Interlagos: { name: "Autódromo José Carlos Pace", country: "Brazil", lngLat: [-46.6997, -23.7036] },
  "Sao Paulo": { name: "Autódromo José Carlos Pace", country: "Brazil", lngLat: [-46.6997, -23.7036] },
  "Las Vegas": { name: "Las Vegas Strip Circuit", country: "United States", lngLat: [-115.173, 36.1147] },
  Lusail: { name: "Lusail International Circuit", country: "Qatar", lngLat: [51.4542, 25.49] },
  "Yas Marina Circuit": { name: "Yas Marina Circuit", country: "UAE", lngLat: [54.6031, 24.4672] },
  "Yas Island": { name: "Yas Marina Circuit", country: "UAE", lngLat: [54.6031, 24.4672] },
};

export function lookupCircuit(name?: string | null): Circuit | undefined {
  if (!name) return undefined;
  if (CIRCUITS[name]) return CIRCUITS[name];
  const key = Object.keys(CIRCUITS).find(
    (k) => k.toLowerCase() === name.toLowerCase() || name.toLowerCase().includes(k.toLowerCase()),
  );
  return key ? CIRCUITS[key] : undefined;
}
