import React from 'react';
import { Link } from 'react-router-dom';
import { FlaskConical, Home, ArrowRight } from 'lucide-react';

/**
 * NotFound - 404 page (Glass Laboratory theme)
 */
const NotFound = () => {
  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] px-4 py-12">
      <div className="max-w-lg mx-auto text-center">
        {/* Animated 404 */}
        <h1 className="mb-4 font-thin text-transparent text-8xl bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text">
          404
        </h1>

        <FlaskConical className="w-16 h-16 mx-auto mb-6 text-cyan-500/40" />

        <h2 className="mb-3 text-2xl font-medium text-gray-800 dark:text-gray-200">
          Compound Not Found
        </h2>
        <p className="mb-8 text-gray-500 dark:text-gray-400">
          The page you're looking for doesn't exist or has been moved to a different lab.
        </p>

        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            to="/"
            className="inline-flex items-center gap-2 px-6 py-3 font-medium text-white transition-shadow duration-200 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500 hover:shadow-glow-cyan"
          >
            <Home className="w-4 h-4" />
            Back to Home
          </Link>
          <Link
            to="/app/analyze"
            className="inline-flex items-center gap-2 px-6 py-3 text-gray-700 transition-all duration-200 border rounded-xl border-white/20 dark:border-gray-700/30 bg-white/10 dark:bg-black/10 backdrop-blur-md dark:text-gray-300 hover:bg-white/20 dark:hover:bg-black/20"
          >
            Open Lab Bench
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </div>
  );
};

export default NotFound;
