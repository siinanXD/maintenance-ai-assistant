type ReactIslandMountOptions = {
  readonly mountEvent: string;
  readonly mountedFlag: string;
};

/**
 * Publish the mounted state for static fallback loaders.
 */
function announceMount(mountedFlag: string, mountEvent: string): void {
  (window as unknown as Record<string, unknown>)[mountedFlag] = true;
  window.dispatchEvent(new Event(mountEvent));
}

/**
 * Announce that React owns the island.
 */
export function markIslandMounted(options: ReactIslandMountOptions): void {
  announceMount(options.mountedFlag, options.mountEvent);
}
