"use client";

/**
 * WarmBackends — invisible client component mounted in root layout.
 * Fires a health-ping to all 5 Railway backends as soon as the app loads.
 * This wakes cold Railway instances BEFORE the user clicks anything, so
 * the first real LP run returns fast instead of waiting 20-30s for cold start.
 */

import { useEffect } from "react";
import { SECTOR_LIST } from "@/lib/sectors";
import { warmAllBackends } from "@/lib/api";

export default function WarmBackends() {
  useEffect(() => {
    // Fire-and-forget: wake all sector backends in parallel
    warmAllBackends(SECTOR_LIST);
  }, []);

  return null; // renders nothing
}
