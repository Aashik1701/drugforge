import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, useInView } from 'framer-motion';
import {
  Beaker, Brain, Shield, Zap, Check,
  FlaskConical, Activity, Target, Pill, BarChart3, Microscope,
  ArrowRight, Star, Clock, Sparkles, ChevronDown, Mouse,
} from 'lucide-react';

// ─── Premium UI Components ─────────────────────────────────
import { AuroraBackground } from '../components/ui/aurora-background';
import { BentoGrid, BentoGridItem } from '../components/ui/bento-grid';
import { ShimmerButton, GhostShimmerButton } from '../components/ui/shimmer-button';
import { BorderBeam } from '../components/ui/border-beam';
import { GlassBadge } from '../components/ui/GlassCard';
import { FloatingMolecules } from '../components/ui/floating-molecules';

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

const PRICING_PLANS = [
  {
    name: 'Student',
    price: 'Free',
    period: '',
    features: ['3 models access', '50 predictions / month', 'Basic molecular viewer', 'Community support'],
    cta: 'Start Free',
    popular: false,
  },
  {
    name: 'Researcher',
    price: '$29',
    period: '/month',
    features: ['All 9 models', 'Unlimited predictions', 'Batch processing (CSV)', 'PDF report export', 'Priority support'],
    cta: 'Start Trial',
    popular: true,
  },
  {
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    features: ['Everything in Researcher', 'On-premise deployment', 'Custom model training', 'SSO & SAML', 'Dedicated account manager'],
    cta: 'Contact Sales',
    popular: false,
  },
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
      className="relative group text-center px-6 py-5 rounded-2xl border border-white/[0.06] bg-white/[0.03] backdrop-blur-sm hover:border-white/[0.15] transition-all duration-300"
    >
      <div className="text-3xl font-bold text-transparent md:text-4xl bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text tabular-nums">
        {stat.isNumber ? `${stat.prefix || ''}${count}${stat.suffix}` : stat.value}
      </div>
      <div className="mt-1.5 text-[11px] tracking-[2px] text-gray-500 dark:text-gray-400 uppercase">
        {stat.label}
      </div>
      {/* Subtle bottom glow on hover */}
      <div className="absolute bottom-0 w-1/2 h-px transition-opacity duration-300 -translate-x-1/2 opacity-0 left-1/2 bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent group-hover:opacity-100" />
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
    <AuroraBackground className="flex items-center justify-center min-h-screen px-4 pt-24 pb-32">
      {/* Floating molecular decorations */}
      <FloatingMolecules />

      <div className="relative z-10 max-w-5xl mx-auto text-center">
        {/* Badge */}
        <motion.div
          initial={{ opacity: 0, y: 20, filter: 'blur(10px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ duration: 0.6 }}
        >
          <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium tracking-wide border border-cyan-500/20 bg-cyan-500/[0.08] text-cyan-600 dark:text-cyan-400 backdrop-blur-sm">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex w-full h-full rounded-full opacity-75 animate-ping bg-cyan-400" />
              <span className="relative inline-flex w-2 h-2 rounded-full bg-cyan-500" />
            </span>
            9 AI Models · Real-Time Predictions · Zero Code
          </span>
        </motion.div>

        {/* Title with glow */}
        <motion.div
          initial={{ opacity: 0, y: 30, filter: 'blur(12px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ duration: 0.9, delay: 0.15 }}
          className="relative mt-10 mb-6"
        >
          {/* Title glow */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none" aria-hidden="true">
            <span className="text-6xl font-thin text-transparent md:text-8xl lg:text-9xl bg-gradient-to-r from-cyan-400 via-violet-400 to-teal-400 bg-clip-text opacity-20 blur-2xl">
              DrugForge
            </span>
          </div>
          <h1 className="relative text-6xl font-thin tracking-tight md:text-8xl lg:text-9xl">
            <span className="text-transparent bg-gradient-to-r from-cyan-400 via-violet-400 to-teal-400 bg-clip-text">
              DrugForge
            </span>
          </h1>
        </motion.div>

        {/* Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 20, filter: 'blur(10px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="max-w-2xl mx-auto mb-4 text-lg font-light leading-relaxed text-gray-500 md:text-xl dark:text-gray-400"
        >
          Zero-code AI drug discovery. Paste a SMILES string,
          get instant ADMET predictions across <span className="font-normal text-cyan-500 dark:text-cyan-400">9 trained models</span>.
        </motion.p>

        {/* Typewriter */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="flex items-center justify-center h-14 mb-14"
        >
          <div className="relative px-6 py-2">
            {/* Code-like wrapper */}
            <span className="mr-1 font-mono text-lg text-gray-400/50 dark:text-gray-600"></span>
            <span className="text-2xl font-light md:text-3xl">
              <span className="text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text">
                {typedText}
              </span>
              <span className="animate-pulse text-violet-400 ml-0.5 font-light">|</span>
            </span>
          </div>
        </motion.div>

        {/* CTAs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.6 }}
          className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center"
        >
          <Link to="/app/analyze">
            <ShimmerButton>
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

        {/* Trust line */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8, duration: 0.5 }}
          className="mt-6 text-xs tracking-wide text-gray-400 dark:text-gray-500"
        >
          Free to use · No sign-up required · Powered by Intel AI
        </motion.p>

        {/* Stats bar */}
        <div className="grid max-w-3xl grid-cols-2 gap-4 mx-auto mt-16 sm:grid-cols-4">
          {STATS.map((stat, i) => (
            <StatCard key={stat.label} stat={stat} index={i} />
          ))}
        </div>
      </div>

      {/* Scroll indicator — animated mouse */}
      
    </AuroraBackground>
  );
};

// ─── Section: Models Bento Grid ───────────────────────────────
const ModelsSection = () => (
  <section className="px-4 mx-auto py-28 max-w-7xl" id="features">
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mb-16 text-center"
    >
      <GlassBadge variant="primary" className="inline-flex items-center mb-6 text-xs">
        <Beaker className="w-3 h-3 mr-1.5" />
        ADMET Prediction Suite
      </GlassBadge>
      <h2 className="mb-5 text-4xl font-thin text-gray-800 md:text-5xl dark:text-gray-100">
        9 AI Models. <span className="text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text">One Platform.</span>
      </h2>
      <p className="max-w-2xl mx-auto text-lg leading-relaxed text-gray-500 dark:text-gray-400">
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
      gradient: 'from-cyan-500 to-cyan-400',
    },
    {
      num: '02',
      title: 'Run Models',
      desc: 'Select individual models or run all 9 simultaneously in one click.',
      gradient: 'from-violet-500 to-violet-400',
    },
    {
      num: '03',
      title: 'Get Insights',
      desc: 'Instant predictions with confidence scores, 3D visualization, and AI analysis.',
      gradient: 'from-teal-500 to-teal-400',
    },
  ];

  return (
    <section className="max-w-5xl px-4 mx-auto py-28">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.6 }}
        className="mb-16 text-center"
      >
        <h2 className="mb-5 text-4xl font-thin text-gray-800 md:text-5xl dark:text-gray-100">
          Input Once. <span className="text-transparent bg-gradient-to-r from-violet-400 to-teal-400 bg-clip-text">Analyze Everything.</span>
        </h2>
        <p className="max-w-lg mx-auto text-lg text-gray-500 dark:text-gray-400">
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
            <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] dark:border-white/[0.08] border-gray-200/50 bg-white/[0.03] dark:bg-white/[0.03] bg-gray-50/80 p-8 h-full transition-all duration-300 hover:border-white/[0.2]">
              {/* Border beam on cards */}
              <BorderBeam
                size={120}
                duration={8 + i * 2}
                delay={i * 2}
                colorFrom={i === 0 ? '#06b6d4' : i === 1 ? '#8b5cf6' : '#14b8a6'}
                colorTo={i === 0 ? '#8b5cf6' : i === 1 ? '#14b8a6' : '#06b6d4'}
              />

              {/* Step number */}
              <span className={`text-6xl font-bold bg-gradient-to-b ${step.gradient} bg-clip-text text-transparent opacity-20 block mb-4`}>
                {step.num}
              </span>

              <h3 className="mb-3 text-xl font-semibold text-gray-800 dark:text-gray-100">
                {step.title}
              </h3>
              <p className="text-sm leading-relaxed text-gray-500 dark:text-gray-400">
                {step.desc}
              </p>
            </div>

            {/* Connector arrow (between cards) */}
            {i < 2 && (
              <div className="absolute z-10 hidden text-gray-300 md:flex top-1/2 -right-5 dark:text-gray-600">
                <ArrowRight className="w-5 h-5" />
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </section>
  );
};

// ─── Section: Pricing ─────────────────────────────────────
const PricingSection = () => (
  <section className="max-w-6xl px-4 mx-auto py-28" id="pricing">
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mb-16 text-center"
    >
      <h2 className="mb-5 text-4xl font-thin text-gray-800 md:text-5xl dark:text-gray-100">
        Simple <span className="text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text">Pricing</span>
      </h2>
      <p className="text-lg text-gray-500 dark:text-gray-400">
        Start free. Upgrade when you need more.
      </p>
    </motion.div>

    <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
      {PRICING_PLANS.map((plan, i) => (
        <motion.div
          key={plan.name}
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.12, duration: 0.6 }}
          className="relative"
        >
          <div
            className={`relative overflow-hidden rounded-2xl h-full flex flex-col p-8
              border ${plan.popular
                ? 'border-cyan-500/40 bg-gradient-to-b from-cyan-500/[0.07] to-violet-500/[0.07]'
                : 'border-white/[0.08] dark:border-white/[0.08] border-gray-200/50 bg-white/[0.03] dark:bg-white/[0.03] bg-gray-50/80'
              }
              transition-all duration-300 hover:border-white/[0.2]`}
          >
            {/* Border beam on popular plan */}
            {plan.popular && (
              <BorderBeam size={180} duration={10} colorFrom="#06b6d4" colorTo="#8b5cf6" />
            )}

            {plan.popular && (
              <GlassBadge variant="primary" className="self-start mb-4 text-xs">
                <Star className="w-3 h-3 mr-1" /> Most Popular
              </GlassBadge>
            )}

            <h3 className="mb-2 text-xl font-semibold text-gray-800 dark:text-gray-200">
              {plan.name}
            </h3>
            <div className="mb-6">
              <span className="text-5xl font-bold text-gray-900 dark:text-white">
                {plan.price}
              </span>
              <span className="ml-1 text-gray-500 dark:text-gray-400">{plan.period}</span>
            </div>

            <ul className="flex-1 mb-8 space-y-3">
              {plan.features.map((f, j) => (
                <li key={j} className="flex items-start gap-3 text-sm text-gray-600 dark:text-gray-300">
                  <Check className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                  <span>{f}</span>
                </li>
              ))}
            </ul>

            {plan.popular ? (
              <ShimmerButton className="justify-center w-full py-3 text-base">
                {plan.cta}
              </ShimmerButton>
            ) : (
              <GhostShimmerButton className="justify-center w-full py-3 text-base">
                {plan.cta}
              </GhostShimmerButton>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  </section>
);

// ─── Section: CTA ─────────────────────────────────────────
const CTASection = () => (
  <section className="px-4 py-32 text-center">
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.7 }}
      className="relative max-w-3xl mx-auto"
    >
      <div className="relative overflow-hidden rounded-3xl border border-white/[0.08] dark:border-white/[0.08] border-gray-200/50 bg-white/[0.03] dark:bg-white/[0.03] bg-gray-50/80 backdrop-blur-sm p-16">
        <BorderBeam size={250} duration={14} colorFrom="#06b6d4" colorTo="#8b5cf6" />

        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none bg-gradient-to-r from-cyan-500/5 via-transparent to-violet-500/5" />

        <h2 className="relative mb-5 text-4xl font-thin text-gray-800 md:text-5xl dark:text-gray-100">
          Ready to accelerate your{' '}
          <span className="text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text">
            research
          </span>?
        </h2>
        <p className="relative max-w-xl mx-auto mb-10 text-lg leading-relaxed text-gray-500 dark:text-gray-400">
          Join researchers using DrugForge to make faster, data-driven decisions in drug discovery.
        </p>
        <div className="relative">
          <Link to="/app/analyze">
            <ShimmerButton>
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
  <footer className="px-4 py-12 border-t border-white/[0.06] dark:border-white/[0.06] border-gray-200/30">
    <div className="flex flex-col items-center justify-between gap-6 mx-auto max-w-7xl md:flex-row">
      <div>
        <span className="text-xl font-thin text-transparent bg-gradient-to-r from-cyan-400 to-violet-400 bg-clip-text">
          DrugForge
        </span>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          AI-Powered Drug Discovery Platform
        </p>
      </div>
      <div className="flex gap-8 text-sm text-gray-500 dark:text-gray-400">
        <a href="#features" className="transition-colors duration-200 hover:text-cyan-500">Features</a>
        <a href="#pricing" className="transition-colors duration-200 hover:text-cyan-500">Pricing</a>
        <Link to="/app" className="transition-colors duration-200 hover:text-cyan-500">Dashboard</Link>
        <Link to="/app/analyze" className="transition-colors duration-200 hover:text-cyan-500">Lab Bench</Link>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        © {new Date().getFullYear()} DrugForge. All rights reserved.
      </p>
    </div>
  </footer>
);

// ─── Main Landing Page ────────────────────────────────────────
const LandingPage = () => {
  return (
    <div className="relative overflow-hidden">
      <HeroSection />
      <ModelsSection />
      <HowItWorks />
      <PricingSection />
      <CTASection />
      <GlassFooter />
    </div>
  );
};

export default LandingPage;
