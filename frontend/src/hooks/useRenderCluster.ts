import { useEffect } from 'react';
import { renderManager } from '@/lib/render/manager';

export function useRenderCluster() {
  useEffect(() => {
    // Poll the queue every 5 seconds to pick up new jobs
    const interval = setInterval(() => {
      renderManager.processQueue();
    }, 5000);

    // Initial check
    renderManager.processQueue();

    return () => clearInterval(interval);
  }, []);
}
