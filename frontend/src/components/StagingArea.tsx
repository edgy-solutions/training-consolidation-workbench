import React, { useEffect, useState } from 'react';
import { ArrowRight, Layers, Zap } from 'lucide-react';
import { api } from '../api';
import type { CourseSection } from '../api';
import { useSelectionStore } from '../stores/selectionStore';
import { useAppStore } from '../store';
import clsx from 'clsx';

interface StagingGroup {
    buName: string;
    courses: {
        id: string;
        title: string;
        sections: CourseSection[];
    }[];
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

    // Fetch sections for all selected courses
    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                // First, get the tree to know which BU each course belongs to
                const tree = await api.getSourceTree();

                // Fetch sections for each selected course
                const coursesData: { id: string; title: string; bu: string; sections: CourseSection[] }[] = [];

                for (const courseId of Array.from(selectedSourceIds)) {
                    // Find the course in the tree to get its BU
                    let courseBU = 'Unknown';
                    let courseTitle = '';

                    for (const bu of tree) {
                        const course = bu.children?.find(c => c.id === courseId);
                        if (course) {
                            courseBU = bu.name;
                            courseTitle = course.name;
                            break;
                        }
                    }

                    // Fetch sections
                    const sections = await api.getCourseSections(courseId);
                    coursesData.push({
                        id: courseId,
                        title: courseTitle,
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
                            sections: course.sections
                        });
                    } else {
                        acc.push({
                            buName: course.bu,
                            courses: [{
                                id: course.id,
                                title: course.title,
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
                            c.sections.forEach(s => {
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
            const payload: any = {
                title: `Consolidated Curriculum`,
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
                            <p className="text-xs text-slate-500">Review selected courses before generating outline</p>
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
                    <div key={idx} className="flex flex-col overflow-hidden">
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
                                                {course.title}
                                            </h4>
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
                                                course.sections.map(section => {
                                                    // Calculate indentation based on level (0 = no indent, 1+ = indent)
                                                    const indentLevel = section.level || 0;

                                                    return (
                                                        <div
                                                            key={section.id}
                                                            className="pb-2 border-b border-slate-100 last:border-0"
                                                            style={{ marginLeft: `${indentLevel * 16}px` }}
                                                        >
                                                            <div className="flex items-start gap-2">
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
                                                                    </p>
                                                                    {/* Concepts */}
                                                                    {section.concepts && section.concepts.length > 0 && (
                                                                        <div className="flex flex-wrap gap-1 mt-1">
                                                                            {section.concepts.map((concept, i) => {
                                                                                const isShared = sharedConcepts.has(concept);
                                                                                const isDimmed = strategy === 'intersection' && !isShared;

                                                                                return (
                                                                                    <span
                                                                                        key={i}
                                                                                        className={clsx(
                                                                                            'text-[10px] px-1.5 py-0.5 rounded border',
                                                                                            isDimmed
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
