import React, { useEffect } from 'react';
import { X, AlertCircle, CheckCircle, Info, AlertTriangle } from 'lucide-react';
import { useDrugForge } from '../context/DrugForgeContext.jsx';
import { motion, AnimatePresence } from 'framer-motion';

const notificationIcons = {
  success: <CheckCircle className="text-green-500" size={20} />,
  error: <AlertCircle className="text-red-500" size={20} />,
  info: <Info className="text-blue-500" size={20} />,
  warning: <AlertTriangle className="text-amber-500" size={20} />
};

const notificationStyles = {
  success: 'border-l-4 border-green-500 bg-green-50 dark:bg-green-900/20',
  error: 'border-l-4 border-red-500 bg-red-50 dark:bg-red-900/20',
  info: 'border-l-4 border-blue-500 bg-blue-50 dark:bg-blue-900/20',
  warning: 'border-l-4 border-amber-500 bg-amber-50 dark:bg-amber-900/20'
};

const Notifications = () => {
  const { state, removeNotification } = useDrugForge();
  const { notifications } = state;

  // Auto-dismiss notifications after a timeout
  useEffect(() => {
    if (notifications.length > 0) {
      const timers = notifications.map(notification => {
        if (notification.persist) return null;
        
        const timer = setTimeout(() => {
          removeNotification(notification.id);
        }, notification.duration || 5000);
        
        return { id: notification.id, timer };
      });
      
      // Cleanup timers on unmount or when notifications change
      return () => {
        timers.forEach(item => {
          if (item && item.timer) clearTimeout(item.timer);
        });
      };
    }
  }, [notifications, removeNotification]);

  if (notifications.length === 0) return null;

  return (
    <div className="fixed z-50 flex flex-col w-full max-w-sm gap-2 top-4 right-4">
      <AnimatePresence>
        {notifications.map(notification => (
          <motion.div
            key={notification.id}
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
            layout
            transition={{ duration: 0.2 }}
            className={`${notificationStyles[notification.type]} rounded-md shadow-md p-4 flex items-start w-full`}
          >
            <div className="flex-shrink-0 mr-3">
              {notificationIcons[notification.type]}
            </div>
            <div className="flex-grow">
              {notification.title && (
                <h4 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                  {notification.title}
                </h4>
              )}
              <p className="text-sm text-gray-600 dark:text-gray-300">
                {notification.message}
              </p>
            </div>
            <button
              onClick={() => removeNotification(notification.id)}
              className="flex-shrink-0 ml-2 text-gray-400 hover:text-gray-600 dark:text-gray-400 dark:hover:text-gray-200 focus:outline-none"
            >
              <X size={16} />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};

export default Notifications;
