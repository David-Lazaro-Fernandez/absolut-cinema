# marketing/

Landing page pública de Matiné, el nombre de cara al público del producto (el dashboard interno de
este repo sigue llamándose Absolut Cinema; ver `design.md` §1). Es un proyecto Next.js **independiente**
del resto del repo: tiene su propio `package.json`, no importa nada de `scraper/`, `analytics/`, `app.py`,
`sync/`, `auth/` ni `archive/`, y ellos tampoco lo importan a él. Se exporta como sitio estático
(`output: 'export'` en `next.config.mjs`) porque no necesita servidor ni base de datos.

Antes de tocar el contenido o el estilo, lee `design.md`: documenta la identidad visual (heredada
de `../DESIGN.md` y `../analytics/labels.py`), el tono de copy, la estructura de la portada y el
vocabulario del stylesheet.

- `app/` — `layout.tsx` (metadatos, `lang="es"`), `page.tsx` (compone las secciones) y `globals.css`
  (todo el CSS, con los tokens de color como variables).
- `components/` — una sección por archivo (`navigation`, `hero-section`, `features-section`,
  `how-it-works-section`, `pilot-section`, `principles-section`, `cta-section`, `footer-section`),
  más `reveal.tsx` (aparición por scroll), `ascii-sphere.tsx` (canvas del hero) e `icons.tsx`.
- `lib/site.ts` — correo de contacto y enlaces de navegación; lo único que se repite en varias secciones.
- `scripts/screenshot.mjs` — capturas y medidas con el Chrome instalado, por protocolo DevTools.

```sh
npm install       # una vez
npm run dev       # http://localhost:3000
npm run build     # exporta el sitio estático a marketing/out/
node scripts/screenshot.mjs http://localhost:3000/ 1440 900 /tmp/hero.png        # un viewport
node scripts/screenshot.mjs http://localhost:3000/ 390 844 /tmp/movil.png full    # página entera
```

`marketing/out/` es el resultado listo para subir a cualquier hosting estático; no se versiona
(ver `.gitignore` de esta carpeta).

`marketing/AGENTS.md` y `marketing/CLAUDE.md` no los escribimos nosotros: `next dev` los regenera
solo (avisa qué tan roto puede estar el conocimiento previo de un agente sobre esta versión de
Next.js) y pide commitearlos. No son la guía de este proyecto — esa sigue siendo `design.md` — así
que no los borres ni les copies contenido; si `next dev` los vuelve a tocar, es normal.
