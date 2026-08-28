import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Bell, Sun, Moon } from 'lucide-react';
import { useDrugForge } from '../../context/DrugForgeContext';
import { useAuth } from '../../context/AuthContext';

const Header = () => {
  const { state, setTheme } = useDrugForge();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isDarkMode = state.theme === 'dark';
  const [query, setQuery] = useState('');

  const toggleTheme = () => setTheme(isDarkMode ? 'light' : 'dark');

  const handleSearch = useCallback((e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    navigate(`/app/analyze?smiles=${encodeURIComponent(q)}`);
    setQuery('');
  }, [query, navigate]);

  // Compute user initials from auth context
  const initials = user?.name
    ? user.name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : 'U';

  return (
    <header className="flex items-center justify-between h-16 mb-6">
      
      {/* Omnibox Trigger */}
      <div className="flex-1 max-w-xl">
        <form onSubmit={handleSearch} className="relative group">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-slate-400 group-hover:text-bio-teal transition-colors" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="block w-full pl-10 pr-3 py-2.5 border border-white/20 rounded-xl leading-5 bg-white/10 dark:bg-black/20 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-bio-teal/50 focus:border-bio-teal/50 transition-all backdrop-blur-md shadow-sm hover:shadow-md"
            placeholder="Paste SMILES and press Enter... (Cmd+K)"
          />
        </form>
      </div>

      {/* Right Actions */}
      <div className="ml-4 flex items-center space-x-4">
        {/* Theme Toggle */}
        <button 
          onClick={toggleTheme}
          className="p-2 rounded-full hover:bg-white/20 transition-colors text-slate-600 dark:text-slate-300"
          aria-label={`Switch to ${isDarkMode ? 'light' : 'dark'} mode`}
        >
          {isDarkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>

        {/* Notifications */}
        <button className="p-2 rounded-full hover:bg-white/20 transition-colors text-slate-600 dark:text-slate-300 relative">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-rose-500 rounded-full animate-pulse" />
        </button>

        {/* User Avatar */}
        <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-bio-teal to-bio-violet p-[2px] cursor-pointer hover:shadow-lg hover:shadow-bio-violet/20 transition-all">
          <div className="h-full w-full rounded-full bg-white dark:bg-slate-900 flex items-center justify-center">
            <span className="font-bold text-xs text-transparent bg-clip-text bg-gradient-to-r from-bio-teal to-bio-violet">
              {initials}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
