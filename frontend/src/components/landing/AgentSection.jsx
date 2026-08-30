import React from 'react';
import { motion } from 'framer-motion';
import { ArrowDown, CheckCircle2, HelpCircle, XCircle, Beaker, FlaskConical } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';

const FlowNode = ({ children, tone = 'default', icon: Icon, delay = 0 }) => {
  const toneClasses = {
    default: 'border-paper-border/60 dark:border-white/[0.08] text-ink dark:text-white',
    exploit: 'border-teal-500/40 text-teal-600 dark:text-teal-400',
    investigate: 'border-violet-500/40 text-violet-600 dark:text-violet-400',
    reject: 'border-rose-500/30 text-rose-500 dark:text-rose-400',
  }[tone];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5, delay }}
      className={`${GLASS_PANEL} ${toneClasses} px-4 py-3 text-sm font-semibold flex items-center justify-center gap-2 text-center`}
    >
      {Icon && <Icon className="w-4 h-4 shrink-0" />}
      {children}
    </motion.div>
  );
};

const Arrow = () => <ArrowDown className="w-4 h-4 mx-auto my-2 text-paper-border dark:text-gray-600" />;

const AgentSection = () => (
  <section className="relative max-w-4xl px-4 mx-auto py-28" id="how-it-works">
    <SectionHeading eyebrow="The agent">An agent that chooses what to investigate.</SectionHeading>

    <p className="max-w-2xl mx-auto -mt-8 mb-14 text-center text-ink-soft dark:text-gray-300">
      Instead of blindly docking everything, DrugForge evaluates evidence, detects
      disagreement between models, and allocates expensive computation where it can
      resolve the most uncertainty.
    </p>

    <div className="max-w-sm mx-auto">
      <FlowNode>Candidates</FlowNode>
      <Arrow />
      <FlowNode delay={0.05}>Cheap prediction</FlowNode>
      <Arrow />
    </div>

    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 max-w-2xl mx-auto">
      <FlowNode icon={CheckCircle2} delay={0.1}>Agreement</FlowNode>
      <FlowNode icon={HelpCircle} delay={0.15}>Disagreement</FlowNode>
      <FlowNode icon={XCircle} delay={0.2}>Low value</FlowNode>
    </div>

    <div className="grid grid-cols-1 gap-3 mt-3 sm:grid-cols-3 max-w-2xl mx-auto">
      <FlowNode tone="exploit" icon={Beaker} delay={0.25}>Exploit</FlowNode>
      <FlowNode tone="investigate" icon={FlaskConical} delay={0.3}>Investigate</FlowNode>
      <FlowNode tone="reject" icon={XCircle} delay={0.35}>Reject</FlowNode>
    </div>

    <div className="max-w-xs mx-auto mt-1">
      <Arrow />
      <FlowNode tone="investigate" delay={0.4}>Vina</FlowNode>
      <p className="mt-2 text-xs text-center text-ink-soft/70 dark:text-gray-500">from Investigate only</p>
    </div>

    <p className="max-w-xl mx-auto mt-14 text-sm text-center text-ink-soft dark:text-gray-400">
      This is the architecture DrugForge is being built toward — an explanation of the
      decision logic, not a claim that an autonomous planner is running today.
    </p>
  </section>
);

export default AgentSection;
