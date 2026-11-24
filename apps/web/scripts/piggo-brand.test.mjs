import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { test } from 'node:test';

const tokens = await readFile(new URL('../src/styles/piggo-tokens.css', import.meta.url), 'utf8');
const values = new Map([...tokens.matchAll(/--piggo-([\w-]+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]));
function color(name, theme) {
  const value = values.get(name);
  assert.ok(value, `Missing token: ${name}`);
  const pair = /^light-dark\((#[\da-f]{6}),\s*(#[\da-f]{6})\)$/i.exec(value);
  const result = pair ? pair[theme === 'light' ? 1 : 2] : value;
  assert.match(result, /^#[\da-f]{6}$/i, `Unsupported color token: ${name}`);
  return result;
}
function luminance(hex) {
  const rgb = hex.slice(1).match(/../g).map(channel => parseInt(channel, 16) / 255)
    .map(channel => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
function contrast(a, b) {
  const [high, low] = [luminance(a), luminance(b)].sort((a, b) => b - a);
  return (high + 0.05) / (low + 0.05);
}

// Check the actual CSS pairs: text >= 4.5:1, control boundaries/focus >= 3:1.
const pairs = [
  ['text', 'background', 4.5], ['text', 'surface', 4.5],
  ['muted', 'background', 4.5], ['muted', 'surface', 4.5],
  ['action-foreground', 'action-background', 4.5],
  ['action-foreground', 'action-hover', 4.5],
  ['action-text', 'surface', 4.5], ['action-text', 'soft', 4.5],
  ['action-text', 'positive-surface', 4.5],
  ['on-action-text', 'action-text', 4.5],
  ['positive', 'positive-surface', 4.5],
  ['warning', 'warning-surface', 4.5],
  ['danger', 'danger-surface', 4.5],
  ['info', 'info-surface', 4.5],
  ['planning', 'planning-surface', 4.5],
  ['debt', 'debt-surface', 4.5],
  ['reminder', 'reminder-surface', 4.5],
  ['danger', 'planning-surface', 4.5],
  ['border', 'surface', 3], ['border', 'background', 3],
  ['focus', 'surface', 3], ['focus', 'background', 3],
];
for (const surface of [
  'warning-surface', 'info-surface', 'danger-surface', 'positive-surface', 'planning-surface',
  'debt-surface', 'reminder-surface',
]) {
  pairs.push(['text', surface, 4.5], ['muted', surface, 4.5], ['focus', surface, 3]);
}
for (const theme of ['light', 'dark']) {
  for (const [foreground, background, minimum] of pairs) {
    test(`${theme}: ${foreground} / ${background} >= ${minimum}:1`, () => {
      const ratio = contrast(color(foreground, theme), color(background, theme));
      assert.ok(ratio >= minimum, `${ratio.toFixed(2)}:1 is below ${minimum}:1`);
    });
  }
}

for (const [name, expected] of [
  ['logo-aprobado.png', 'b862269910e0aa27c4a14e4cc51d03a01fc676c886155535324aed96aff8bcf9'],
  ['mascota-aprobada.png', '1ad14747d908cd6549983ed5871bbe65cf5c5f394920935f6613a9676d220756'],
]) {
  test(`approved artwork is unchanged: ${name}`, async () => {
    const bytes = await readFile(new URL(`../public/brand/piggo/${name}`, import.meta.url));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), expected);
  });
}
