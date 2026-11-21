// Build-time data loading. Everything here runs at `astro build`; nothing ships to the browser.
import fs from 'node:fs';
import path from 'node:path';

const SITE_ROOT = process.cwd();                       // site/
const REPO_ROOT = path.resolve(SITE_ROOT, '..');

function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c; }
    else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [head, ...body] = rows;
  return body.filter(r => r.length > 1).map(r => Object.fromEntries(head.map((h, i) => [h, r[i] ?? ''])));
}

// Team colours only (no logos). Chosen by us, approximate, used for a small accent stripe.
const COLOURS = {
  CSK: '#c9a400', MI: '#1f5fae', KKR: '#5b2a86', RCB: '#c0262d', DC: '#2a5db0',
  PBKS: '#d1343b', RR: '#d6458f', SRH: '#e8731a', GT: '#2b3a55', LSG: '#2a9db0',
  DECCAN: '#6b7280', KTK: '#6b7280', PWI: '#6b7280', RPS: '#6b7280', GL: '#6b7280',
};

export function franchises() {
  const csv = fs.readFileSync(path.join(REPO_ROOT, 'data/reference/franchises.csv'), 'utf8');
  return parseCsv(csv).map(r => ({
    id: r.franchise_id,
    name: r.current_name,
    aliases: r.aliases ? r.aliases.split('|').concat([]) : [],
    status: r.status,
    firstSeason: r.first_season,
    lastSeason: r.last_season,
    notes: r.notes,
    colour: COLOURS[r.franchise_id] || '#6b7280',
    // owner / source_url columns are deliberately not published: we model the seat, not people.
  }));
}

export function forecast() {
  const real = path.join(SITE_ROOT, 'data/forecast.json');
  const sample = path.join(SITE_ROOT, 'data/forecast.sample.json');
  return JSON.parse(fs.readFileSync(fs.existsSync(real) ? real : sample, 'utf8'));
}

export function l2() {
  const read = f => {
    const p = path.join(REPO_ROOT, 'data/processed/l2', f);
    return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : null;
  };
  return { scores: read('l2_scores.json'), aiq: read('auctioniq_scores.json'), llm: read('llm_scores.json') };
}

export function hashInfo() {
  const p = path.join(SITE_ROOT, 'data/hash.json');
  if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, 'utf8'));
  return {
    status: 'PLACEHOLDER',
    sha256: '0'.repeat(64),
    file: 'forecast.json',
    frozen_at: null,
    doi: null,
  };
}

export const fmtLakh = v => v >= 100 ? `₹${(v / 100).toFixed(2).replace(/\.?0+$/, "")} cr` : `₹${v} lakh`;
export const pct = v => `${Math.round(v * 100)}%`;
