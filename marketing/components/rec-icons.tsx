// Íconos de línea de /a-donde-ir/, en currentColor (sin hex, design.md §2).

const base = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, 'aria-hidden': true } as const;

export function Sliders() {
  return (
    <svg {...base}>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" strokeLinecap="round" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </svg>
  );
}

export function Locate() {
  return (
    <svg {...base}>
      <circle cx="12" cy="12" r="6.5" />
      <circle cx="12" cy="12" r="2" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" strokeLinecap="round" />
    </svg>
  );
}

export function Send() {
  return (
    <svg {...base} strokeWidth={2}>
      <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function People() {
  return (
    <svg {...base}>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 19.5c.6-3.2 3-5 6-5s5.4 1.8 6 5" strokeLinecap="round" />
      <path d="M15.5 5.3a3 3 0 0 1 0 5.4M17.5 14.8c1.8.6 3 2.2 3.4 4.7" strokeLinecap="round" />
    </svg>
  );
}

export function Popcorn() {
  return (
    <svg {...base}>
      <path d="M5.5 10h13l-1.6 10.5H7.1L5.5 10Z" strokeLinejoin="round" />
      <path d="M9.5 10l.6 10.5M14.5 10l-.6 10.5" />
      <path d="M6 10a2.5 2.5 0 0 1 2.2-4 2.8 2.8 0 0 1 5-1.2 2.5 2.5 0 0 1 4.6 1.9A2.2 2.2 0 0 1 18 10" strokeLinecap="round" />
    </svg>
  );
}

export function Calendar() {
  return (
    <svg {...base}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" strokeLinecap="round" />
    </svg>
  );
}

export function Wallet() {
  return (
    <svg {...base}>
      <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3" strokeLinejoin="round" />
      <rect x="4" y="8" width="16.5" height="11.5" rx="2" />
      <circle cx="16" cy="13.8" r="1.1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function Close() {
  return (
    <svg {...base} strokeWidth={2}>
      <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
    </svg>
  );
}

export function Pin() {
  return (
    <svg {...base}>
      <path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21Z" strokeLinejoin="round" />
      <circle cx="12" cy="9.8" r="2.3" />
    </svg>
  );
}
