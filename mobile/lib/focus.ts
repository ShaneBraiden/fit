import { useFocusEffect } from 'expo-router';
import { useCallback, useRef } from 'react';

/** Runs `refresh` whenever the screen comes back into focus, but not on its first focus
 *  (the screen's own fetches already ran then). */
export function useFocusRefresh(refresh: () => void) {
  const seen = useRef(false);
  useFocusEffect(useCallback(() => {
    if (seen.current) refresh();
    seen.current = true;
  }, [refresh]));
}
