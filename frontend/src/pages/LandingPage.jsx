import React from 'react';
import { Link } from 'react-router-dom';
import Hero from '../components/landing/Hero';
import ProblemSection from '../components/landing/ProblemSection';
import AgentSection from '../components/landing/AgentSection';
import EvidenceSection from '../components/landing/EvidenceSection';
import LearningSection from '../components/landing/LearningSection';
import ComputeSection from '../components/landing/ComputeSection';
import ModelsSection from '../components/landing/ModelsSection';
import DockingSection from '../components/landing/DockingSection';
import ResearchSection from '../components/landing/ResearchSection';
import ArchitectureSection from '../components/landing/ArchitectureSection';
import FinalCTA from '../components/landing/FinalCTA';
import { ACCENT_GRADIENT } from '../components/landing/shared';

const Footer = () => (
  <footer className="relative px-4 py-12 bg-white/80 dark:bg-gray-900/80 backdrop-blur-md border-t border-paper-border/50 dark:border-white/[0.06]">
    <div className="flex flex-col items-center justify-between gap-6 mx-auto max-w-7xl md:flex-row">
      <div>
        <span className={`font-display text-xl font-bold ${ACCENT_GRADIENT}`}>DrugForge</span>
        <p className="mt-1 text-xs text-ink-soft dark:text-gray-400">Agentic computational drug discovery</p>
      </div>
      <div className="flex flex-wrap justify-center gap-6 text-sm text-ink-soft dark:text-gray-400">
        <a href="#discover" className="transition-colors hover:text-clay-deep dark:hover:text-violet-400">Discover</a>
        <a href="#how-it-works" className="transition-colors hover:text-clay-deep dark:hover:text-violet-400">How It Works</a>
        <a href="#evidence" className="transition-colors hover:text-clay-deep dark:hover:text-violet-400">Evidence</a>
        <Link to="/research" className="transition-colors hover:text-clay-deep dark:hover:text-violet-400">Research</Link>
        <Link to="/app/analyze" className="transition-colors hover:text-clay-deep dark:hover:text-violet-400">Lab</Link>
        <Link to="/app" className="transition-colors hover:text-clay-deep dark:hover:text-violet-400">Dashboard</Link>
      </div>
      <p className="text-xs text-ink-soft dark:text-gray-400">© {new Date().getFullYear()} DrugForge.</p>
    </div>
  </footer>
);

const LandingPage = () => (
  <div className="relative overflow-hidden">
    <Hero />
    <ProblemSection />
    <AgentSection />
    <EvidenceSection />
    <LearningSection />
    <ComputeSection />
    <ModelsSection />
    <DockingSection />
    <ResearchSection />
    <ArchitectureSection />
    <FinalCTA />
    <Footer />
  </div>
);

export default LandingPage;
