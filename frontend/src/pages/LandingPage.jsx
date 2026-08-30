import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, useInView } from 'framer-motion';
import {
  Beaker, Brain, Shield, Zap,
  FlaskConical, Activity, Target, Pill, BarChart3, Microscope,
  ArrowRight, Clock,
} from 'lucide-react';

// ─── Premium UI Components ─────────────────────────────────
import { BentoGrid, BentoGridItem } from '../components/ui/bento-grid';
import { ShimmerButton, GhostShimmerButton } from '../components/ui/shimmer-button';
import { BorderBeam } from '../components/ui/border-beam';
import WebGLBackground from '../components/WebGLBackground';

// ─── Accent gradient (small "AI" brand pop, warm-neutral base) ────
// Light: clay → violet. Dark: violet → teal (close to the app's existing
// dark-mode brand accent). Reused everywhere a highlighted word/number needs
// the DrugForge "AI" signature without going back to a full aurora wash.
const ACCENT_GRADIENT =
  'bg-gradient-to-r from-clay-deep to-violet-600 dark:from-violet-400 dark:to-teal-400 bg-clip-text text-transparent';

// ─── Typewriter Hook ──────────────────────────────────────────
const useTypewriter = (words, typingSpeed = 120, deletingSpeed = 60, pauseMs = 2000) => {
  const [text, setText] = useState('');
  const [wordIndex, setWordIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const currentWord = words[wordIndex];
    const timeout = setTimeout(() => {
      if (!isDeleting) {
        setText(currentWord.slice(0, charIndex + 1));
        setCharIndex(prev => prev + 1);
        if (charIndex + 1 === currentWord.length) {
          setTimeout(() => setIsDeleting(true), pauseMs);
        }
      } else {
        setText(currentWord.slice(0, charIndex - 1));
        setCharIndex(prev => prev - 1);
        if (charIndex <= 1) {
          setIsDeleting(false);
          setWordIndex(prev => (prev + 1) % words.length);
        }
      }
    }, isDeleting ? deletingSpeed : typingSpeed);

    return () => clearTimeout(timeout);
  }, [charIndex, isDeleting, wordIndex, words, typingSpeed, deletingSpeed, pauseMs]);

  return text;
};

// ─── Animated Counter Hook ────────────────────────────────────
const useAnimatedCounter = (target, duration = 1800, startWhenVisible = true) => {
  const [count, setCount] = useState(0);
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-50px" });
  const started = useRef(false);

  useEffect(() => {
    if (!startWhenVisible || !inView || started.current) return;
    started.current = true;
    const start = performance.now();
    const tick = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [inView, target, duration, startWhenVisible]);

  return { count, ref };
};

// ─── Model Data ───────────────────────────────────────────────
const MODELS = [
  { name: 'Solubility (LogS)', icon: FlaskConical, desc: 'Predict aqueous solubility for drug-likeness assessment', color: 'cyan' },
  { name: 'BBB Permeability', icon: Shield, desc: 'Blood-brain barrier penetration classification', color: 'violet' },
  { name: 'Toxicity', icon: Activity, desc: 'Multi-endpoint toxicity risk profiling', color: 'rose' },
  { name: 'CYP3A4 Inhibition', icon: Pill, desc: 'Cytochrome P450 3A4 enzyme inhibition prediction', color: 'amber' },
  { name: 'Half-Life', icon: Clock, desc: 'Pharmacokinetic half-life estimation', color: 'teal' },
  { name: 'COX-2 Binding', icon: Target, desc: 'Cyclooxygenase-2 target binding affinity', color: 'emerald' },
  { name: 'HepG2 Cytotoxicity', icon: Microscope, desc: 'Hepatocyte cytotoxicity screening', color: 'sky' },
  { name: 'ACE2 Binding', icon: Brain, desc: 'ACE2 receptor binding prediction', color: 'violet' },
  { name: 'Binding Score', icon: BarChart3, desc: 'General protein-ligand binding affinity', color: 'cyan' },
];

const STATS = [
  { value: 9, label: 'AI Models', suffix: '', isNumber: true },
  { value: 2, label: 'Sec Inference', prefix: '< ', suffix: 's', isNumber: true },
  { value: 93, label: 'Avg. Accuracy', suffix: '%+', isNumber: true },
  { value: '∞', label: 'Predictions', isNumber: false },
];

// ─── Stat Card ────────────────────────────────────────────────
const StatCard = ({ stat, index }) => {
  const { count, ref } = useAnimatedCounter(stat.isNumber ? stat.value : 0, 1600);

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.9 + index * 0.1 }}
      className="relative group text-center px-6 py-5 rounded-2xl border border-paper-border/50 dark:border-white/[0.08] bg-white/70 dark:bg-white/[0.03] backdrop-blur-sm hover:border-clay/40 dark:hover:border-white/[0.15] transition-all duration-300"
    >
      <div className={`text-3xl md:text-4xl font-bold tabular-nums font-display ${ACCENT_GRADIENT}`}>
        {stat.isNumber ? `${stat.prefix || ''}${count}${stat.suffix}` : stat.value}
      </div>
      <div className="mt-1.5 text-[11px] tracking-[2px] text-ink-soft dark:text-gray-400 uppercase">
        {stat.label}
      </div>
      <div className="absolute bottom-0 w-1/2 h-px transition-opacity duration-300 -translate-x-1/2 opacity-0 left-1/2 bg-gradient-to-r from-transparent via-violet-500/40 to-transparent group-hover:opacity-100" />
    </motion.div>
  );
};

