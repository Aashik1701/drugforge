/**
 * Theme utility functions for consistent styling across components
 */

/**
 * Get themed classes based on dark mode state
 * @param {boolean} isDarkMode - Current dark mode state
 * @param {string} lightClass - Classes for light mode
 * @param {string} darkClass - Classes for dark mode
 * @returns {string} Combined class string
 */
export const getThemeClasses = (isDarkMode, lightClass, darkClass) => {
  return isDarkMode ? darkClass : lightClass;
};

/**
 * Get input field classes with theme support
 * @param {boolean} isDarkMode - Current dark mode state
 * @param {boolean} hasError - Whether the input has an error
 * @returns {string} Input class string
 */
export const getInputClasses = (isDarkMode, hasError = false) => {
  const base = "w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors duration-200";
  const theme = isDarkMode 
    ? "bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-400" 
    : "bg-white border-gray-300 text-gray-900 placeholder-gray-500";
  const error = hasError ? "border-red-500 ring-red-500" : "";
  return `${base} ${theme} ${error}`.trim();
};

/**
 * Get card container classes with theme support
 * @param {boolean} isDarkMode - Current dark mode state
 * @returns {string} Card class string
 */
export const getCardClasses = (isDarkMode) => {
  return `p-6 rounded-lg shadow-lg transition-colors duration-200 ${
    isDarkMode ? 'bg-gray-800 border border-gray-700' : 'bg-white border border-gray-200'
  }`;
};

/**
 * Get button classes with theme support
 * @param {boolean} isDarkMode - Current dark mode state
 * @param {string} variant - Button variant ('primary', 'secondary', 'danger')
 * @param {boolean} isLoading - Whether the button is in loading state
 * @returns {string} Button class string
 */
export const getButtonClasses = (isDarkMode, variant = 'primary', isLoading = false) => {
  const base = "px-4 py-2 font-medium rounded-md transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2";
  
  if (isLoading) {
    return `${base} bg-gray-400 cursor-not-allowed text-white`;
  }
  
  switch (variant) {
    case 'primary':
      return `${base} bg-blue-500 hover:bg-blue-600 text-white focus:ring-blue-500`;
    case 'secondary':
      const secondaryTheme = isDarkMode
        ? 'bg-gray-700 hover:bg-gray-600 text-gray-200 border border-gray-600'
        : 'bg-gray-200 hover:bg-gray-300 text-gray-800 border border-gray-300';
      return `${base} ${secondaryTheme} focus:ring-gray-500`;
    case 'danger':
      return `${base} bg-red-500 hover:bg-red-600 text-white focus:ring-red-500`;
    default:
      return `${base} bg-blue-500 hover:bg-blue-600 text-white focus:ring-blue-500`;
  }
};

/**
 * Get text classes with theme support
 * @param {boolean} isDarkMode - Current dark mode state
 * @param {string} level - Text level ('primary', 'secondary', 'muted')
 * @returns {string} Text class string
 */
export const getTextClasses = (isDarkMode, level = 'primary') => {
  switch (level) {
    case 'primary':
      return isDarkMode ? 'text-gray-100' : 'text-gray-900';
    case 'secondary':
      return isDarkMode ? 'text-gray-300' : 'text-gray-700';
    case 'muted':
      return isDarkMode ? 'text-gray-400' : 'text-gray-500';
    default:
      return isDarkMode ? 'text-gray-100' : 'text-gray-900';
  }
};

/**
 * Get error display classes with theme support
 * @param {boolean} isDarkMode - Current dark mode state
 * @returns {string} Error display class string
 */
export const getErrorClasses = (isDarkMode) => {
  return `flex items-start p-4 border rounded-md transition-colors duration-200 ${
    isDarkMode 
      ? 'bg-red-900/20 border-red-600' 
      : 'bg-orange-100 border-orange-400'
  }`;
};

/**
 * Get success display classes with theme support
 * @param {boolean} isDarkMode - Current dark mode state
 * @returns {string} Success display class string
 */
export const getSuccessClasses = (isDarkMode) => {
  return `flex items-start p-4 border rounded-md transition-colors duration-200 ${
    isDarkMode 
      ? 'bg-green-900/20 border-green-600' 
      : 'bg-green-100 border-green-400'
  }`;
};

/**
 * Get background classes for different sections
 * @param {boolean} isDarkMode - Current dark mode state
 * @param {string} level - Background level ('primary', 'secondary', 'elevated')
 * @returns {string} Background class string
 */
export const getBackgroundClasses = (isDarkMode, level = 'primary') => {
  switch (level) {
    case 'primary':
      return isDarkMode ? 'bg-gray-900' : 'bg-white';
    case 'secondary':
      return isDarkMode ? 'bg-gray-800' : 'bg-gray-50';
    case 'elevated':
      return isDarkMode ? 'bg-gray-700' : 'bg-white';
    default:
      return isDarkMode ? 'bg-gray-900' : 'bg-white';
  }
};
