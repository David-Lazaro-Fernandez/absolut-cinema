// node --experimental-strip-types --test lib/demo.test.mjs
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { personName, phone, website, workEmail } from './demo.ts';

test('work email rejects personal providers in any country', () => {
  for (const email of ['ana@gmail.com', 'ana@hotmail.es', 'ana@yahoo.com.mx', 'ana@live.com.mx', 'ANA@Outlook.com', 'ana@icloud.com', 'ana@prodigy.net.mx']) {
    assert.notEqual(workEmail(email), '', email);
  }
});

test('work email accepts company domains, also ones that contain a provider name', () => {
  for (const email of ['ana@cinesdelcentro.mx', 'ana@mail.cinepolis.com', 'ana@gmailcinemas.com', ' ana@cinemex.com ']) {
    assert.equal(workEmail(email), '', email);
  }
  for (const email of ['', 'ana', 'ana@cinemex', 'ana @cinemex.com']) assert.notEqual(workEmail(email), '', email);
});

test('names, phone and website', () => {
  assert.equal(personName('María José', 'nombre'), '');
  assert.equal(personName("O'Connor-Pérez", 'apellido'), '');
  assert.notEqual(personName('A', 'nombre'), '');
  assert.notEqual(personName('Ana3', 'nombre'), '');
  assert.equal(phone(''), '');
  assert.equal(phone('55 1234-5678'), '');
  assert.notEqual(phone('1234'), '');
  assert.equal(website(''), '');
  assert.equal(website('https://www.cinemex.com/cartelera'), '');
  assert.notEqual(website('cinemex'), '');
});
