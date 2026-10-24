import React, { useEffect, useState, useMemo, useRef, useCallback } from 'react';
import { ArrowRight, ChevronDown, ChevronRight, Layers, Zap } from 'lucide-react';
import { api, courseSubtitle, courseTooltip } from '../api';
import type { CourseSection } from '../api';
import { useSelectionStore } from '../stores/selectionStore';
import { useAppStore, projectTitle } from '../store';
import clsx from 'clsx';

interface StagingGroup {
    buName: string;
    courses: {
        id: string;
        title: string;
        filename?: string | null;
        version?: string | null;
        sections: CourseSection[];
    }[];
}

// Color palette for similarity groups
const SIMILARITY_COLORS = [
    'bg-blue-100 border-blue-300',
    'bg-amber-100 border-amber-300',
    'bg-green-100 border-green-300',
    'bg-purple-100 border-purple-300',
    'bg-pink-100 border-pink-300',
    'bg-cyan-100 border-cyan-300',
    'bg-orange-100 border-orange-300',
    'bg-teal-100 border-teal-300',
];

// No slides and no concepts of its own: kept in the list, left out of similarity
const isEmptySection = (s: CourseSection) => (s.slide_count ?? 1) === 0 && s.concepts_inherited === true;

// Indent stops growing after this many steps; deeper rows show a depth number instead
const MAX_INDENT_STEPS = 3;

// Rows to show, depth-first. The tree comes from parent_id (the HAS_SECTION edge), so it does
// not depend on the API's order; children keep their relative order, and a section whose
// parent is missing is a root. An API without parent_id falls back to nesting by level.
// A collapsed section hides its subtree.
function visibleSections(sections: CourseSection[], collapsed: Set<string>) {
    const ids = new Set(sections.map(s => s.id));
    const hasParentIds = sections.some(s => s.parent_id !== undefined);
    const byParent = new Map<string | null, CourseSection[]>();
    const stack: CourseSection[] = [];
    for (const s of sections) {
        let parent: string | null = null;
        if (hasParentIds) {
            parent = s.parent_id && ids.has(s.parent_id) ? s.parent_id : null;
        } else {
            while (stack.length && (stack[stack.length - 1].level ?? 0) >= (s.level ?? 0)) stack.pop();
            parent = stack.length ? stack[stack.length - 1].id : null;
            stack.push(s);
        }
        byParent.set(parent, [...(byParent.get(parent) ?? []), s]);
    }
    const rows: Array<{ section: CourseSection; indentLevel: number; hasChildren: boolean }> = [];
    const seen = new Set<string>();
    const walk = (s: CourseSection, indentLevel: number) => {
        if (seen.has(s.id)) return;
        seen.add(s.id);
        const kids = byParent.get(s.id) ?? [];
        rows.push({ section: s, indentLevel, hasChildren: kids.length > 0 });
        if (!collapsed.has(s.id)) kids.forEach(k => walk(k, indentLevel + 1));
    };
    (byParent.get(null) ?? []).forEach(s => walk(s, 0));
    return rows;
}

// Simple word-based title similarity using Jaccard index
function getTitleSimilarity(title1: string, title2: string): number {
    const words1 = new Set(title1.toLowerCase().split(/\s+/).filter(w => w.length > 2));
    const words2 = new Set(title2.toLowerCase().split(/\s+/).filter(w => w.length > 2));
    if (words1.size === 0 || words2.size === 0) return 0;

    const intersection = [...words1].filter(w => words2.has(w)).length;
    const union = new Set([...words1, ...words2]).size;
    return intersection / union;
}

// Calculate concept overlap using Jaccard index
function getConceptOverlap(concepts1: string[], concepts2: string[]): number {
    const set1 = new Set(concepts1.map(c => c.toLowerCase()));
    const set2 = new Set(concepts2.map(c => c.toLowerCase()));
    if (set1.size === 0 || set2.size === 0) return 0;

    const intersection = [...set1].filter(c => set2.has(c)).length;
    const union = new Set([...set1, ...set2]).size;
    return intersection / union;
}

