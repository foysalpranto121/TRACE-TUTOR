import React, { useEffect, useRef } from 'react';
import { useTheme } from '../../context/ThemeContext';

// Sparse falling code glyphs behind hero/auth sections. Canvas keeps it off the
// layout/paint path; it throttles to ~20fps, pauses when the tab or section is
// hidden, and never runs unless FX are set to "full".
const GLYPHS = '01{}[]()<>;=+-*/%&|!#ifelseforwhileintprintfscanfreturnvoidmainNULL'.split('');

export const CodeRain = ({ className = '', density = 0.6, opacity = 0.5 }) => {
  const canvasRef = useRef(null);
  const { ambient, isDark } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !ambient) return undefined;

    const ctx = canvas.getContext('2d', { alpha: true });
    const parent = canvas.parentElement;
    let raf = 0;
    let columns = [];
    let dpr = 1;
    let visible = true;
    let last = 0;
    const FRAME_MS = 50; // ~20fps is plenty for drifting glyphs and saves battery

    // Multi-hue so the rain reads as playful rather than one flat tint.
    const palette = isDark
      ? ['rgba(34,211,238,', 'rgba(167,139,250,', 'rgba(163,230,53,', 'rgba(251,146,60,', 'rgba(244,114,182,']
      : ['rgba(2,132,199,', 'rgba(124,58,237,', 'rgba(5,150,105,', 'rgba(234,88,12,', 'rgba(219,39,119,'];

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;

      const spacing = 26;
      const count = Math.max(1, Math.floor((rect.width / spacing) * density));
      columns = Array.from({ length: count }, () => ({
        x: Math.random() * rect.width,
        y: Math.random() * rect.height,
        speed: 0.35 + Math.random() * 0.9,
        glyph: GLYPHS[(Math.random() * GLYPHS.length) | 0],
        alpha: 0.15 + Math.random() * 0.5,
        color: palette[(Math.random() * palette.length) | 0],
        size: 10 + Math.random() * 4,
        ttl: 40 + Math.random() * 120,
      }));
    };

    const draw = (now) => {
      raf = requestAnimationFrame(draw);
      if (!visible || now - last < FRAME_MS) return;
      last = now;

      const h = canvas.height / dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, canvas.width / dpr, h);
      ctx.font = '500 12px "JetBrains Mono", monospace';

      for (const c of columns) {
        c.y += c.speed;
        c.ttl -= 1;
        if (c.ttl <= 0) {
          c.glyph = GLYPHS[(Math.random() * GLYPHS.length) | 0];
          c.ttl = 40 + Math.random() * 120;
        }
        if (c.y > h + 20) {
          c.y = -20;
          c.x = Math.random() * (canvas.width / dpr);
        }
        ctx.font = `500 ${c.size}px "JetBrains Mono", monospace`;
        ctx.fillStyle = `${c.color}${(c.alpha * opacity).toFixed(3)})`;
        ctx.fillText(c.glyph, c.x, c.y);
      }
    };

    resize();
    raf = requestAnimationFrame(draw);

    const ro = new ResizeObserver(resize);
    ro.observe(parent);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting && !document.hidden; }, { threshold: 0 });
    io.observe(canvas);
    const onVisibility = () => { visible = !document.hidden; };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [ambient, isDark, density, opacity]);

  if (!ambient) return null;
  return <canvas ref={canvasRef} aria-hidden className={`absolute inset-0 w-full h-full pointer-events-none ${className}`} />;
};
