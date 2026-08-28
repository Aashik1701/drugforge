import React, { useState, useCallback, useEffect, useRef } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { useDrugForge } from '../context/DrugForgeContext';

const Chatbot = () => {
    const { isDarkMode } = useDrugForge();
    const [isOpen, setIsOpen] = useState(false);
    const [message, setMessage] = useState('');
    const [messages, setMessages] = useState([
        { text: 'Welcome to DrugForge! How can I assist you with drug discovery today?\n\n💡 *Try asking about drug properties, molecular predictions, or ADMET analysis!*', sender: 'bot', timestamp: new Date() }
    ]);
    const [generatingAnswer, setGeneratingAnswer] = useState(false);
    const [apiAvailable, setApiAvailable] = useState(true);
    
    // Use ref to access latest messages
    const messagesEndRef = useRef(null);
    const apiKeyRef = useRef(import.meta.env.VITE_API_GENERATIVE_LANGUAGE_CLIENT);
    
    // Validate API key on component mount
    useEffect(() => {
        const apiKey = import.meta.env.VITE_API_GENERATIVE_LANGUAGE_CLIENT;
        const isValidKey = apiKey && 
                          apiKey.length > 20 && 
                          apiKey.startsWith('AIza') && 
                          apiKey !== 'your_gemini_api_key_here' && 
                          apiKey !== 'undefined';
        
        apiKeyRef.current = apiKey;
        setApiAvailable(isValidKey);
        
        if (!isValidKey) {
            // Silent debug - only log in development if needed
            console.debug('Chatbot: Running in offline/fallback mode (no valid Gemini API key configured)');
        }
    }, []);
    
    // Auto scroll to bottom when messages change
    useEffect(() => {
        if (messagesEndRef.current && isOpen) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isOpen]);

    const toggleChat = useCallback(() => {
        setIsOpen(prev => !prev);
    }, []);

    const closeChat = useCallback(() => {
        setIsOpen(false);
    }, []);

    // Fallback responses for when API is unavailable
    const getFallbackResponse = (userMessage) => {
        const msg = userMessage.toLowerCase();
        
        if (msg.includes('hello') || msg.includes('hi') || msg.includes('hey')) {
            return "👋 **Hello!** I'm DrugForge AI, your drug discovery assistant!\n\n🔬 **I can help with:**\n• Molecular property predictions\n• ADMET analysis (Absorption, Distribution, Metabolism, Excretion, Toxicity)\n• Drug-target binding predictions\n• Compound solubility analysis\n• Virtual screening guidance\n\n*Note: API services are currently limited. Please try the prediction tools in the main application!*";
        }
        
        if (msg.includes('help') || msg.includes('what can you do')) {
            return "🎯 **DrugForge Features:**\n\n**Prediction Tools:**\n• ACE2 Binding Prediction\n• COX-2 Inhibition Analysis\n• CYP3A4 Interaction Prediction\n• HEPG2 Cytotoxicity Assessment\n• Blood-Brain Barrier Permeability (BBBP)\n• Drug Half-Life Estimation\n• Toxicity Screening\n• Binding Score Calculation\n• Virtual Screening\n\n**How to use:** Navigate to any prediction tool, enter a SMILES string, and get instant AI-powered predictions!";
        }
        
        if (msg.includes('smiles') || msg.includes('molecular')) {
            return "🧬 **SMILES Notation Guide:**\n\nSMILES (Simplified Molecular Input Line Entry System) represents molecular structures as text strings.\n\n**Examples:**\n• Aspirin: `CC(=O)OC1=CC=CC=C1C(=O)O`\n• Caffeine: `CN1C=NC2=C1C(=O)N(C(=O)N2C)C`\n• Ethanol: `CCO`\n\n**Tips:**\n• Use parentheses for branches\n• Numbers indicate ring closures\n• Uppercase = atoms, lowercase = aromatic\n\n*Try entering these in our prediction tools!*";
        }
        
        if (msg.includes('api') || msg.includes('error') || msg.includes('rate limit')) {
            return "⚠️ **API Status Information:**\n\nThe chat API is currently experiencing issues, but all DrugForge prediction tools are still fully functional!\n\n**Available Now:**\n✅ All molecular prediction tools\n✅ ADMET property analysis\n✅ Virtual screening\n✅ Binding score calculations\n\n**Troubleshooting:**\n• Refresh the page and try again\n• Use the main prediction tools instead\n• Contact support if issues persist";
        }
        
        return "🤖 **DrugForge AI (Offline Mode)**\n\nI'm currently running in limited mode. For full AI assistance, please:\n\n1. **Use the prediction tools** in the main application\n2. **Try again later** when API services are restored\n3. **Ask specific questions** about DrugForge features\n\n**Quick Links:**\n• Molecular property predictions\n• ADMET analysis tools\n• Virtual screening platform\n• Drug-target binding analysis\n\n*All core functionality remains available!*";
    };

    const handleSendMessage = useCallback(async () => {
        if (message.trim() === '') return;
        
        const userMessage = { 
            text: message, 
            sender: 'user', 
            timestamp: new Date() 
        };
        
        // Update with user message
        setMessages(prevMessages => [...prevMessages, userMessage]);
        setMessage('');
        setGeneratingAnswer(true);
        
        // Check if API key is available - only fallback if clearly invalid
        const isValidApiKey = apiKeyRef.current && 
                             apiKeyRef.current.length > 20 && 
                             apiKeyRef.current.startsWith('AIza') && 
                             apiKeyRef.current !== 'your_gemini_api_key_here' && 
                             apiKeyRef.current !== 'undefined' && 
                             apiKeyRef.current !== '';
        
        if (!isValidApiKey) {
            // Use fallback response immediately
            setTimeout(() => {
                const fallbackResponse = getFallbackResponse(message);
                setMessages(prevMessages => [
                    ...prevMessages,
                    { 
                        text: fallbackResponse, 
                        sender: 'bot', 
                        timestamp: new Date() 
                    }
                ]);
                setGeneratingAnswer(false);
                setApiAvailable(false);
            }, 800); // Small delay to simulate thinking
            return;
        }
        
        try {
            const response = await axios({
                url: `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=${apiKeyRef.current}`,
                method: "post",
                headers: {
                    'Content-Type': 'application/json',
                },
                data: {
                    contents: [
                        {
                            parts: [
                                {
                                    text: `You are DrugForge AI, an expert assistant specializing in drug discovery, pharmaceutical research, and computational chemistry. Provide helpful, accurate information about drug development, molecular properties, toxicity prediction, and related topics. Keep responses concise but informative.

User question: ${message}`
                                }
                            ]
                        }
                    ],
                    generationConfig: {
                        temperature: 0.7,
                        maxOutputTokens: 1000,
                    }
                },
            });

            // Add bot response after API call completes
            const botResponse = response.data.candidates?.[0]?.content?.parts?.[0]?.text || "No response generated";
            setMessages(prevMessages => [
                ...prevMessages,
                { 
                    text: botResponse, 
                    sender: 'bot', 
                    timestamp: new Date() 
                }
            ]);
            
            // Ensure API is marked as available after successful call
            setApiAvailable(true);
        } catch (error) {
            console.error("Chatbot API error:", error);
            console.error("Error details:", {
                status: error.response?.status,
                statusText: error.response?.statusText,
                data: error.response?.data,
                message: error.message
            });
            
            let errorMessage = "Sorry - Something went wrong. Please try again!";
            
            if (error.response?.status === 403) {
                errorMessage = "⚠️ **API Authentication Error**\n\nThe Google Gemini API key is invalid or missing. Please:\n1. Check your API key in the environment configuration\n2. Ensure the key has the correct permissions\n3. Verify your Google Cloud project settings";
                setApiAvailable(false); // Only set offline for auth errors
            } else if (error.response?.status === 429) {
                errorMessage = "⏰ **Rate Limit Exceeded**\n\nYou've reached the API usage limit. Please:\n1. Wait a few minutes before trying again\n2. Check your Google Gemini API usage\n3. Consider upgrading your plan for higher limits\n\n*Tip: You can continue using other DrugForge features while waiting.*";
                
                // Don't set API unavailable for rate limits - user can try again
                setMessages(prevMessages => [
                    ...prevMessages,
                    { 
                        text: errorMessage, 
                        sender: 'bot', 
                        timestamp: new Date() 
                    }
                ]);
                setGeneratingAnswer(false);
                return;
            } else if (error.response?.status === 400) {
                errorMessage = "🚫 **Bad Request**\n\nThere was an issue with the request format. Please try rephrasing your question.";
            } else if (error.response?.status >= 500) {
                errorMessage = "🔧 **Server Error**\n\nGoogle's servers are experiencing issues. Please try again in a few minutes.";
            } else if (error.code === 'NETWORK_ERROR' || !error.response) {
                errorMessage = "🌐 **Connection Error**\n\nCouldn't connect to Google's servers. Please check your internet connection and try again.";
            }
            
            setMessages(prevMessages => [
                ...prevMessages,
                { 
                    text: errorMessage, 
                    sender: 'bot', 
                    timestamp: new Date() 
                }
            ]);
        } finally {
            setGeneratingAnswer(false);
        }
    }, [message]);

    const handleKeyPress = useCallback((e) => {
        if (e.key === 'Enter' && !generatingAnswer) {
            handleSendMessage();
        }
    }, [handleSendMessage, generatingAnswer]);

    // Quick test function for development
    const sendTestMessage = useCallback(() => {
        setMessage('Hello, can you help me with drug discovery?');
        setTimeout(() => handleSendMessage(), 100);
    }, [handleSendMessage]);

    return (
        <div className="fixed bottom-6 right-6 z-50">
            {isOpen ? (
                <div className={`w-80 sm:w-96 h-96 rounded-lg shadow-xl flex flex-col overflow-hidden border transition-colors duration-200 ${
                    isDarkMode 
                        ? 'bg-gray-800 border-gray-600' 
                        : 'bg-white border-gray-200'
                }`}>
                <div className={`px-4 py-3 flex justify-between items-center transition-colors duration-200 ${
                    isDarkMode 
                        ? 'bg-blue-700' 
                        : 'bg-blue-600'
                }`}>
                    <div className="flex items-center space-x-2">
                        <h3 className="text-white font-medium">Chat with DrugForge AI</h3>
                        {!apiAvailable && (
                            <span className="text-xs bg-yellow-500 text-yellow-900 px-2 py-1 rounded-full">
                                Offline Mode
                            </span>
                        )}
                    </div>
                    <button 
                        className={`text-white rounded-full w-6 h-6 flex items-center justify-center focus:outline-none transition-colors duration-200 ${
                            isDarkMode 
                                ? 'hover:bg-blue-800' 
                                : 'hover:bg-blue-700'
                        }`}
                        onClick={closeChat} 
                        aria-label="Close chat"
                    >
                        ✖
                    </button>
                </div>
                <div className={`flex-grow overflow-auto p-4 transition-colors duration-200 ${
                    isDarkMode 
                        ? 'bg-gray-900' 
                        : 'bg-gray-50'
                }`}>
                    {/* Debug info in development */}
                    {process.env.NODE_ENV === 'development' && (
                        <div className={`mb-2 p-2 rounded text-xs border ${
                            isDarkMode 
                                ? 'bg-gray-800 border-gray-600 text-gray-300' 
                                : 'bg-gray-100 border-gray-300 text-gray-600'
                        }`}>
                            API Status: {apiAvailable ? '🟢 Online' : '🔴 Offline'} | 
                            Key: {apiKeyRef.current ? '✅ Present' : '❌ Missing'}
                        </div>
                    )}
                    <div className="flex flex-col space-y-4">
                        {messages.map((msg, index) => (
                            <div 
                                key={`msg-${index}-${msg.timestamp}`} 
                                className={`rounded-lg max-w-[85%] transition-colors duration-200 ${msg.sender === 'bot' 
                                    ? `border self-start ${
                                        isDarkMode 
                                            ? 'bg-gray-700 border-gray-600 text-gray-100' 
                                            : 'bg-white border-gray-200 text-gray-800'
                                    }` 
                                    : 'bg-blue-500 text-white self-end'
                                }`}
                            >
                                <div className={`px-3 py-1 border-b flex justify-between items-center ${
                                    msg.sender === 'bot' 
                                        ? (isDarkMode ? 'border-gray-600' : 'border-gray-100')
                                        : 'border-blue-400'
                                }`}>
                                    <span className="text-xs font-medium">{msg.sender === 'bot' ? 'DrugForge' : 'You'}</span>
                                    <span className="text-xs opacity-75">
                                        {msg.timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                                    </span>
                                </div>
                                <div className="px-3 py-2">
                                    <ReactMarkdown className={`prose prose-sm ${
                                        msg.sender === 'bot' && isDarkMode 
                                            ? 'prose-invert' 
                                            : ''
                                    }`}>{msg.text}</ReactMarkdown>
                                </div>
                            </div>
                        ))}
                        {generatingAnswer && (
                            <div className={`rounded-lg max-w-[85%] self-start border transition-colors duration-200 ${
                                isDarkMode 
                                    ? 'bg-gray-700 border-gray-600 text-gray-100' 
                                    : 'bg-white border-gray-200 text-gray-800'
                            }`}>
                                <div className={`px-3 py-1 border-b flex justify-between items-center ${
                                    isDarkMode ? 'border-gray-600' : 'border-gray-100'
                                }`}>
                                    <span className="text-xs font-medium">DrugForge</span>
                                    <span className="text-xs opacity-75">Typing...</span>
                                </div>
                                <div className="px-3 py-2">
                                    <div className="flex items-center space-x-1">
                                        <div className="flex space-x-1">
                                            <div className={`w-2 h-2 rounded-full animate-pulse ${
                                                isDarkMode ? 'bg-gray-400' : 'bg-gray-500'
                                            }`}></div>
                                            <div className={`w-2 h-2 rounded-full animate-pulse animation-delay-200 ${
                                                isDarkMode ? 'bg-gray-400' : 'bg-gray-500'
                                            }`}></div>
                                            <div className={`w-2 h-2 rounded-full animate-pulse animation-delay-400 ${
                                                isDarkMode ? 'bg-gray-400' : 'bg-gray-500'
                                            }`}></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                </div>
                <div className={`p-3 border-t flex transition-colors duration-200 ${
                    isDarkMode 
                        ? 'bg-gray-800 border-gray-600' 
                        : 'bg-gray-100 border-gray-200'
                }`}>
                    {/* Test button in development */}
                    {process.env.NODE_ENV === 'development' && (
                        <button 
                            onClick={sendTestMessage}
                            className={`mr-2 px-2 py-2 text-xs rounded transition-colors duration-200 ${
                                isDarkMode 
                                    ? 'bg-green-700 text-white hover:bg-green-600' 
                                    : 'bg-green-600 text-white hover:bg-green-700'
                            }`}
                        >
                            Test
                        </button>
                    )}
                    <input
                        type="text"
                        placeholder="Type your message..."
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                        onKeyPress={handleKeyPress}
                        disabled={generatingAnswer}
                        className={`flex-grow px-3 py-2 border rounded-l-md focus:outline-none focus:ring-1 focus:ring-blue-500 transition-colors duration-200 ${
                            isDarkMode 
                                ? 'bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-400' 
                                : 'bg-white border-gray-300 text-gray-800 placeholder-gray-500'
                        }`}
                        aria-label="Chat message input"
                    />
                    <button 
                        onClick={handleSendMessage} 
                        disabled={generatingAnswer || message.trim() === ''} 
                        className={`px-4 py-2 rounded-r-md transition-colors duration-200 ${
                            generatingAnswer || message.trim() === '' 
                                ? 'bg-gray-400 text-gray-100 cursor-not-allowed' 
                                : 'bg-blue-600 text-white hover:bg-blue-700'
                        }`}
                    >
                        {generatingAnswer ? 'Thinking...' : 'Send'}
                    </button>
                </div>
            </div>
            ) : (
                <div className={`hover:bg-blue-700 rounded-full p-3 shadow-lg flex items-center justify-center cursor-pointer transition-all duration-300 transform hover:scale-105 ${
                    isDarkMode 
                        ? 'bg-blue-700 shadow-gray-900/30' 
                        : 'bg-blue-600 shadow-gray-500/30'
                }`} onClick={toggleChat}>
                    <div className="relative w-10 h-10 flex items-center justify-center rounded-full overflow-hidden bg-white">
                        <video width="40" height="40" loop autoPlay muted playsInline className="max-w-full max-h-full">
                            <source src="/Images/videos/chatbot-icon.mp4" type="video/mp4" />
                            Your browser does not support the video tag.
                        </video>
                    </div>
                    <span className="ml-2 text-white font-medium">Chat</span>
                </div>
            )}
        </div>
    );
};

export default Chatbot;