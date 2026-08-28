import React from 'react';
import { motion } from 'framer-motion';

/**
 * GlassCard - Core UI component for the Glass Laboratory aesthetic
 * Features: Frosted glass effect, depth shadows, hover animations
 * 
 * @param {ReactNode} children - Card content
 * @param {string} className - Additional Tailwind classes
 * @param {boolean} hoverable - Enable hover lift effect (default: true)
 * @param {object} animation - Framer Motion variants
 * @param {function} onClick - Optional click handler
 */
const GlassCard = ({ 
  children, 
  className = '', 
  hoverable = true,
  hoverEffect,          // Gemini-style alias for hoverable
  animation = {},
  onClick,
  ...props 
}) => {
  // Support both prop names
  const isHoverable = hoverEffect !== undefined ? hoverEffect : hoverable;
  const defaultAnimation = {
    initial: { opacity: 0, y: 20, scale: 0.95 },
    animate: { opacity: 1, y: 0, scale: 1 },
    exit: { opacity: 0, y: -20, scale: 0.95 },
    transition: { duration: 0.4, ease: [0.23, 1, 0.32, 1] }
  };

  const mergedAnimation = { ...defaultAnimation, ...animation };

  const hoverClasses = isHoverable 
    ? 'hover:bg-white/20 hover:-translate-y-1 hover:shadow-2xl dark:hover:bg-white/10' 
    : '';

  return (
    <motion.div
      className={`
        relative overflow-hidden rounded-2xl
        border border-white/20 dark:border-gray-700/30
        bg-white/10 dark:bg-black/20
        backdrop-blur-xl
        shadow-xl
        transition-all duration-300
        ${hoverClasses}
        ${onClick ? 'cursor-pointer' : ''}
        ${className}
      `}
      onClick={onClick}
      whileHover={isHoverable ? { y: -5, boxShadow: '0 20px 40px -10px rgba(45, 212, 191, 0.2)' } : {}}
      {...mergedAnimation}
      {...props}
    >
      {/* Subtle gradient overlay for depth */}
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
      
      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>

      {/* Glow effect on hover */}
      {isHoverable && (
        <div className="absolute inset-0 opacity-0 hover:opacity-100 transition-opacity duration-300 pointer-events-none">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 via-transparent to-violet-500/10" />
        </div>
      )}
    </motion.div>
  );
};

/**
 * GlassPanel - Larger glass surface for main content areas
 */
export const GlassPanel = ({ children, className = '', ...props }) => {
  return (
    <GlassCard
      className={`p-8 ${className}`}
      hoverable={false}
      {...props}
    >
      {children}
    </GlassCard>
  );
};

/**
 * GlassButton - Button with glass aesthetic
 */
export const GlassButton = ({ 
  children, 
  variant = 'primary', 
  className = '',
  disabled = false,
  ...props 
}) => {
  const variants = {
    primary: 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300 border-cyan-500/30 hover:bg-cyan-500/30',
    secondary: 'bg-violet-500/20 text-violet-700 dark:text-violet-300 border-violet-500/30 hover:bg-violet-500/30',
    success: 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/30',
    danger: 'bg-rose-500/20 text-rose-700 dark:text-rose-300 border-rose-500/30 hover:bg-rose-500/30',
    ghost: 'bg-white/10 text-gray-700 dark:text-gray-300 border-white/20 hover:bg-white/20',
  };

  return (
    <motion.button
      className={`
        relative px-6 py-3 rounded-xl
        border backdrop-blur-md
        font-medium transition-all duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]}
        ${className}
      `}
      whileHover={!disabled ? { scale: 1.02, y: -2 } : {}}
      whileTap={!disabled ? { scale: 0.98 } : {}}
      disabled={disabled}
      {...props}
    >
      {children}
    </motion.button>
  );
};

/**
 * GlassInput - Input with glass aesthetic
 */
export const GlassInput = ({ className = '', icon, ...props }) => {
  return (
    <div className="relative">
      {icon && (
        <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 dark:text-gray-400">
          {icon}
        </div>
      )}
      <input
        className={`
          w-full px-4 py-3 rounded-xl
          ${icon ? 'pl-11' : ''}
          bg-white/30 dark:bg-black/30
          backdrop-blur-md
          border border-white/20 dark:border-gray-700/30
          text-gray-900 dark:text-gray-100
          placeholder-gray-500 dark:placeholder-gray-400
          focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500/50
          transition-all duration-200
          ${className}
        `}
        {...props}
      />
    </div>
  );
};

/**
 * GlassBadge - Small badge with glass effect
 */
export const GlassBadge = ({ children, variant = 'default', className = '' }) => {
  const variants = {
    default: 'bg-white/20 text-gray-700 dark:text-gray-300',
    primary: 'bg-cyan-500/20 text-cyan-700 dark:text-cyan-300',
    success: 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300',
    warning: 'bg-amber-500/20 text-amber-700 dark:text-amber-300',
    danger: 'bg-rose-500/20 text-rose-700 dark:text-rose-300',
  };

  return (
    <span className={`
      inline-flex items-center px-3 py-1 rounded-full
      text-xs font-medium backdrop-blur-md
      border border-white/20 dark:border-gray-700/30
      ${variants[variant]}
      ${className}
    `}>
      {children}
    </span>
  );
};

export default GlassCard;
