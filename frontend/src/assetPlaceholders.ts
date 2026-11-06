import { useEffect, useState } from 'react';
import { api } from './api';

// Deck-prefixed image placeholders in stored markdown: {{24ea01202009--figure-17-46.jpg}}.
// Stored text keeps this form (the pptx export resolves it); the UI swaps in signed URLs for display.
const PLACEHOLDER = /\{\{\s*([0-9a-f]{12}--[^{}\s]+)\s*\}\}/g;

// Signed links are short-lived, so reuse resolved URLs for a few minutes only.
const CACHE_TTL_MS = 4 * 60 * 1000;
const urlCache = new Map<string, { url: string; at: number }>();

const fixtureUrl = (id: string) => `fixture://images/${id}`;

export async function resolveAssetPlaceholders(markdown: string): Promise<string> {
    const ids = [...new Set([...markdown.matchAll(PLACEHOLDER)].map(m => m[1]))];
    if (ids.length === 0) return markdown;

    const now = Date.now();
    const stale = ids.filter(id => {
        const hit = urlCache.get(id);
        return !hit || now - hit.at > CACHE_TTL_MS;
    });

    if (stale.length > 0) {
        try {
            const urls = await api.resolveImageUrls(stale.map(fixtureUrl));
            for (const id of stale) {
                const input = fixtureUrl(id);
                const url = urls[input];
                // The api returns the input unchanged when it cannot resolve
                if (url && url !== input) urlCache.set(id, { url, at: now });
            }
        } catch (e) {
            console.error('Failed to resolve asset placeholders:', e);
            return markdown;
        }
    }

    return markdown.replace(PLACEHOLDER, (whole, id: string) => {
        const hit = urlCache.get(id);
        return hit ? `![${id}](${hit.url})` : whole;
    });
}

/** Inverse for the editor: a signed fixture-asset URL back to its {{id}} placeholder. */
export function placeholderFromUrl(url: string): string | null {
    let pathname: string;
    try {
        pathname = new URL(url, 'http://localhost').pathname;
    } catch {
        return null;
    }
    const m = pathname.match(/\/source\/fixture-asset\/([^/]+)$/);
    if (!m) return null;
    let id: string;
    try {
        id = decodeURIComponent(m[1]);
    } catch {
        return null;
    }
    return /^[0-9a-f]{12}--.+$/.test(id) ? `{{${id}}}` : null;
}

export function useResolvedMarkdown(markdown: string | undefined): string {
    const [resolved, setResolved] = useState<{ source: string; text: string } | null>(null);
    const source = markdown || '';

    useEffect(() => {
        PLACEHOLDER.lastIndex = 0;
        if (!PLACEHOLDER.test(source)) return;
        let cancelled = false;
        resolveAssetPlaceholders(source).then(text => {
            if (!cancelled) setResolved({ source, text });
        });
        return () => { cancelled = true; };
    }, [source]);

    // Show the raw text until the resolved version for this exact source is ready
    return resolved && resolved.source === source ? resolved.text : source;
}
