// node --experimental-strip-types --test lib/recommend.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NO_FILTER, ROW_SORT_LABEL, filterRows, rowPrice, sortRows } from './recommend.ts';

const promo = { name: 'Combo Lunes', kind: 'combo', includes: '', program: null, program_about: null, condition: '', price: 99, price_max: null, people: 2, applied: false };
const row = (show_id, chain, title, time, total, tickets, km, withPromo = false) => ({
  chain, show_id, cinema_name: `Cine ${show_id}`, lat: 0, lng: 0, title, date: '2026-10-01',
  datetime_local: `2026-10-01T${time}:00`, language: 'spanish', format_bucket: 'traditional', distance_km: km,
  buy_url: null, box_office_only: false, tickets_total: tickets, snacks_total: null, snacks_items: null,
  snack_reference: null, total, promo: withPromo ? promo : null,
});
const ROWS = [
  row('a', 'cinepolis', 'Él', '11:30', 300, 200, 4.2),
  row('b', 'cinemex', 'Zootopia 2', '18:00', 250, 180, 1.1, true),
  row('c', 'cinemex', 'Avatar', '12:00', null, 150, 2.5),
  row('d', 'cinepolis', 'avatar', '21:45', null, null, 0.8, true),
  row('e', 'cinemex', 'Él', '17:59', 250, 160, 3.0),
];
const ids = (rows) => rows.map((r) => r.show_id).join('');
const only = (patch) => ids(filterRows(ROWS, { ...NO_FILTER, ...patch }));

test('no filter keeps every row in order', () => {
  assert.equal(only({}), 'abcde');
});

test('chain filter', () => {
  assert.equal(only({ chain: 'cinemex' }), 'bce');
  assert.equal(only({ chain: 'cinepolis' }), 'ad');
  assert.equal(only({ chain: 'cineteca' }), '');
});

test('title filter ignores case, accents and surrounding spaces, and matches part of the name', () => {
  assert.equal(only({ title: 'avatar' }), 'cd');
  assert.equal(only({ title: ' EL ' }), 'ae');
  assert.equal(only({ title: 'zoo' }), 'b');
  assert.equal(only({ title: 'nada' }), '');
});

test('price filter uses total, then tickets, and drops rows without price', () => {
  assert.equal(rowPrice(ROWS[0]), 300);
  assert.equal(rowPrice(ROWS[2]), 150);
  assert.equal(rowPrice(ROWS[3]), null);
  assert.equal(only({ maxPrice: 250 }), 'bce');
  assert.equal(only({ maxPrice: 300 }), 'abce');
  assert.equal(only({ maxPrice: 149 }), '');
  assert.equal(only({ maxPrice: 0 }), '');
});

test('hour filter: start hour in [from, to)', () => {
  assert.equal(only({ slot: 'morning' }), 'a');
  assert.equal(only({ slot: 'afternoon' }), 'ce');
  assert.equal(only({ slot: 'night' }), 'bd');
});

test('promo filter', () => {
  assert.equal(only({ promo: true }), 'bd');
});

test('filters combine', () => {
  assert.equal(only({ chain: 'cinemex', title: 'el', maxPrice: 250, slot: 'afternoon' }), 'e');
  assert.equal(only({ chain: 'cinepolis', promo: true, slot: 'night' }), 'd');
});

test('sort without key keeps the API order', () => {
  assert.equal(sortRows(ROWS, null), ROWS);
  assert.equal(sortRows(ROWS, ''), ROWS);
});

test('sort by each option, both directions', () => {
  assert.equal(ids(sortRows(ROWS, 'distance')), 'dbcea');
  assert.equal(ids(sortRows(ROWS, '-distance')), 'aecbd');
  assert.equal(ids(sortRows(ROWS, 'time')), 'acebd');
  assert.equal(ids(sortRows(ROWS, '-time')), 'dbeca');
  // El orden por título ignora acentos y mayúsculas.
  assert.equal(ids(sortRows(ROWS, 'title')), 'cdaeb');
  assert.equal(ids(sortRows(ROWS, '-title')), 'baecd');
  assert.equal(ids(sortRows(ROWS, 'chain')), 'bcead');
  assert.equal(ids(sortRows(ROWS, '-chain')), 'adbce');
});

test('every sort option in the menu sorts; each pair is the reverse of the other without ties', () => {
  for (const option of Object.keys(ROW_SORT_LABEL)) assert.equal(sortRows(ROWS, option).length, ROWS.length, option);
  const byKm = ids(sortRows(ROWS, 'distance'));
  assert.equal(ids(sortRows(ROWS, '-distance')), [...byKm].reverse().join(''));
});

test('sort by price puts rows without price last in both directions', () => {
  assert.equal(ids(sortRows(ROWS, 'price')), 'cbead');
  assert.equal(ids(sortRows(ROWS, '-price')), 'abecd');
});

test('filter and sort keep the same row objects and do not change the input', () => {
  const before = structuredClone(ROWS);
  const out = sortRows(filterRows(ROWS, { ...NO_FILTER, chain: 'cinemex' }), '-price');
  assert.ok(out.every((r) => ROWS.includes(r)));
  assert.deepEqual(ROWS, before);
  assert.deepEqual(Object.keys(out[0]), Object.keys(before[0]));
});
