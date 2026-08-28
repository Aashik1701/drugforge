import React, { createContext, useContext, useReducer, useEffect, useState } from 'react';

// Initial state
const initialState = {
  user: null,
  favorites: [],
  recentSearches: [],
  theme: 'light',
  apiSettings: {
    modelVersion: 'latest',
    exhaustiveness: 8,
    useFastMode: false,
  },
  notifications: [],
  isLoading: false,
  error: null,
};

// Action types
export const ActionTypes = {
  SET_USER: 'SET_USER',
  ADD_FAVORITE: 'ADD_FAVORITE',
  REMOVE_FAVORITE: 'REMOVE_FAVORITE',
  ADD_SEARCH: 'ADD_SEARCH',
  CLEAR_SEARCHES: 'CLEAR_SEARCHES',
  SET_THEME: 'SET_THEME',
  UPDATE_API_SETTINGS: 'UPDATE_API_SETTINGS',
  ADD_NOTIFICATION: 'ADD_NOTIFICATION',
  REMOVE_NOTIFICATION: 'REMOVE_NOTIFICATION',
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
};

// Reducer function
function drugForgeReducer(state, action) {
  switch (action.type) {
    case ActionTypes.SET_USER:
      return {
        ...state,
        user: action.payload
      };
    case ActionTypes.ADD_FAVORITE:
      return {
        ...state,
        favorites: [...state.favorites, action.payload]
      };
    case ActionTypes.REMOVE_FAVORITE:
      return {
        ...state,
        favorites: state.favorites.filter(fav => fav.id !== action.payload)
      };
    case ActionTypes.ADD_SEARCH:
      // Keep only the last 10 searches
      const updatedSearches = [action.payload, ...state.recentSearches.slice(0, 9)];
      return {
        ...state,
        recentSearches: updatedSearches
      };
    case ActionTypes.CLEAR_SEARCHES:
      return {
        ...state,
        recentSearches: []
      };
    case ActionTypes.SET_THEME:
      return {
        ...state,
        theme: action.payload
      };
    case ActionTypes.UPDATE_API_SETTINGS:
      return {
        ...state,
        apiSettings: {
          ...state.apiSettings,
          ...action.payload
        }
      };
    case ActionTypes.ADD_NOTIFICATION:
      return {
        ...state,
        notifications: [
          ...state.notifications, 
          { id: Date.now(), ...action.payload }
        ]
      };
    case ActionTypes.REMOVE_NOTIFICATION:
      return {
        ...state,
        notifications: state.notifications.filter(
          note => note.id !== action.payload
        )
      };
    case ActionTypes.SET_LOADING:
      return {
        ...state,
        isLoading: action.payload
      };
    case ActionTypes.SET_ERROR:
      return {
        ...state,
        error: action.payload
      };
    case ActionTypes.CLEAR_ERROR:
      return {
        ...state,
        error: null
      };
    default:
      return state;
  }
}

// Create context
export const DrugForgeContext = createContext();

// Provider component
export const DrugForgeProvider = ({ children }) => {
  // Load state from localStorage
  const loadState = () => {
    try {
      const serializedState = localStorage.getItem('drugForgeState');
      if (serializedState === null) {
        return initialState;
      }
      
      // Parse the stored state
      const parsedState = JSON.parse(serializedState);
      
      // Check if a user preference for theme exists
      const userPrefersDark = window.matchMedia && 
        window.matchMedia('(prefers-color-scheme: dark)').matches;
      
      // If theme is not in stored state, use system preference
      if (!parsedState.theme) {
        parsedState.theme = userPrefersDark ? 'dark' : 'light';
      }
      
      return parsedState;
    } catch (e) {
      console.warn('Error loading state from localStorage:', e);
      return initialState;
    }
  };

  const [state, dispatch] = useReducer(drugForgeReducer, loadState());

  // Save state to localStorage whenever it changes
  useEffect(() => {
    try {
      const serializedState = JSON.stringify(state);
      localStorage.setItem('drugForgeState', serializedState);
    } catch (e) {
      console.warn('Error saving state to localStorage:', e);
    }
  }, [state]);
  
  // Initialize theme from system preference if not already set
  useEffect(() => {
    // If theme is already set in state, do nothing
    if (state.theme) return;
    
    const userPrefersDark = window.matchMedia && 
      window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    if (userPrefersDark) {
      dispatch({ type: ActionTypes.SET_THEME, payload: 'dark' });
    } else {
      dispatch({ type: ActionTypes.SET_THEME, payload: 'light' });
    }
  }, []);

  // Sidebar collapse state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const toggleSidebar = () => setIsSidebarCollapsed(prev => !prev);

  // AI Chat Context — what the researcher is currently analyzing
  const [activeContext, setActiveContext] = useState(null);

  // Computed convenience values
  const isDarkMode = state.theme === 'dark';
  const toggleTheme = () => dispatch({
    type: ActionTypes.SET_THEME,
    payload: state.theme === 'dark' ? 'light' : 'dark',
  });

  // Context value
  const value = {
    isSidebarCollapsed,
    toggleSidebar,
    activeContext,
    setActiveContext,
    state,
    dispatch,
    isDarkMode,
    toggleTheme,
    // Action helper functions
    setUser: (user) => dispatch({ 
      type: ActionTypes.SET_USER, 
      payload: user 
    }),
    addFavorite: (molecule) => dispatch({ 
      type: ActionTypes.ADD_FAVORITE, 
      payload: molecule 
    }),
    removeFavorite: (id) => dispatch({ 
      type: ActionTypes.REMOVE_FAVORITE, 
      payload: id 
    }),
    addSearch: (search) => dispatch({ 
      type: ActionTypes.ADD_SEARCH, 
      payload: search 
    }),
    clearSearches: () => dispatch({ type: ActionTypes.CLEAR_SEARCHES }),
    setTheme: (theme) => dispatch({ 
      type: ActionTypes.SET_THEME, 
      payload: theme 
    }),
    updateApiSettings: (settings) => dispatch({ 
      type: ActionTypes.UPDATE_API_SETTINGS, 
      payload: settings 
    }),
    addNotification: (notification) => dispatch({ 
      type: ActionTypes.ADD_NOTIFICATION, 
      payload: notification 
    }),
    removeNotification: (id) => dispatch({ 
      type: ActionTypes.REMOVE_NOTIFICATION, 
      payload: id 
    }),
    setLoading: (isLoading) => dispatch({ 
      type: ActionTypes.SET_LOADING, 
      payload: isLoading 
    }),
    setError: (error) => dispatch({ 
      type: ActionTypes.SET_ERROR, 
      payload: error 
    }),
    clearError: () => dispatch({ type: ActionTypes.CLEAR_ERROR }),
  };

  return (
    <DrugForgeContext.Provider value={value}>
      {children}
    </DrugForgeContext.Provider>
  );
};

// Custom hook for using the context
export const useDrugForge = () => {
  const context = useContext(DrugForgeContext);
  if (context === undefined) {
    throw new Error('useDrugForge must be used within a DrugForgeProvider');
  }
  return context;
};
