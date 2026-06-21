// Color helpers (RGB tuples for deck.gl)

export function esiColor(esi) {
  // 0..10 → green → yellow → red
  const t = Math.max(0, Math.min(1, esi / 10));
  if (t < 0.5) {
    const k = t / 0.5;
    return [
      Math.round(34 + (251 - 34) * k),
      Math.round(211 + (191 - 211) * k),
      Math.round(238 + (36 - 238) * k),
    ];
  }
  const k = (t - 0.5) / 0.5;
  return [
    Math.round(251 + (248 - 251) * k),
    Math.round(191 + (113 - 191) * k),
    Math.round(36 + (113 - 36) * k),
  ];
}

export function probColor(p) {
  // probability 0..1 → soft cyan → magenta
  const t = Math.max(0, Math.min(1, p));
  return [
    Math.round(56 + (244 - 56) * t),
    Math.round(189 + (114 - 189) * t),
    Math.round(248 + (182 - 248) * t),
  ];
}

export function withAlpha(rgb, a) {
  return [rgb[0], rgb[1], rgb[2], Math.round(a * 255)];
}