// ─── Section: Hero ────────────────────────────────────────────
const HeroSection = () => {
  const typedText = useTypewriter([
    'predict solubility',
    'screen for toxicity',
    'analyze drug targets',
    'assess BBB permeability',
    'evaluate binding affinity',
  ]);

  return (
    <section className="relative min-h-screen flex items-center overflow-hidden">
      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-32 pb-20 w-full">
        <div className="max-w-2xl">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium tracking-wide border border-clay/25 dark:border-violet-500/20 bg-white/60 dark:bg-black/30 backdrop-blur-md text-clay-deep dark:text-violet-300">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex w-full h-full rounded-full opacity-75 animate-ping bg-violet-400" />
                <span className="relative inline-flex w-2 h-2 rounded-full bg-violet-500" />
              </span>
              9 AI Models · Real-Time Predictions · Zero Code
            </span>
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="mt-8 font-display font-bold tracking-tight text-ink dark:text-white text-5xl sm:text-6xl lg:text-7xl leading-[1.05] [text-shadow:0_2px_24px_rgba(252,252,252,0.8)] dark:[text-shadow:0_2px_24px_rgba(17,24,39,0.85)]"
          >
            Predict Better
            <br />
            <span className={ACCENT_GRADIENT}>Molecules.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="mt-6 text-lg leading-relaxed text-ink-soft dark:text-gray-300"
          >
            Zero-code AI drug discovery. Paste a SMILES string, get instant ADMET
            predictions across <span className="font-semibold text-clay-deep dark:text-violet-400">9 trained models</span>.
          </motion.p>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.35 }}
            className="flex items-center h-10 mt-6"
          >
            <span className="text-xl font-medium sm:text-2xl">
              <span className={ACCENT_GRADIENT}>{typedText}</span>
              <span className="animate-pulse text-violet-500 dark:text-violet-400 ml-0.5">|</span>
            </span>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.45 }}
            className="flex flex-col items-center gap-4 mt-10 sm:flex-row sm:justify-start"
          >
            <Link to="/app/analyze">
              <ShimmerButton background="linear-gradient(135deg, #4D432D, #8B5CF6)">
                <Beaker className="w-5 h-5" />
                Open Lab Bench
                <ArrowRight className="w-5 h-5" />
              </ShimmerButton>
            </Link>
            <Link to="/app">
              <GhostShimmerButton>
                View Dashboard
              </GhostShimmerButton>
            </Link>
          </motion.div>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.5 }}
            className="mt-6 text-xs tracking-wide text-ink-soft/70 dark:text-gray-400"
          >
            Free to use · No sign-up required · Powered by Intel AI
            <span className="mx-2 text-paper-border dark:text-gray-700">·</span>
            Background: live COX-2 (PDB 1CX2) — move your cursor, scroll the page
          </motion.p>

          <div className="grid max-w-lg grid-cols-2 gap-4 mt-14 sm:grid-cols-4">
            {STATS.map((stat, i) => (
              <StatCard key={stat.label} stat={stat} index={i} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

// ─── Section: Models Bento Grid ───────────────────────────────
const ModelsSection = () => (
  <section className="relative px-4 mx-auto py-28 max-w-7xl" id="features">
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mb-16 text-center"
    >
      <span className="inline-flex items-center mb-6 px-3.5 py-1.5 rounded-full text-xs font-medium border border-clay/25 dark:border-violet-500/20 bg-white/60 dark:bg-black/30 backdrop-blur-md text-clay-deep dark:text-violet-300">
        <Beaker className="w-3 h-3 mr-1.5" />
        ADMET Prediction Suite
      </span>
      <h2 className="mb-5 font-display text-4xl font-bold text-ink md:text-5xl dark:text-white [text-shadow:0_2px_20px_rgba(252,252,252,0.9)] dark:[text-shadow:0_2px_20px_rgba(17,24,39,0.9)]">
        9 AI Models. <span className={ACCENT_GRADIENT}>One Platform.</span>
      </h2>
      <p className="max-w-2xl mx-auto text-lg leading-relaxed text-ink-soft dark:text-gray-300">
        From ADMET profiling to target binding — run every prediction from a single interface.
        Each model is trained on curated pharmaceutical datasets.
      </p>
    </motion.div>

    <BentoGrid>
      {MODELS.map((model, i) => (
        <BentoGridItem
          key={model.name}
          title={model.name}
          description={model.desc}
          accentColor={model.color}
          index={i}
          icon={<model.icon className={`w-6 h-6 text-${model.color}-400`} />}
        />
      ))}
    </BentoGrid>
  </section>
);

// ─── Section: How It Works ──────────────────────────────────
const HowItWorks = () => {
  const steps = [
    {
      num: '01',
      title: 'Paste SMILES',
      desc: 'Enter any valid SMILES notation — from aspirin to novel candidates.',
      colorFrom: '#4D432D',
      colorTo: '#8B5CF6',
    },
    {
      num: '02',
      title: 'Run Models',
      desc: 'Select individual models or run all 9 simultaneously in one click.',
      colorFrom: '#8B5CF6',
      colorTo: '#2DD4BF',
    },
    {
      num: '03',
      title: 'Get Insights',
      desc: 'Instant predictions with confidence scores, 3D visualization, and AI analysis.',
      colorFrom: '#2DD4BF',
      colorTo: '#4D432D',
    },
  ];

  return (
    <section className="relative max-w-5xl px-4 mx-auto py-28" id="how-it-works">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.6 }}
        className="mb-16 text-center"
      >
        <h2 className="mb-5 font-display text-4xl font-bold text-ink md:text-5xl dark:text-white [text-shadow:0_2px_20px_rgba(252,252,252,0.9)] dark:[text-shadow:0_2px_20px_rgba(17,24,39,0.9)]">
          Input Once. <span className={ACCENT_GRADIENT}>Analyze Everything.</span>
        </h2>
        <p className="max-w-lg mx-auto text-lg text-ink-soft dark:text-gray-300">
          Three steps from SMILES string to actionable drug discovery insights.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
        {steps.map((step, i) => (
          <motion.div
            key={step.num}
            initial={{ opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.15, duration: 0.6 }}
            className="relative group"
          >
            <div className="relative overflow-hidden rounded-2xl border border-paper-border/60 dark:border-white/[0.08] bg-white/85 dark:bg-white/[0.04] backdrop-blur-md p-8 h-full transition-all duration-300 hover:border-clay/40 dark:hover:border-white/[0.2]">
              <BorderBeam
                size={120}
                duration={8 + i * 2}
                delay={i * 2}
                colorFrom={step.colorFrom}
                colorTo={step.colorTo}
              />

              <span
                className="block mb-4 text-6xl font-bold opacity-15 bg-clip-text text-transparent bg-gradient-to-b"
                style={{ backgroundImage: `linear-gradient(to bottom, ${step.colorFrom}, ${step.colorTo})` }}
              >
                {step.num}
              </span>

              <h3 className="mb-3 text-xl font-semibold text-ink dark:text-white">
                {step.title}
              </h3>
              <p className="text-sm leading-relaxed text-ink-soft dark:text-gray-400">
                {step.desc}
              </p>
            </div>

            {i < 2 && (
              <div className="absolute z-10 hidden text-paper-border md:flex top-1/2 -right-5 dark:text-gray-600">
                <ArrowRight className="w-5 h-5" />
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </section>
  );
};

// ─── Section: CTA ─────────────────────────────────────────
const CTASection = () => (
  <section className="relative px-4 py-32 text-center">
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.7 }}
      className="relative max-w-3xl mx-auto"
    >
      <div className="relative overflow-hidden rounded-3xl border border-paper-border/60 dark:border-white/[0.08] bg-white/85 dark:bg-white/[0.04] backdrop-blur-md p-16">
        <BorderBeam size={250} duration={14} colorFrom="#4D432D" colorTo="#8B5CF6" />

        <h2 className="relative mb-5 font-display text-4xl font-bold text-ink md:text-5xl dark:text-white">
          Ready to accelerate your{' '}
          <span className={ACCENT_GRADIENT}>research</span>?
        </h2>
        <p className="relative max-w-xl mx-auto mb-10 text-lg leading-relaxed text-ink-soft dark:text-gray-300">
          Join researchers using DrugForge to make faster, data-driven decisions in drug discovery.
        </p>
        <div className="relative">
          <Link to="/app/analyze">
            <ShimmerButton background="linear-gradient(135deg, #4D432D, #8B5CF6)">
              Launch Lab Bench
              <ArrowRight className="w-5 h-5" />
            </ShimmerButton>
          </Link>
        </div>
      </div>
    </motion.div>
  </section>
);

// ─── Footer ─────────────────────────────────────────────
const GlassFooter = () => (
  <footer className="relative px-4 py-12 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-t border-paper-border/50 dark:border-white/[0.06]">
    <div className="flex flex-col items-center justify-between gap-6 mx-auto max-w-7xl md:flex-row">
      <div>
        <span className={`font-display text-xl font-bold ${ACCENT_GRADIENT}`}>
          DrugForge
        </span>
        <p className="mt-1 text-xs text-ink-soft dark:text-gray-400">
          AI-Powered Drug Discovery Platform
        </p>
      </div>
      <div className="flex gap-8 text-sm text-ink-soft dark:text-gray-400">
        <a href="#features" className="transition-colors duration-200 hover:text-clay-deep dark:hover:text-violet-400">Features</a>
        <Link to="/app" className="transition-colors duration-200 hover:text-clay-deep dark:hover:text-violet-400">Dashboard</Link>
        <Link to="/app/analyze" className="transition-colors duration-200 hover:text-clay-deep dark:hover:text-violet-400">Lab Bench</Link>
      </div>
      <p className="text-xs text-ink-soft dark:text-gray-400">
        © {new Date().getFullYear()} DrugForge. All rights reserved.
      </p>
    </div>
  </footer>
);

// ─── Main Landing Page ────────────────────────────────────────
const LandingPage = () => {
  return (
    <div className="relative overflow-hidden">
      <WebGLBackground className="fixed inset-0 -z-10 pointer-events-none" />
      <HeroSection />
      <ModelsSection />
      <HowItWorks />
      <CTASection />
      <GlassFooter />
    </div>
  );
};

export default LandingPage;
