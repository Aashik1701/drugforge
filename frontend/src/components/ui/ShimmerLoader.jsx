import React from 'react';

/**
 * ShimmerLoader - Skeleton loading placeholder with shimmer animation
 * Replaces spinners per the Glass Laboratory spec
 */

const shimmerBase = `
  relative overflow-hidden
  bg-white/10 dark:bg-white/5
  rounded-xl
  before:absolute before:inset-0
  before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent
  before:animate-shimmer
`;

export const ShimmerBlock = ({ className = '', ...props }) => (
  <div className={`${shimmerBase} ${className}`} {...props} />
);

export const ShimmerText = ({ lines = 3, className = '' }) => (
  <div className={`space-y-3 ${className}`}>
    {Array.from({ length: lines }).map((_, i) => (
      <ShimmerBlock
        key={i}
        className="h-4"
        style={{ width: i === lines - 1 ? '60%' : '100%' }}
      />
    ))}
  </div>
);

export const ShimmerCard = ({ className = '' }) => (
  <div className={`
    p-6 rounded-2xl
    bg-white/10 dark:bg-black/20
    backdrop-blur-xl
    border border-white/20 dark:border-gray-700/30
    ${className}
  `}>
    <ShimmerBlock className="w-12 h-12 mb-4 rounded-lg" />
    <ShimmerBlock className="w-2/3 h-6 mb-3" />
    <ShimmerText lines={2} />
  </div>
);

export const ShimmerTable = ({ rows = 5, cols = 4 }) => (
  <div className="space-y-2">
    {/* Header */}
    <div className="flex gap-4 p-3">
      {Array.from({ length: cols }).map((_, i) => (
        <ShimmerBlock key={i} className="flex-1 h-4" />
      ))}
    </div>
    {/* Rows */}
    {Array.from({ length: rows }).map((_, r) => (
      <div key={r} className="flex gap-4 p-3 rounded-lg bg-white/5 dark:bg-black/5">
        {Array.from({ length: cols }).map((_, c) => (
          <ShimmerBlock key={c} className="flex-1 h-4" />
        ))}
      </div>
    ))}
  </div>
);

export default ShimmerBlock;