// Combined similarity score (weighted average)
function getSimilarityScore(section1: CourseSection, section2: CourseSection): number {
    const titleSim = getTitleSimilarity(section1.title, section2.title);
    const conceptSim = getConceptOverlap(section1.concepts || [], section2.concepts || []);
    // Weight: 30% title, 70% concepts
    return titleSim * 0.3 + conceptSim * 0.7;
}

// A section with where it sits: ancestor titles (root = '') and its place in its course's outline (0..1)
type SectionEntry = { section: CourseSection; groupIdx: number; courseId: string; path: string; position: number };

// Titles of the ancestors, so same-titled siblings can be told apart by what they sit under
function pathSimilarity(a: string, b: string): number {
    if (!a && !b) return 1;
    if (!a || !b) return 0;
    return getTitleSimilarity(a, b);
}

// Order candidates for a target: score, then same parent path, then nearer position, then id
function compareMatches(
    target: SectionEntry,
    a: { entry: SectionEntry; score: number },
    b: { entry: SectionEntry; score: number }
): number {
    if (Math.abs(a.score - b.score) > 1e-9) return b.score - a.score;
    const pathDiff = pathSimilarity(target.path, b.entry.path) - pathSimilarity(target.path, a.entry.path);
    if (pathDiff !== 0) return pathDiff;
    const posDiff = Math.abs(target.position - a.entry.position) - Math.abs(target.position - b.entry.position);
    if (posDiff !== 0) return posDiff;
    return a.entry.section.id < b.entry.section.id ? -1 : a.entry.section.id > b.entry.section.id ? 1 : 0;
}

// Candidates in other courses (same column or not) above the threshold, best first
function rankedMatches(target: SectionEntry, allSections: SectionEntry[], threshold: number) {
    return allSections
        .filter(s => s.courseId !== target.courseId)
        .map(s => ({ entry: s, score: getSimilarityScore(target.section, s.section) }))
        .filter(m => m.score >= threshold)
        .sort((a, b) => compareMatches(target, a, b));
}

// Same business unit = same column; those matches are drawn dashed
type MatchKind = 'same-bu' | 'cross-bu';
const matchKind = (a: SectionEntry, b: SectionEntry): MatchKind => (a.groupIdx === b.groupIdx ? 'same-bu' : 'cross-bu');

// Find similar sections across all courses
function findSimilarSections(
    sectionId: string,
    allSections: SectionEntry[],
    threshold: number = 0.25
): Array<{ sectionId: string; score: number; kind: MatchKind }> {
    const targetSection = allSections.find(s => s.section.id === sectionId);
    if (!targetSection) return [];

    return rankedMatches(targetSection, allSections, threshold)
        .map(m => ({ sectionId: m.entry.section.id, score: m.score, kind: matchKind(targetSection, m.entry) }));
}

