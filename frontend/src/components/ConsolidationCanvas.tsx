import React, { useEffect, useMemo } from 'react';
import { Plus, GitMerge, BookOpen, Shield, Wrench, ClipboardCheck } from 'lucide-react';
import { api } from '../api';
import { SynthBlock } from './SynthBlock';

interface ConsolidationCanvasProps {
    projectId: string | null;
    setProjectId: (id: string) => void;
    discipline: string;
    refreshTrigger?: number;
}

import { useAppStore } from '../store';

// Section type metadata for display
const SECTION_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
    'introduction': { label: 'Introduction', icon: BookOpen, color: 'text-blue-600' },
    'mandatory_safety': { label: 'Safety & Compliance', icon: Shield, color: 'text-red-600' },
    'technical': { label: 'Technical Content', icon: Wrench, color: 'text-indigo-600' },
    'mandatory_assessment': { label: 'Assessment', icon: ClipboardCheck, color: 'text-green-600' },
};

export const ConsolidationCanvas: React.FC<ConsolidationCanvasProps> = ({ projectId, setProjectId, discipline, refreshTrigger }) => {
    const structure = useAppStore(state => state.structure);
    const fetchStructure = useAppStore(state => state.fetchStructure);
    const addNode = useAppStore(state => state.addNode);

    // Initial Project Creation is handled by App.tsx -> store.createProjectIfNeeded
    // We just need to fetch structure when projectId changes
    useEffect(() => {
        if (projectId) {
            fetchStructure();
        }
    }, [projectId, refreshTrigger, fetchStructure]);

    // Get all project nodes (excluding the project root itself)
    const allProjectNodes = useMemo(() => {
        return structure.filter(n => n.id !== projectId);
    }, [structure, projectId]);

    // Build a map of parent -> children for hierarchy
    const childrenByParent = useMemo(() => {
        const map = new Map<string, typeof allProjectNodes>();
        for (const node of allProjectNodes) {
            const parentId = node.parent_id || '';
            if (!map.has(parentId)) {
                map.set(parentId, []);
            }
            map.get(parentId)!.push(node);
        }
        return map;
    }, [allProjectNodes]);

    // Get top-level nodes (direct children of project)
    const topLevelNodes = useMemo(() => {
        return childrenByParent.get(projectId || '') || [];
    }, [childrenByParent, projectId]);

    const groupedNodes = useMemo(() => {
        // Define order of section types
        const sectionOrder = ['introduction', 'mandatory_safety', 'technical', 'mandatory_assessment'];

        // Helper to collect node and all its descendants in order
        const collectWithDescendants = (node: typeof topLevelNodes[0], collected: typeof topLevelNodes) => {
            collected.push(node);
            const children = childrenByParent.get(node.id) || [];
            // Sort children by order
            children.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
            for (const child of children) {
                collectWithDescendants(child, collected);
            }
        };

        // Group nodes by section_type (top-level determines section type for group)
        const groups: Record<string, typeof topLevelNodes> = {};

        for (const node of topLevelNodes) {
            const type = node.section_type || 'technical';
            if (!groups[type]) {
                groups[type] = [];
            }
            // Collect the top-level node and all its descendants
            collectWithDescendants(node, groups[type]);
        }

        // Return ordered array of groups
        return sectionOrder
            .filter(type => groups[type]?.length > 0)
            .map(type => ({
                type,
                config: SECTION_CONFIG[type] || SECTION_CONFIG['technical'],
                nodes: groups[type]
            }));
    }, [topLevelNodes, childrenByParent]);

    return (
        <div className="flex-1 bg-slate-50 p-6 flex flex-col h-full overflow-y-auto custom-scrollbar">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-brand-teal" />
                    <h2 className="font-bold text-slate-800 text-lg">Consolidated Outline</h2>
                </div>
                <button
                    onClick={() => projectId && addNode(projectId, "New Module")}
                    className="text-brand-teal hover:bg-brand-teal/10 p-2 rounded-full transition-colors"
                    title="Add new section"
                >
                    <Plus size={20} />
                </button>
            </div>

            {/* Canvas Area */}
            <div className="max-w-4xl mx-auto w-full space-y-8 pb-20">
                {/* Root Project Title */}
                <div className="text-center mb-10">
                    <h1 className="text-3xl font-bold text-slate-800 tracking-tight">
                        {structure.find(n => n.id === projectId)?.title || "Loading..."}
                    </h1>
                    <p className="text-slate-500 text-sm mt-2">Global Standardization Project • {discipline}</p>
                </div>

                {/* Grouped Draft Nodes (SynthBlocks) */}
                {groupedNodes.map(group => {
                    const Icon = group.config.icon;
                    return (
                        <div key={group.type} className="space-y-4">
                            {/* Section Header */}
                            <div className="flex items-center gap-3 border-b border-slate-200 pb-2">
                                <Icon size={20} className={group.config.color} />
                                <h3 className={`font-semibold text-sm uppercase tracking-wide ${group.config.color}`}>
                                    {group.config.label}
                                </h3>
                                <span className="text-xs text-slate-400">
                                    ({group.nodes.length} {group.nodes.length === 1 ? 'module' : 'modules'})
                                </span>
                            </div>

                            {/* Nodes in this section - with hierarchy indentation */}
                            <div className="space-y-3 pl-4 border-l-2 border-slate-200">
                                {group.nodes.map(node => {
                                    const level = node.level ?? 0;
                                    const indentClass = level > 0 ? `ml-${Math.min(level * 6, 12)}` : '';
                                    const scaleClass = level > 0 ? 'scale-[0.97] origin-left' : '';

                                    return (
                                        <div
                                            key={node.id}
                                            className={`${indentClass} ${scaleClass} transition-all`}
                                            style={{ marginLeft: level > 0 ? `${level * 1.5}rem` : 0 }}
                                        >
                                            {level > 0 && (
                                                <div className="flex items-center gap-2 mb-1 text-xs text-slate-400">
                                                    <span className="w-4 h-px bg-slate-300" />
                                                    <span>Subsection</span>
                                                </div>
                                            )}
                                            <SynthBlock key={node.id} node={node} onRefresh={fetchStructure} />
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })}

                {/* Empty State / Placeholder */}
                {topLevelNodes.length === 0 && (
                    <div className="border-2 border-dashed border-slate-200 rounded-xl p-12 flex flex-col items-center justify-center text-slate-400 bg-slate-50/50">
                        <GitMerge size={48} className="mb-4 opacity-20" />
                        <p className="font-medium">Ready to Consolidate</p>
                        <p className="text-sm mt-1">Add a new Topic or drag legacy policies here to start.</p>
                    </div>
                )}
            </div>
        </div>
    );
};
