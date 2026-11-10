'use client';
import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import ThemeToggle from './ThemeToggle';

const LINKS = [
  { id: 'replay', label: 'Replay' },
  { id: 'console', label: 'Tower console' },
  { id: 'gnani', label: 'Gnani models' },
  { id: 'results', label: 'Results' },
  { id: 'how', label: 'How it works' },
  { id: 'experiments', label: 'Experiments' },
  { id: 'limits', label: 'Limits' },
];

/** Sticky top bar. The underline follows the section you are reading (scroll-spy). */
export default function Nav() {
  const [active, setActive] = useState('');
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: '-45% 0px -50% 0px' },
    );
    LINKS.forEach((l) => { const el = document.getElementById(l.id); if (el) io.observe(el); });
    return () => { window.removeEventListener('scroll', onScroll); io.disconnect(); };
  }, []);
  return (
    <header className={`sticky top-0 z-40 border-b transition-colors ${scrolled ? 'border-line bg-ink/85 backdrop-blur' : 'border-transparent'}`}>
      <nav aria-label="Sections" className="mx-auto flex h-14 max-w-page items-center gap-4 px-4 sm:px-6">
        <a href="#top" className="font-mono text-sm font-semibold tracking-[0.12em]">SENTINEL<span className="text-red">-V</span></a>
        <ul className="ml-auto hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <li key={l.id} className="relative">
              <a href={`#${l.id}`} aria-current={active === l.id ? 'true' : undefined}
                className={`block px-3 py-2 text-[13px] ${active === l.id ? 'text-text' : 'text-dim hover:text-text'}`}>
                {l.label}
              </a>
              {active === l.id && (
                <motion.span layoutId="nav-underline" className="absolute inset-x-3 -bottom-px h-0.5 rounded bg-signal" />
              )}
            </li>
          ))}
        </ul>
        <div className="ml-auto md:ml-2"><ThemeToggle /></div>
      </nav>
    </header>
  );
}
