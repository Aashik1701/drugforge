import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { SectionHeading, GLASS_PANEL } from './shared';
import { RESEARCH_CARDS, FUNNEL_SUMMARY } from './researchData';

const ResearchSection = () => (
  <section className="relative px-4 mx-auto py-28 max-w-5xl">
    <SectionHeading eyebrow="Research evidence">DrugForge measures its own limitations.</SectionHeading>
    <p className="max-w-2xl mx-auto -mt-8 mb-14 text-center text-ink-soft dark:text-gray-300">
      {FUNNEL_SUMMARY.passCount} passes of offline evaluation on the computational funnel — reported
      honestly, including what didn&apos;t work.
    </p>

    <div className="grid gap-6 sm:grid-cols-2">
      {RESEARCH_CARDS.map((card, i) => (
        <motion.div
          key={card.title}
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.5, delay: i * 0.08 }}
          className={`${GLASS_PANEL} p-6`}
        >
          <h3 className="mb-2 text-lg font-semibold text-ink dark:text-white">{card.title}</h3>
          <p className="text-sm leading-relaxed text-ink-soft dark:text-gray-400">{card.body}</p>
        </motion.div>
      ))}
    </div>

    <div className="mt-12 text-center">
      <Link
        to="/research"
        className="inline-flex items-center gap-2 text-clay-deep dark:text-violet-400 font-medium hover:underline"
      >
        Explore the research <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  </section>
);

export default ResearchSection;
