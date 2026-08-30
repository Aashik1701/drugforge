import React from 'react';
import {
  FlaskConical, Shield, Activity, Pill, Clock, Target, Microscope, Brain, BarChart3,
} from 'lucide-react';
import { BentoGrid, BentoGridItem } from '../ui/bento-grid';
import { SectionHeading } from './shared';

const MODELS = [
  { name: 'Solubility (LogS)', icon: FlaskConical, desc: 'Aqueous solubility for drug-likeness assessment', category: 'ADMET', color: 'cyan' },
  { name: 'BBB Permeability', icon: Shield, desc: 'Blood-brain barrier penetration classification', category: 'ADMET', color: 'violet' },
  { name: 'Toxicity', icon: Activity, desc: 'Multi-endpoint toxicity risk profiling', category: 'Safety', color: 'rose' },
  { name: 'CYP3A4 Inhibition', icon: Pill, desc: 'Cytochrome P450 3A4 enzyme inhibition prediction', category: 'ADMET', color: 'amber' },
  { name: 'Half-Life', icon: Clock, desc: 'Pharmacokinetic half-life estimation', category: 'ADMET', color: 'teal' },
  { name: 'COX-2 Binding', icon: Target, desc: 'Cyclooxygenase-2 target binding affinity', category: 'Binding', color: 'emerald' },
  { name: 'HepG2 Cytotoxicity', icon: Microscope, desc: 'Hepatocyte cytotoxicity screening', category: 'Safety', color: 'sky' },
  { name: 'ACE2 Binding', icon: Brain, desc: 'ACE2 receptor binding prediction', category: 'Binding', color: 'violet' },
  { name: 'Binding Score', icon: BarChart3, desc: 'General protein-ligand binding affinity', category: 'Binding', color: 'cyan' },
];

const ModelsSection = () => (
  <section className="relative px-4 mx-auto py-28 max-w-7xl">
    <SectionHeading eyebrow="Scientific toolkit">One discovery system. Multiple scientific lenses.</SectionHeading>
    <p className="max-w-2xl mx-auto -mt-8 mb-14 text-center text-ink-soft dark:text-gray-300">
      Different evidence sources for the same scientific decision — none claimed
      equally accurate, each covering a different question.
    </p>

    <BentoGrid>
      {MODELS.map((model, i) => (
        <BentoGridItem
          key={model.name}
          title={model.name}
          description={`${model.desc} · ${model.category} evidence`}
          accentColor={model.color}
          index={i}
          icon={<model.icon className={`w-6 h-6 text-${model.color}-400`} />}
        />
      ))}
    </BentoGrid>
  </section>
);

export default ModelsSection;
