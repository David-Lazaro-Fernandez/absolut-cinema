'use client';

import { useEffect, useRef } from 'react';

const CHARS = '░▒▓█▀▄▌▐│─┤├┴┬╭╮╰╯';

// El color sale de la variable --ink del stylesheet, así el canvas no lleva ningún hex propio.
function inkRgb() {
  const hex = getComputedStyle(document.documentElement).getPropertyValue('--ink').trim().replace('#', '');
  const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
  const n = parseInt(full, 16);
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
}

export function AsciiSphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rgb = inkRgb();
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let frame = 0;
    let time = 0;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const radius = Math.min(rect.width, rect.height) * 0.5;

      ctx.font = '12px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      const points: { x: number; y: number; z: number; char: string }[] = [];
      for (let phi = 0; phi < Math.PI * 2; phi += 0.15) {
        for (let theta = 0; theta < Math.PI; theta += 0.15) {
          const x = Math.sin(theta) * Math.cos(phi + time * 0.5);
          const y = Math.sin(theta) * Math.sin(phi + time * 0.5);
          const z = Math.cos(theta);
          const rotY = time * 0.3;
          const x1 = x * Math.cos(rotY) - z * Math.sin(rotY);
          const z1 = x * Math.sin(rotY) + z * Math.cos(rotY);
          const rotX = time * 0.2;
          const y1 = y * Math.cos(rotX) - z1 * Math.sin(rotX);
          const z2 = y * Math.sin(rotX) + z1 * Math.cos(rotX);
          const depth = (z2 + 1) / 2;
          points.push({
            x: cx + x1 * radius,
            y: cy + y1 * radius,
            z: z2,
            char: CHARS[Math.floor(depth * (CHARS.length - 1))],
          });
        }
      }
      points.sort((a, b) => a.z - b.z);
      for (const p of points) {
        ctx.fillStyle = `rgba(${rgb}, ${0.2 + (p.z + 1) * 0.4})`;
        ctx.fillText(p.char, p.x, p.y);
      }

      if (reduceMotion) return;
      time += 0.02;
      frame = requestAnimationFrame(render);
    };

    resize();
    render();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(frame);
    };
  }, []);

  return <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%' }} />;
}