export const StagingArea: React.FC = () => {
    const { selectedSourceIds } = useSelectionStore();
    const { setStagingMode, setProjectId } = useAppStore();
    const [groups, setGroups] = useState<StagingGroup[]>([]);
    const [loading, setLoading] = useState(true);
    const [strategy, setStrategy] = useState<'union' | 'intersection' | 'master_outline'>('union');
    const [sharedConcepts, setSharedConcepts] = useState<Set<string>>(new Set());
    const [masterCourseId, setMasterCourseId] = useState<string | null>(null);
    const [templates, setTemplates] = useState<Array<{ name: string; display_name: string }>>([]);
    const [selectedTemplate, setSelectedTemplate] = useState<string>("standard");
    const [generating, setGenerating] = useState(false);

    // New state for similarity features
    const [hoveredSectionId, setHoveredSectionId] = useState<string | null>(null);
    const [highlightedSections, setHighlightedSections] = useState<Map<string, MatchKind>>(new Map());
    // Section ids whose subtree is folded (local, not persisted)
    const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
    const [matchingConcepts, setMatchingConcepts] = useState<Set<string>>(new Set());

    // Refs for scroll sync
    const columnRefs = useRef<(HTMLDivElement | null)[]>([]);
    const sectionRefs = useRef<Map<string, HTMLDivElement>>(new Map());

    // Flatten all sections for similarity lookup
    const allSections = useMemo(() => {
        const result: SectionEntry[] = [];
        groups.forEach((group, groupIdx) => {
            group.courses.forEach(course => {
                const byId = new Map(course.sections.map(s => [s.id, s]));
                const pathOf = (s: CourseSection) => {
                    const titles: string[] = [];
                    const seen = new Set([s.id]);
                    let p = s.parent_id ? byId.get(s.parent_id) : undefined;
                    while (p && !seen.has(p.id)) {
                        seen.add(p.id);
                        titles.unshift(p.title);
                        p = p.parent_id ? byId.get(p.parent_id) : undefined;
                    }
                    return titles.join(' / ');
                };
                const span = Math.max(1, course.sections.length - 1);
                course.sections.forEach((section, i) => {
                    if (isEmptySection(section)) return;
                    result.push({ section, groupIdx, courseId: course.id, path: pathOf(section), position: i / span });
                });
            });
        });
        return result;
    }, [groups]);

    // Compute similarity color groups - only sections with matches in another course get colored
    const sectionColorMap = useMemo(() => {
        const colorMap = new Map<string, { color: string; kind: MatchKind }>();
        const matchPairs: Array<{ id1: string; id2: string; score: number; kind: MatchKind }> = [];

        // Only mutual best matches share a colour: A's best in B's course is B and B's best in A's course is A,
        // so same-titled siblings cannot both join one partner
        const bestIn = new Map<string, SectionEntry>(); // `${sectionId}|${courseId}` -> best candidate there
        allSections.forEach(target => {
            const best = new Map<string, { entry: SectionEntry; score: number }>();
            rankedMatches(target, allSections, 0.2).forEach(m => {
                if (!best.has(m.entry.courseId)) best.set(m.entry.courseId, m);
            });
            best.forEach((m, c) => bestIn.set(`${target.section.id}|${c}`, m.entry));
        });
        allSections.forEach(a => {
            allSections.forEach(b => {
                if (a.courseId >= b.courseId) return; // each course pair once
                if (bestIn.get(`${a.section.id}|${b.courseId}`) === b && bestIn.get(`${b.section.id}|${a.courseId}`) === a) {
                    matchPairs.push({ id1: a.section.id, id2: b.section.id, score: getSimilarityScore(a.section, b.section), kind: matchKind(a, b) });
                }
            });
        });

        // Group matched pairs - sections that match get the same color
        const colorGroups: Set<string>[] = [];

        matchPairs.forEach(({ id1, id2 }) => {
            // Find existing groups containing either id
            const group1Idx = colorGroups.findIndex(g => g.has(id1));
            const group2Idx = colorGroups.findIndex(g => g.has(id2));

            if (group1Idx === -1 && group2Idx === -1) {
                // Neither in a group - create new group
                colorGroups.push(new Set([id1, id2]));
            } else if (group1Idx !== -1 && group2Idx === -1) {
                // Only id1 in a group - add id2 to it
                colorGroups[group1Idx].add(id2);
            } else if (group1Idx === -1 && group2Idx !== -1) {
                // Only id2 in a group - add id1 to it
                colorGroups[group2Idx].add(id1);
            } else if (group1Idx !== group2Idx) {
                // Both in different groups - merge
                colorGroups[group2Idx].forEach(id => colorGroups[group1Idx].add(id));
                colorGroups.splice(group2Idx, 1);
            }
            // If both already in same group, do nothing
        });

        // Assign colors to groups
        colorGroups.forEach((group, idx) => {
            const color = SIMILARITY_COLORS[idx % SIMILARITY_COLORS.length];
            group.forEach(sectionId => {
                // cross-bu wins when a section has partners of both kinds
                const kind: MatchKind = matchPairs.some(m => m.kind === 'cross-bu' && (m.id1 === sectionId || m.id2 === sectionId))
                    ? 'cross-bu' : 'same-bu';
                colorMap.set(sectionId, { color, kind });
            });
        });

        return colorMap;
    }, [allSections]);

    // Handle hover - find and highlight similar sections
    const handleSectionHover = useCallback((sectionId: string | null) => {
        setHoveredSectionId(sectionId);
        if (!sectionId) {
            setHighlightedSections(new Map());
            setMatchingConcepts(new Set());
            return;
        }

        const similar = findSimilarSections(sectionId, allSections, 0.2);
        setHighlightedSections(new Map(similar.map(s => [s.sectionId, s.kind])));

        // Find concepts that are shared between hovered section and highlighted sections
        const hoveredSection = allSections.find(s => s.section.id === sectionId);
        if (hoveredSection && similar.length > 0) {
            const hoveredConcepts = new Set((hoveredSection.section.concepts || []).map(c => c.toLowerCase()));
            const sharedConceptsSet = new Set<string>();

            similar.forEach(({ sectionId: matchId }) => {
                const matchSection = allSections.find(s => s.section.id === matchId);
                if (matchSection) {
                    (matchSection.section.concepts || []).forEach(c => {
                        if (hoveredConcepts.has(c.toLowerCase())) {
                            sharedConceptsSet.add(c.toLowerCase());
                        }
                    });
                }
            });
            setMatchingConcepts(sharedConceptsSet);
        } else {
            setMatchingConcepts(new Set());
        }
    }, [allSections]);

    // Handle click - scroll other columns to matching sections
    const handleSectionClick = useCallback((sectionId: string) => {
        const similar = findSimilarSections(sectionId, allSections, 0.2);
        if (similar.length === 0) return;

        // Find best match per course (always another course)
        const clickedSection = allSections.find(s => s.section.id === sectionId);
        if (!clickedSection) return;

        // Scroll to first similar section in each other course
        const scrolledCourses = new Set<string>();
        similar.forEach(({ sectionId: matchId }) => {
            const match = allSections.find(s => s.section.id === matchId);
            if (!match || match.courseId === clickedSection.courseId) return;
            if (scrolledCourses.has(match.courseId)) return;

            scrolledCourses.add(match.courseId);

            // Scroll to element
            const element = sectionRefs.current.get(matchId);
            if (element) {
                element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                // Add pulse animation
                element.classList.add('animate-pulse-once');
                setTimeout(() => element.classList.remove('animate-pulse-once'), 1000);
            }
        });
    }, [allSections]);

    // Fetch sections for all selected courses
    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                // First, get the tree to know which BU each course belongs to
                const tree = await api.getSourceTree();

                // Fetch sections for each selected course
                const coursesData: { id: string; title: string; filename?: string | null; version?: string | null; bu: string; sections: CourseSection[] }[] = [];

                for (const courseId of Array.from(selectedSourceIds)) {
                    // Find the course in the tree to get its BU
                    let courseBU = 'Unknown';
                    let courseTitle = '';
                    let courseFile: string | null | undefined;
                    let courseVersion: string | null | undefined;

                    for (const bu of tree) {
                        const course = bu.children?.find(c => c.id === courseId);
                        if (course) {
                            courseBU = bu.name;
                            courseTitle = course.name;
                            courseFile = course.filename;
                            courseVersion = course.version;
                            break;
                        }
                    }

                    // Fetch sections
                    const sections = await api.getCourseSections(courseId);
                    coursesData.push({
                        id: courseId,
                        title: courseTitle,
                        filename: courseFile,
                        version: courseVersion,
                        bu: courseBU,
                        sections
                    });
                }

                // Group by BU
                const grouped = coursesData.reduce((acc, course) => {
                    const existing = acc.find(g => g.buName === course.bu);
                    if (existing) {
                        existing.courses.push({
                            id: course.id,
                            title: course.title,
                            filename: course.filename,
                            version: course.version,
                            sections: course.sections
                        });
                    } else {
                        acc.push({
                            buName: course.bu,
                            courses: [{
                                id: course.id,
                                title: course.title,
                                filename: course.filename,
                                version: course.version,
                                sections: course.sections
                            }]
                        });
                    }
                    return acc;
                }, [] as StagingGroup[]);

                setGroups(grouped);

                // Calculate shared concepts (present in at least 2 BUs)
                if (grouped.length >= 2) {
                    const conceptsByBU = grouped.map(g => {
                        const concepts = new Set<string>();
                        g.courses.forEach(c => {
                            c.sections.filter(s => !isEmptySection(s)).forEach(s => {
                                s.concepts?.forEach(concept => concepts.add(concept));
                            });
                        });
                        return concepts;
                    });

                    const shared = new Set<string>();
                    conceptsByBU.forEach((buConcepts, i) => {
                        buConcepts.forEach(concept => {
                            // Check if this concept appears in at least one other BU
                            const appearsInOtherBU = conceptsByBU.some((otherBUConcepts, j) =>
                                i !== j && otherBUConcepts.has(concept)
                            );
                            if (appearsInOtherBU) {
                                shared.add(concept);
                            }
                        });
                    });

                    setSharedConcepts(shared);
                }

            } catch (error) {
                console.error('Failed to fetch staging data:', error);
            } finally {
                setLoading(false);
            }
        };

        if (selectedSourceIds.size > 0) {
            fetchData();
        }
    }, [selectedSourceIds]);

    // Fetch available templates
    useEffect(() => {
        const fetchTemplates = async () => {
            try {
                const data = await api.getTemplates();
                setTemplates(data.templates);
            } catch (error) {
                console.error('Error fetching templates:', error);
                // Fallback to standard
                setTemplates([{ name: 'standard', display_name: 'Standard' }]);
            }
        };
        fetchTemplates();
    }, []);

    const handleGenerate = async () => {
        if (generating) return;
        setGenerating(true);
        try {
            // Build the payload
            const { discipline } = useAppStore.getState();
            const payload: any = {
                title: projectTitle(discipline), // Must match createProjectIfNeeded logic
                domain: null,
                selected_source_ids: Array.from(selectedSourceIds)
            };

            // Add master_course_id if in master outline mode
            if (strategy === 'master_outline' && masterCourseId) {
                payload.master_course_id = masterCourseId;
            }

            // Add selected template
            payload.template_name = selectedTemplate;

            const result = await api.generateProjectSkeleton(payload);

            // Switch back to consolidation view and load the new project
            setStagingMode(false);
            setProjectId(result.project_id);
        } catch (error) {
            console.error('Failed to generate outline:', error);
        } finally {
            setGenerating(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin text-brand-teal">
                    <Layers size={48} />
                </div>
            </div>
        );
    }

    const gridClass = groups.length === 1 ? 'grid-cols-1' : groups.length === 2 ? 'grid-cols-2' : 'grid-cols-3';

    return (
        <div className="flex flex-col h-full bg-slate-50">
            {/* Header with Generate Button */}
            <div className="bg-white border-b border-slate-200 p-4 space-y-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Layers className="text-blue-600" size={24} />
                        <div>
                            <h2 className="font-bold text-slate-800">Staging & Comparison</h2>
                            <p className="text-xs text-slate-500">Review selected courses before generating outline. Similar sections are color-coded.</p>
                        </div>
                    </div>

                    {/* Template Selector and Generate Button */}
                    <div className="flex items-center gap-3">
                        <label className="text-sm font-medium text-slate-700">Template:</label>
                        <select
                            value={selectedTemplate}
                            onChange={(e) => setSelectedTemplate(e.target.value)}
                            className="px-3 py-1.5 rounded-md border-2 border-slate-300 text-sm font-medium text-slate-700 bg-white hover:border-blue-400 focus:outline-none focus:border-blue-500 transition-colors"
                        >
                            {templates.map(template => (
                                <option key={template.name} value={template.name}>
                                    {template.display_name}
                                </option>
                            ))}
                        </select>

                        <button
                            onClick={handleGenerate}
                            disabled={generating}
                            className={clsx(
                                "flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors",
                                generating
                                    ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                                    : "bg-blue-600 text-white hover:bg-blue-700"
                            )}
                        >
                            {generating ? (
                                <>
                                    <div className="animate-spin h-4 w-4 border-2 border-slate-500 border-t-transparent rounded-full" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <Zap size={16} />
                                    Generate Outline
                                </>
                            )}
                        </button>
                    </div>
                </div>

                {/* Strategy Toggle */}
                <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-slate-700">Merge Strategy:</span>
                    <div className="flex gap-3">
                        <button
                            onClick={() => setStrategy('union')}
                            className={clsx(
                                'px-4 py-2 rounded-md text-sm font-medium transition-all border-2',
                                strategy === 'union'
                                    ? 'bg-blue-600 text-white border-blue-600'
                                    : 'bg-white text-slate-700 border-slate-300 hover:border-blue-400 hover:bg-slate-50'
                            )}
                        >
                            Union (All Concepts)
                        </button>
                        <button
                            onClick={() => setStrategy('intersection')}
                            className={clsx(
                                'px-4 py-2 rounded-md text-sm font-medium transition-all border-2',
                                strategy === 'intersection'
                                    ? 'bg-blue-600 text-white border-blue-600'
                                    : 'bg-white text-slate-700 border-slate-300 hover:border-blue-400 hover:bg-slate-50'
                            )}
                        >
                            Intersection (Shared Only)
                        </button>
                        <button
                            onClick={() => {
                                setStrategy('master_outline');
                                setMasterCourseId(null);
                            }}
                            className={clsx(
                                'px-4 py-2 rounded-md text-sm font-medium transition-all border-2',
                                strategy === 'master_outline'
                                    ? 'bg-amber-600 text-white border-amber-600'
                                    : 'bg-white text-slate-700 border-slate-300 hover:border-amber-400 hover:bg-slate-50'
                            )}
                            title="Select a master course to use as the base outline structure"
                        >
                            🏆 Master Outline
                        </button>
                    </div>
                    {strategy === 'intersection' && sharedConcepts.size > 0 && (
                        <span className="text-xs text-slate-500">
                            {sharedConcepts.size} shared concepts
                        </span>
                    )}
                    {strategy === 'master_outline' && !masterCourseId && (
                        <span className="text-xs text-amber-600 font-medium">
                            ⚠️ Select a master course below
                        </span>
                    )}
                    {strategy === 'master_outline' && masterCourseId && (
                        <span className="text-xs text-green-600 font-medium">
                            ✓ Master course selected
                        </span>
                    )}
                </div>
            </div>

            {/* Main Grid */}
            <div className={clsx('grid h-full divide-x divide-gray-200 overflow-hidden', gridClass)}>
                {groups.map((group, idx) => (
                    <div
                        key={idx}
                        className="flex flex-col overflow-hidden"
                        ref={el => { columnRefs.current[idx] = el; }}
                    >
                        {/* Column Header */}
                        <div className="bg-slate-100 border-b border-slate-200 p-3 flex-shrink-0">
                            <h3 className="font-bold text-sm text-slate-700">{group.buName}</h3>
                            <p className="text-xs text-slate-500">
                                {group.courses.length} course{group.courses.length !== 1 ? 's' : ''}
                            </p>
                        </div>

                        {/* Course Cards */}
                        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
                            {group.courses.map(course => {
                                const isMaster = masterCourseId === course.id;
                                const courseHasSharedConcepts = course.sections.some(s =>
                                    s.concepts?.some(c => sharedConcepts.has(c))
                                );
                                const courseIsRelevant = strategy === 'union' || courseHasSharedConcepts;

                                return (
                                    <div
                                        key={course.id}
                                        className={clsx(
                                            "border rounded shadow-sm transition-all",
                                            isMaster
                                                ? "border-amber-500 bg-amber-50 ring-4 ring-amber-200"
                                                : courseIsRelevant
                                                    ? "border-blue-400 bg-white ring-2 ring-blue-100"
                                                    : "border-gray-300 bg-white opacity-60"
                                        )}
                                    >
                                        {/* Course Title */}
                                        <div className={clsx(
                                            "p-3 border-b",
                                            isMaster
                                                ? "bg-amber-100 border-amber-300"
                                                : courseIsRelevant
                                                    ? "bg-blue-50 border-blue-200"
                                                    : "bg-gray-100 border-gray-200"
                                        )}>
                                            <h4 className={clsx(
                                                "font-bold text-sm flex items-center gap-2",
                                                isMaster ? "text-amber-900" : courseIsRelevant ? "text-slate-800" : "text-slate-500"
                                            )}>
                                                {isMaster && <span className="text-lg">🏆</span>}
                                                <span title={courseTooltip(course.title, course.id)}>{course.title}</span>
                                            </h4>
                                            {courseSubtitle(course) && (
                                                <p className="text-[10px] text-slate-400 truncate" title={courseTooltip(course.title, course.id)}>{courseSubtitle(course)}</p>
                                            )}
                                            <div className="flex items-center justify-between mt-1">
                                                <p className="text-xs text-slate-500">
                                                    {course.sections.length} section{course.sections.length !== 1 ? 's' : ''}
                                                </p>
                                                {strategy === 'master_outline' && !isMaster && (
                                                    <button
                                                        onClick={() => setMasterCourseId(course.id)}
                                                        className="px-2 py-1 text-xs font-medium bg-amber-600 text-white rounded hover:bg-amber-700 transition-colors"
                                                        title="Set as master outline"
                                                    >
                                                        ⭐ Set as Master
                                                    </button>
                                                )}
                                            </div>
                                        </div>

                                        {/* Sections List */}
                                        <div className="p-3 space-y-1">
                                            {course.sections.length === 0 ? (
                                                <p className="text-xs text-slate-400 italic">No sections found</p>
                                            ) : (
                                                visibleSections(course.sections, collapsedSections).map(({ section, indentLevel, hasChildren }) => {
                                                    const similarity = sectionColorMap.get(section.id);
                                                    const hlKind = highlightedSections.get(section.id);
                                                    const matchAttr = similarity?.kind ?? hlKind;
                                                    const isHovered = hoveredSectionId === section.id;
                                                    const isHighlighted = hlKind !== undefined;
                                                    const hasMatches = highlightedSections.size > 0;

                                                    return (
                                                        <div
                                                            key={section.id}
                                                            ref={el => { if (el) sectionRefs.current.set(section.id, el); }}
                                                            className={clsx(
                                                                "pb-2 border-b border-slate-100 last:border-0 rounded-md px-2 py-1 transition-all cursor-pointer",
                                                                similarity?.color,
                                                                // Same-business-unit matches: dashed outline instead of solid
                                                                similarity?.kind === 'same-bu' && "border-2 border-dashed",
                                                                // Hovered section: fill background only if it has matches
                                                                isHovered && hasMatches && "ring-2 ring-blue-500 bg-blue-50",
                                                                // Hovered section with no matches: just show outline
                                                                isHovered && !hasMatches && "ring-1 ring-slate-400",
                                                                // Highlighted matching sections in other columns
                                                                isHighlighted && hlKind === 'cross-bu' && "ring-2 ring-purple-500 bg-purple-50",
                                                                isHighlighted && hlKind === 'same-bu' && "border-2 border-dashed border-purple-500 bg-purple-50"
                                                            )}
                                                            style={{ marginLeft: `${Math.min(indentLevel, MAX_INDENT_STEPS) * 16}px` }}
                                                            onMouseEnter={() => handleSectionHover(section.id)}
                                                            onMouseLeave={() => handleSectionHover(null)}
                                                            onClick={() => handleSectionClick(section.id)}
                                                            data-match={matchAttr}
                                                            title={matchAttr === 'same-bu' ? "Similar section in the same business unit. Click to scroll to similar sections" : "Click to scroll to similar sections"}
                                                        >
                                                            <div className="flex items-start gap-2">
                                                                {hasChildren && (
                                                                    <button
                                                                        type="button"
                                                                        data-testid="section-toggle"
                                                                        className="mt-0.5 flex-shrink-0 text-slate-400 hover:text-slate-700"
                                                                        title={collapsedSections.has(section.id) ? 'Expand subsections' : 'Collapse subsections'}
                                                                        onClick={e => {
                                                                            e.stopPropagation();
                                                                            setCollapsedSections(prev => {
                                                                                const next = new Set(prev);
                                                                                if (!next.delete(section.id)) next.add(section.id);
                                                                                return next;
                                                                            });
                                                                        }}
                                                                    >
                                                                        {collapsedSections.has(section.id) ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                                                                    </button>
                                                                )}
                                                                {indentLevel > MAX_INDENT_STEPS && (
                                                                    <span
                                                                        data-testid="depth-badge"
                                                                        className="mt-0.5 flex-shrink-0 text-[9px] leading-3 font-semibold text-slate-400 border border-slate-200 rounded px-1"
                                                                        title={`Level ${indentLevel + 1}`}
                                                                    >
                                                                        {indentLevel + 1}
                                                                    </span>
                                                                )}
                                                                <ArrowRight
                                                                    size={12}
                                                                    className={clsx(
                                                                        "mt-0.5 flex-shrink-0",
                                                                        indentLevel === 0 ? "text-blue-600" : "text-slate-400"
                                                                    )}
                                                                />
                                                                <div className="flex-1 min-w-0">
                                                                    <p className={clsx(
                                                                        "text-xs",
                                                                        indentLevel === 0
                                                                            ? "font-bold text-slate-800"
                                                                            : "font-medium text-slate-700"
                                                                    )}>
                                                                        {section.title}
                                                                    {isEmptySection(section) && (
                                                                        <span
                                                                            data-testid="empty-badge"
                                                                            className="ml-1.5 text-[9px] leading-3 font-semibold text-slate-400 border border-slate-200 rounded px-1 align-middle"
                                                                            title="No slides and no concepts of its own"
                                                                        >
                                                                            empty
                                                                        </span>
                                                                    )}
                                                                    </p>
                                                                    {/* Concepts */}
                                                                    {section.concepts && section.concepts.length > 0 && (
                                                                        <div className="flex flex-wrap gap-1 mt-1">
                                                                            {section.concepts.map((concept, i) => {
                                                                                const isShared = sharedConcepts.has(concept);
                                                                                const isDimmed = strategy === 'intersection' && !isShared;
                                                                                const isMatchingConcept = matchingConcepts.has(concept.toLowerCase()) &&
                                                                                    (isHovered || isHighlighted);

                                                                                return (
                                                                                    <span
                                                                                        key={i}
                                                                                        className={clsx(
                                                                                            'text-[10px] px-1.5 py-0.5 rounded border transition-all',
                                                                                            // Matching concept highlight (when section is hovered/highlighted)
                                                                                            isMatchingConcept
                                                                                                ? 'bg-emerald-100 text-emerald-700 border-emerald-400 font-bold ring-1 ring-emerald-300'
                                                                                                : isDimmed
                                                                                                    ? 'bg-slate-50 text-slate-300 border-slate-200'
                                                                                                    : isShared && strategy === 'intersection'
                                                                                                        ? 'bg-blue-100 text-blue-700 border-blue-300 font-medium'
                                                                                                        : 'bg-slate-100 text-slate-600 border-slate-200'
                                                                                        )}
                                                                                    >
                                                                                        {concept}
                                                                                    </span>
                                                                                );
                                                                            })}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                })
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};
