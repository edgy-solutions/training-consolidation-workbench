// Concept names arrive in case variants ("Wire Gauge" / "wire gauge"); these helpers treat them as one.

// Case-folded, trimmed name with whitespace runs collapsed
export const conceptKey = (name: string) => name.trim().replace(/\s+/g, ' ').toLowerCase();

// The most frequent original casing; ties go to the one seen first
export function displayCasing(names: string[]): string {
    const counts = new Map<string, number>();
    for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
    let best = '';
    let bestCount = 0;
    for (const [n, c] of counts) {
        if (c > bestCount) {
            best = n;
            bestCount = c;
        }
    }
    return best;
}

// One entry per conceptKey, first-seen order; salience is the max, with null (unknown) losing to any number
export function mergeByCase<T extends { name: string; salience?: number | null }>(concepts: T[]): T[] {
    const groups = new Map<string, T[]>();
    for (const c of concepts) {
        const k = conceptKey(c.name);
        const g = groups.get(k);
        if (g) g.push(c);
        else groups.set(k, [c]);
    }
    return [...groups.values()].map(g => {
        let salience: number | null | undefined;
        for (const c of g) {
            if (c.salience == null) {
                if (salience === undefined) salience = c.salience;
            } else {
                salience = salience == null ? c.salience : Math.max(salience, c.salience);
            }
        }
        return { ...g[0], name: displayCasing(g.map(c => c.name)), salience };
    });
}
