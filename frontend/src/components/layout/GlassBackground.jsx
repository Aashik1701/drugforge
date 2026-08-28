import React, { useEffect, useRef } from 'react';
import { useDrugForge } from '../../context/DrugForgeContext';

/**
 * GlassBackground - Animated mesh gradient background
 * Creates a slowly moving, multi-colored gradient that serves as the
 * backdrop for the glass UI elements
 */
const GlassBackground = ({ children }) => {
  const { isDarkMode } = useDrugForge();
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;
    let time = 0;

    // Set canvas size
    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Gradient orb class
    class GradientOrb {
      constructor(color, x, y, radius) {
        this.color = color;
        this.baseX = x;
        this.baseY = y;
        this.x = x;
        this.y = y;
        this.radius = radius;
        this.angle = Math.random() * Math.PI * 2;
        this.speed = 0.0005 + Math.random() * 0.0005;
        this.drift = 50 + Math.random() * 100;
      }

      update(time) {
        this.angle += this.speed;
        this.x = this.baseX + Math.cos(this.angle) * this.drift;
        this.y = this.baseY + Math.sin(this.angle) * this.drift;
      }

      draw(ctx) {
        const gradient = ctx.createRadialGradient(
          this.x, this.y, 0,
          this.x, this.y, this.radius
        );
        gradient.addColorStop(0, this.color);
        gradient.addColorStop(1, 'transparent');
        
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }
    }

    // Create orbs with different colors for light/dark mode
    let orbs;
    const createOrbs = () => {
      if (isDarkMode) {
        orbs = [
          new GradientOrb('rgba(6, 182, 212, 0.15)', canvas.width * 0.2, canvas.height * 0.3, 400),    // Cyan
          new GradientOrb('rgba(139, 92, 246, 0.12)', canvas.width * 0.7, canvas.height * 0.4, 450),   // Violet
          new GradientOrb('rgba(20, 184, 166, 0.1)', canvas.width * 0.5, canvas.height * 0.7, 500),    // Teal
          new GradientOrb('rgba(59, 130, 246, 0.08)', canvas.width * 0.8, canvas.height * 0.2, 350),   // Blue
        ];
      } else {
        orbs = [
          new GradientOrb('rgba(224, 242, 254, 0.6)', canvas.width * 0.2, canvas.height * 0.3, 400),   // Light Sky
          new GradientOrb('rgba(243, 232, 255, 0.5)', canvas.width * 0.7, canvas.height * 0.4, 450),   // Light Violet
          new GradientOrb('rgba(204, 251, 241, 0.5)', canvas.width * 0.5, canvas.height * 0.7, 500),   // Teal
          new GradientOrb('rgba(186, 230, 253, 0.4)', canvas.width * 0.8, canvas.height * 0.2, 350),   // Light Blue
        ];
      }
    };
    createOrbs();

    // Animation loop
    const animate = () => {
      time += 1;
      
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Fill with base color
      ctx.fillStyle = isDarkMode ? '#0a0a0a' : '#f8fafc';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // Update and draw orbs
      ctx.globalCompositeOperation = 'screen';
      orbs.forEach(orb => {
        orb.update(time);
        orb.draw(ctx);
      });
      ctx.globalCompositeOperation = 'source-over';
      
      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    // Cleanup
    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, [isDarkMode]);

  return (
    <div className="relative min-h-screen w-full overflow-hidden">
      {/* Animated canvas background */}
      <canvas
        ref={canvasRef}
        className="fixed inset-0 -z-10"
        style={{ filter: 'blur(60px)' }}
      />
      
      {/* Static gradient fallback for better performance on low-end devices */}
      <div className={`
        fixed inset-0 -z-20
        ${isDarkMode 
          ? 'bg-gradient-to-br from-gray-900 via-slate-900 to-gray-900' 
          : 'bg-gradient-to-br from-sky-100 via-violet-50 to-teal-100'
        }
      `} />
      
      {/* Subtle grain texture overlay */}
      <div 
        className="fixed inset-0 -z-10 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' /%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' /%3E%3C/svg%3E")`,
          backgroundRepeat: 'repeat',
        }}
      />
      
      {/* Content */}
      <div className="relative z-0">
        {children}
      </div>
    </div>
  );
};

/**
 * StaticGlassBackground - Fallback without canvas animation
 * Use this if you need better performance or SSR compatibility
 */
export const StaticGlassBackground = ({ children }) => {
  const { isDarkMode } = useDrugForge();

  return (
    <div className="relative min-h-screen w-full overflow-hidden">
      {/* Static gradient background */}
      <div className={`
        fixed inset-0 -z-10
        ${isDarkMode 
          ? 'bg-[radial-gradient(ellipse_at_top_left,_var(--tw-gradient-stops))] from-cyan-900/20 via-slate-900 to-violet-900/20' 
          : 'bg-[radial-gradient(ellipse_at_top_left,_var(--tw-gradient-stops))] from-sky-200 via-violet-100 to-teal-200'
        }
      `} />
      
      {/* Animated gradient orbs using CSS */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className={`
          absolute top-1/4 left-1/4 w-96 h-96 rounded-full blur-3xl animate-pulse
          ${isDarkMode ? 'bg-cyan-500/10' : 'bg-sky-300/40'}
        `} style={{ animationDuration: '8s' }} />
        <div className={`
          absolute top-1/3 right-1/4 w-[30rem] h-[30rem] rounded-full blur-3xl animate-pulse
          ${isDarkMode ? 'bg-violet-500/10' : 'bg-violet-300/40'}
        `} style={{ animationDuration: '12s', animationDelay: '2s' }} />
        <div className={`
          absolute bottom-1/4 left-1/2 w-[28rem] h-[28rem] rounded-full blur-3xl animate-pulse
          ${isDarkMode ? 'bg-teal-500/10' : 'bg-teal-300/40'}
        `} style={{ animationDuration: '10s', animationDelay: '4s' }} />
      </div>
      
      {/* Grain texture */}
      <div 
        className="fixed inset-0 -z-10 opacity-[0.015] pointer-events-none"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' /%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' /%3E%3C/svg%3E")`,
          backgroundRepeat: 'repeat',
        }}
      />
      
      {/* Content */}
      <div className="relative z-0">
        {children}
      </div>
    </div>
  );
};

export default GlassBackground;
