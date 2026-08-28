import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Menu, X } from 'lucide-react';
import { ThemeToggle } from './ThemeProvider.jsx';

/**
 * GlassHeader — Floating top nav for public routes only (landing, signin, register).
 * App routes (/app/*) use the Sidebar + layout/Header instead.
 */
const GlassHeader = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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

            {/* Desktop Nav — public page anchors */}
            <nav className="hidden md:flex items-center gap-1">
              <a href="#features" className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-cyan-500 transition-colors">
                Features
              </a>
              <a href="#pricing" className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-cyan-500 transition-colors">
                Pricing
              </a>
            </nav>

            {/* Right side: theme + auth */}
            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link
                to="/signin"
                className="hidden md:inline-flex px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors"
              >
                Sign In
              </Link>
              <Link
                to="/app"
                className="hidden md:inline-flex px-5 py-2 text-sm font-medium text-white rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500 hover:shadow-glow-cyan transition-shadow duration-200"
              >
                Get Started
              </Link>

              {/* Mobile menu button */}
              <button
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                className="md:hidden p-2 text-gray-600 dark:text-gray-400"
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
                className="md:hidden overflow-hidden"
              >
                <div className="pt-4 pb-2 space-y-1 border-t border-white/10 dark:border-gray-700/20 mt-3">
                  <a href="#features" onClick={() => setMobileMenuOpen(false)} className="block px-4 py-3 rounded-xl text-sm text-gray-600 dark:text-gray-400">
                    Features
                  </a>
                  <a href="#pricing" onClick={() => setMobileMenuOpen(false)} className="block px-4 py-3 rounded-xl text-sm text-gray-600 dark:text-gray-400">
                    Pricing
                  </a>
                  <div className="flex gap-2 pt-2">
                    <Link to="/signin" onClick={() => setMobileMenuOpen(false)} className="flex-1 text-center px-4 py-2.5 text-sm rounded-xl bg-white/10 dark:bg-black/10 text-gray-700 dark:text-gray-300">
                      Sign In
                    </Link>
                    <Link to="/app" onClick={() => setMobileMenuOpen(false)} className="flex-1 text-center px-4 py-2.5 text-sm font-medium text-white rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500">
                      Get Started
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
