/**
 * ChatWidget – Context-Aware AI Assistant Floating on Every Page
 *
 * Features:
 * - Minimized button that expands to full chat window
 * - Automatically sees what the researcher is analyzing (via activeContext)
 * - Secure API calls (API key never reaches frontend)
 * - Glass morphism design matching DrugForge aesthetic
 * - Auto-scroll and message history
 */

import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, X, Send, Loader2, Sparkles, Bot } from 'lucide-react';
import axios from 'axios';
import { useDrugForge } from '../context/DrugForgeContext';

const ChatWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: 'ai',
      text: '👋 Hello! I\'m your DrugForge AI assistant. I can see what you\'re analyzing and help you understand your molecular results. Ask me anything!',
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Grab the invisible context from the current page!
  const { activeContext } = useDrugForge();
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', text: userMsg }]);
    setIsLoading(true);

    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';

      // Send the message PLUS the secret screen context
      const response = await axios.post(`${API_URL}/api/chat/ask`, {
        message: userMsg,
        context: activeContext, // This is where the magic happens
      });

      setMessages((prev) => [...prev, { role: 'ai', text: response.data.reply }]);
    } catch (error) {
      console.error('[ChatWidget] Error:', error);
      
      let errorMsg = 'Sorry, I lost connection to the server.';
      const status = error.response?.status;
      const detail = error.response?.data?.detail || error.response?.data?.error || '';
      
      // Handle specific error codes
      if (status === 503) {
        errorMsg = '🔑 AI engine not configured. Please set GEMINI_API_KEY in backend .env';
      } else if (status === 500 && detail.includes('quota') || status === 429) {
        errorMsg = '⏱️ **Gemini API quota exceeded.** Your free tier limit has been reached.\n\n**Options:**\n• Wait 24 hours for quota reset\n• Add billing at https://ai.google.dev/pricing (50x higher limits)\n• Use a new API key from another Google account\n\n💡 In the meantime, you can still analyze molecules - just the AI chat is temporarily unavailable.';
      } else if (status === 500) {
        errorMsg = `❌ Server error: ${detail.slice(0,100) || error.message}`;
      } else if (error.code === 'ERR_NETWORK') {
        errorMsg = '🌐 Network error: Backend server may be offline (http://localhost:5001)';
      } else {
        errorMsg = detail || error.message || 'Unknown error occurred';
      }
      
      setMessages((prev) => [...prev, { role: 'ai', text: `⚠️ ${errorMsg}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-[100] flex flex-col items-end">
      {/* Expanded Chat Window */}
      {isOpen && (
        <div className="mb-4 w-80 sm:w-96 h-[500px] flex flex-col rounded-2xl border border-white/20 bg-slate-900/90 backdrop-blur-xl shadow-[0_0_40px_rgba(6,182,212,0.15)] overflow-hidden transition-all duration-300 animate-in fade-in slide-in-from-bottom-4">
          {/* Header */}
          <div className="p-4 border-b border-white/10 bg-gradient-to-r from-cyan-500/20 to-violet-500/20 flex justify-between items-center">
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-cyan-400" />
              <h3 className="font-bold text-white">DrugForge AI</h3>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              className="text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Context Indicator (Lets user know AI is watching) */}
          {activeContext?.smiles && (
            <div className="px-4 py-1.5 bg-cyan-500/10 border-b border-white/5 text-[10px] text-cyan-400 font-mono flex items-center overflow-x-auto">
              <Bot className="w-3 h-3 mr-1 shrink-0" />
              <span className="truncate">Context: {activeContext.smiles}</span>
            </div>
          )}

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-hide">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-xl p-3 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-cyan-500 text-slate-900 font-medium rounded-tr-none'
                      : 'bg-white/10 text-slate-200 rounded-tl-none border border-white/5'
                  }`}
                >
                  {msg.text}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white/5 border border-white/5 rounded-xl rounded-tl-none p-4 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                  <span className="text-xs text-slate-400">Thinking...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <form onSubmit={handleSend} className="p-3 border-t border-white/10 bg-black/20">
            <div className="relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about this molecule..."
                className="w-full bg-white/5 border border-white/10 rounded-full py-2.5 pl-4 pr-12 text-sm text-white focus:outline-none focus:border-cyan-500/50 transition-colors placeholder:text-slate-500"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading}
                className="absolute right-1 top-1 bottom-1 aspect-square flex items-center justify-center bg-cyan-500 hover:bg-cyan-400 text-slate-900 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </form>
        </div>
      )}

      {/* The Floating Action Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center justify-center gap-2 px-4 py-3 rounded-full shadow-2xl transition-all duration-300 border ${
          isOpen
            ? 'bg-white/10 border-white/20 text-white hover:bg-white/20'
            : 'bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-900 hover:scale-105 hover:shadow-[0_0_20px_rgba(6,182,212,0.4)] border-transparent font-semibold'
        }`}
      >
        {isOpen ? <X className="w-5 h-5" /> : <MessageSquare className="w-5 h-5" />}
        {!isOpen && <span>Chat</span>}
      </button>
    </div>
  );
};

export default ChatWidget;
