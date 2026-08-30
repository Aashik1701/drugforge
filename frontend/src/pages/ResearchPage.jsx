import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, Loader2 } from 'lucide-react';

const FINDINGS_URL = '/research/FINDINGS.md';

const markdownComponents = {
  h1: ({ children }) => (
    <h1 className="mt-2 mb-4 font-display text-3xl font-bold text-ink dark:text-white">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mt-10 mb-3 font-display text-xl font-bold text-ink dark:text-white">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mt-6 mb-2 text-base font-semibold text-ink dark:text-white">{children}</h3>
  ),
  p: ({ children }) => <p className="mb-4 leading-relaxed text-ink-soft dark:text-gray-300">{children}</p>,
  a: ({ href, children }) => (
    <a href={href} className="text-clay-deep dark:text-violet-400 hover:underline">
      {children}
    </a>
  ),
  strong: ({ children }) => <strong className="font-semibold text-ink dark:text-white">{children}</strong>,
  code: ({ children }) => (
    <code className="px-1.5 py-0.5 rounded bg-ink/5 dark:bg-white/10 text-[0.85em] font-mono text-ink dark:text-gray-200">
      {children}
    </code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="pl-4 my-4 border-l-2 border-clay/40 dark:border-violet-500/40 text-ink-soft dark:text-gray-400">
      {children}
    </blockquote>
  ),
  ul: ({ children }) => <ul className="pl-5 mb-4 list-disc space-y-1.5 text-ink-soft dark:text-gray-300">{children}</ul>,
  ol: ({ children }) => <ol className="pl-5 mb-4 list-decimal space-y-1.5 text-ink-soft dark:text-gray-300">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  hr: () => <hr className="my-10 border-paper-border/60 dark:border-white/[0.08]" />,
  table: ({ children }) => (
    <div className="overflow-x-auto mb-4">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-semibold border-b border-paper-border/60 dark:border-white/[0.08] text-ink dark:text-white">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 border-b border-paper-border/30 dark:border-white/[0.05] text-ink-soft dark:text-gray-300">
      {children}
    </td>
  ),
};

const ResearchPage = () => {
  const [content, setContent] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(FINDINGS_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}`);
        return res.text();
      })
      .then((text) => {
        if (!cancelled) setContent(text);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-paper dark:bg-gray-900">
      <div className="max-w-3xl px-4 py-16 mx-auto sm:px-6">
        <Link
          to="/"
          className="inline-flex items-center gap-2 mb-10 text-sm font-medium text-ink-soft dark:text-gray-400 hover:text-clay-deep dark:hover:text-violet-400"
        >
          <ArrowLeft className="w-4 h-4" /> Back to DrugForge
        </Link>

        {error && (
          <p className="text-rose-500 dark:text-rose-400">Could not load the research findings ({error}).</p>
        )}
        {!content && !error && (
          <div className="flex items-center gap-2 text-ink-soft dark:text-gray-400">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading findings…
          </div>
        )}
        {content && <ReactMarkdown components={markdownComponents}>{content}</ReactMarkdown>}
      </div>
    </div>
  );
};

export default ResearchPage;
