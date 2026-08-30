import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Menu, X } from 'lucide-react';
import { ThemeToggle } from './ThemeProvider.jsx';

const NAV_LINKS = [
  { label: 'Discover', href: '/#discover' },
  { label: 'How It Works', href: '/#how-it-works' },
  { label: 'Evidence', href: '/#evidence' },
  { label: 'Research', to: '/research' },
  { label: 'Lab', to: '/app/analyze' },
  { label: 'Dashboard', to: '/app' },
];

/**
 * GlassHeader — Floating top nav for public routes only (landing, signin,
 * register, research). App routes (/app/*) use the Sidebar + layout/Header
 * instead. Anchor links use an absolute `/#id` path so they work correctly
 * from any public page, not just when already on the landing page.
 */
const GlassHeader = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const renderLink = (link, className, onClick) =>
    link.to ? (
      <Link key={link.label} to={link.to} onClick={onClick} className={className}>
        {link.label}
      </Link>
    ) : (
      <a key={link.label} href={link.href} onClick={onClick} className={className}>
        {link.label}
      </a>
    );

  return (
    <header className="fixed top-0 left-0 right-0 z-[1000]">
      <div className="mx-auto max-w-7xl px-4 pt-3">
        <div className="rounded-2xl px-6 py-3 bg-white/10 dark:bg-black/20 backdrop-blur-xl border border-white/20 dark:border-gray-700/30 shadow-glass transition-all duration-300">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <Link
              to="/"
              className="text-xl font-thin tracking-tight bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent hover:opacity-80 transition-opacity"
            >
              DrugForge
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden lg:flex items-center gap-1">
              {NAV_LINKS.map((link) =>
                renderLink(
                  link,
                  'px-3.5 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-cyan-500 dark:hover:text-violet-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500/50 rounded-lg'
                )
              )}
            </nav>

            {/* Right side: theme + auth */}
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link
                to="/signin"
                className="hidden lg:inline-flex px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
              >
                Sign In
              </Link>
              <Link
                to="/app/analyze"
                className="hidden lg:inline-flex px-5 py-2 text-sm font-medium text-white rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500 hover:shadow-glow-cyan transition-shadow duration-200"
              >
                Launch DrugForge
              </Link>

              {/* Mobile menu button */}
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={mobileMenuOpen}
                className="lg:hidden p-2 text-gray-600 dark:text-gray-400"
              >
                {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {/* Mobile Menu */}
          <AnimatePresence>
            {mobileMenuOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="lg:hidden overflow-hidden"
              >
                <div className="pt-4 pb-2 space-y-1 border-t border-white/10 dark:border-gray-700/20 mt-3">
                  {NAV_LINKS.map((link) =>
                    renderLink(link, 'block px-4 py-3 rounded-xl text-sm text-gray-600 dark:text-gray-400', () => setMobileMenuOpen(false))
                  )}
                  <div className="flex gap-2 pt-2">
                    <Link to="/signin" onClick={() => setMobileMenuOpen(false)} className="flex-1 text-center px-4 py-2.5 text-sm rounded-xl bg-white/10 dark:bg-black/10 text-gray-700 dark:text-gray-300">
                      Sign In
                    </Link>
                    <Link to="/app/analyze" onClick={() => setMobileMenuOpen(false)} className="flex-1 text-center px-4 py-2.5 text-sm font-medium text-white rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500">
                      Launch DrugForge
                    </Link>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
};

export default GlassHeader;
