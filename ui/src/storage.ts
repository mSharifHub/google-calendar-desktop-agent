// Thin wrapper that falls back to localStorage during local dev
const isChromeExt =
  typeof chrome !== 'undefined' && !!chrome.storage;

export function storageGet<T>(key: string): Promise<T | null> {
  return new Promise(resolve => {
    if (isChromeExt) {
      chrome.storage.local.get(key, d => resolve((d[key] as T) ?? null));
    } else {
      const raw = localStorage.getItem(key);
      resolve(raw ? (JSON.parse(raw) as T) : null);
    }
  });
}

export function storageSet(key: string, value: unknown): void {
  if (isChromeExt) {
    chrome.storage.local.set({ [key]: value });
  } else {
    localStorage.setItem(key, JSON.stringify(value));
  }
}
