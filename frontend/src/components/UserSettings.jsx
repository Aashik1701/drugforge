import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Palette, Key, Bell, Shield, LogOut, Moon, Sun, Monitor } from 'lucide-react';
import GlassCard, { GlassPanel, GlassButton, GlassInput, GlassBadge } from './ui/GlassCard';
import { useDrugForge } from '../context/DrugForgeContext';
import { useAuth } from '../context/AuthContext';

const UserSettings = () => {
  const { isDarkMode, toggleTheme } = useDrugForge();
  const { user } = useAuth();
  const [activeSection, setActiveSection] = useState('profile');

  const sections = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'appearance', label: 'Appearance', icon: Palette },
    { id: 'api-keys', label: 'API Keys', icon: Key },
    { id: 'notifications', label: 'Notifications', icon: Bell },
  ];

  return (
    <div className="min-h-screen p-4 md:p-8 pb-24">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-8"
        >
          <h1 className="text-3xl font-thin text-gray-800 dark:text-gray-100">
            <span className="text-cyan-500">Settings</span>
          </h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">
            Manage your account and preferences.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {/* Sidebar Nav */}
          <div className="md:col-span-1">
            <GlassCard className="p-3" hoverable={false}>
              <nav className="space-y-1">
                {sections.map(sec => (
                  <button
                    key={sec.id}
                    onClick={() => setActiveSection(sec.id)}
                    className={`
                      w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm
                      transition-all duration-200
                      ${activeSection === sec.id
                        ? 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-white/10 dark:hover:bg-black/10'
                      }
                    `}
                  >
                    <sec.icon className="w-4 h-4" />
                    {sec.label}
                  </button>
                ))}
              </nav>
            </GlassCard>
          </div>

          {/* Content */}
          <div className="md:col-span-3">
            {activeSection === 'profile' && <ProfileSection />}
            {activeSection === 'appearance' && <AppearanceSection isDarkMode={isDarkMode} toggleTheme={toggleTheme} />}
            {activeSection === 'api-keys' && <APIKeysSection />}
            {activeSection === 'notifications' && <NotificationsSection />}
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── Profile Section ──────────────────────────────────────────
const ProfileSection = () => {
  const { user, updateProfile } = useAuth();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [profile, setProfile] = useState({
    name: user?.name || '',
    email: user?.email || '',
    institution: user?.institution || '',
  });

  const handleChange = (field, value) => {
    setProfile(prev => ({ ...prev, [field]: value }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    await updateProfile(profile);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <GlassPanel className="p-8">
      <h2 className="text-xl font-medium text-gray-800 dark:text-gray-200 mb-6">Profile</h2>
      
      {/* Avatar */}
      <div className="flex items-center gap-6 mb-8">
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-cyan-500 to-violet-500 flex items-center justify-center text-white text-2xl font-light">
          {profile.name ? profile.name[0].toUpperCase() : 'U'}
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{profile.email}</p>
        </div>
      </div>

      <div className="space-y-5 max-w-lg">
        <div>
          <label className="block text-sm text-gray-500 dark:text-gray-400 mb-2">Full Name</label>
          <GlassInput
            value={profile.name}
            onChange={(e) => handleChange('name', e.target.value)}
            placeholder="Dr. Jane Doe"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-500 dark:text-gray-400 mb-2">Email</label>
          <GlassInput
            type="email"
            value={profile.email}
            onChange={(e) => handleChange('email', e.target.value)}
            placeholder="jane@university.edu"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-500 dark:text-gray-400 mb-2">Institution</label>
          <GlassInput
            value={profile.institution}
            onChange={(e) => handleChange('institution', e.target.value)}
            placeholder="MIT, Stanford, etc."
          />
        </div>
        <GlassButton variant="primary" className="mt-4" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Changes'}
        </GlassButton>
      </div>
    </GlassPanel>
  );
};

// ─── Appearance Section ───────────────────────────────────────
const AppearanceSection = ({ isDarkMode, toggleTheme }) => {
  const themes = [
    { id: 'light', label: 'Light', icon: Sun, desc: 'Classic light mode with soft glass effects' },
    { id: 'dark', label: 'Dark', icon: Moon, desc: 'Deep dark mode for low-light environments' },
  ];

  return (
    <GlassPanel className="p-8">
      <h2 className="text-xl font-medium text-gray-800 dark:text-gray-200 mb-6">Appearance</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {themes.map(theme => {
          const isActive = (theme.id === 'dark') === isDarkMode;
          return (
            <button
              key={theme.id}
              onClick={() => {
                if (!isActive) toggleTheme();
              }}
              className={`
                p-6 rounded-xl text-left transition-all duration-200
                border backdrop-blur-md
                ${isActive
                  ? 'bg-cyan-500/15 border-cyan-500/30 ring-2 ring-cyan-500/20'
                  : 'bg-white/5 dark:bg-black/5 border-white/20 dark:border-gray-700/20 hover:bg-white/10'
                }
              `}
            >
              <theme.icon className={`w-8 h-8 mb-3 ${isActive ? 'text-cyan-500' : 'text-gray-400'}`} />
              <h3 className="font-medium text-gray-800 dark:text-gray-200 mb-1">{theme.label}</h3>
              <p className="text-xs text-gray-500 dark:text-gray-400">{theme.desc}</p>
            </button>
          );
        })}
      </div>
    </GlassPanel>
  );
};

// ─── API Keys Section ─────────────────────────────────────────
const APIKeysSection = () => {
  const [apiKey, setApiKey] = useState('');

  return (
    <GlassPanel className="p-8">
      <h2 className="text-xl font-medium text-gray-800 dark:text-gray-200 mb-2">API Keys</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        Manage your API access tokens for programmatic access.
      </p>

      <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 mb-6">
        <p className="text-sm text-amber-700 dark:text-amber-300">
          API access is available on the Researcher plan and above.
        </p>
      </div>

      <div className="space-y-4 max-w-lg">
        <div>
          <label className="block text-sm text-gray-500 dark:text-gray-400 mb-2">API Key</label>
          <GlassInput
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            icon={<Key className="w-4 h-4" />}
          />
        </div>
        <GlassButton variant="primary">Generate New Key</GlassButton>
      </div>
    </GlassPanel>
  );
};

// ─── Notifications Section ────────────────────────────────────
const NotificationsSection = () => {
  const [prefs, setPrefs] = useState({
    predictions: true,
    batch: true,
    updates: false,
  });

  const toggle = (key) => setPrefs(prev => ({ ...prev, [key]: !prev[key] }));

  const options = [
    { key: 'predictions', label: 'Prediction Results', desc: 'Get notified when predictions complete' },
    { key: 'batch', label: 'Batch Processing', desc: 'Alerts when batch jobs finish' },
    { key: 'updates', label: 'Product Updates', desc: 'New features and model updates' },
  ];

  return (
    <GlassPanel className="p-8">
      <h2 className="text-xl font-medium text-gray-800 dark:text-gray-200 mb-6">Notifications</h2>
      <div className="space-y-4">
        {options.map(opt => (
          <div
            key={opt.key}
            className="flex items-center justify-between p-4 rounded-xl bg-white/5 dark:bg-black/5"
          >
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">{opt.label}</h4>
              <p className="text-xs text-gray-500 dark:text-gray-400">{opt.desc}</p>
            </div>
            <button
              onClick={() => toggle(opt.key)}
              className={`
                w-12 h-7 rounded-full relative transition-all duration-200
                ${prefs[opt.key]
                  ? 'bg-cyan-500'
                  : 'bg-gray-300 dark:bg-gray-600'
                }
              `}
            >
              <span className={`
                absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform duration-200
                ${prefs[opt.key] ? 'translate-x-5' : 'translate-x-0.5'}
              `} />
            </button>
          </div>
        ))}
      </div>
    </GlassPanel>
  );
};

export default UserSettings;
