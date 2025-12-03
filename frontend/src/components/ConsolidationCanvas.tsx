import React, { useEffect } from 'react';
import { Plus, GitMerge } from 'lucide-react';
import { api } from '../api';
import { SynthBlock } from './SynthBlock';

interface ConsolidationCanvasProps {
    projectId: string | null;
    setProjectId: (id: string) => void;
    discipline: string;
    refreshTrigger?: number;
}

import { useAppStore } from '../store';

export const ConsolidationCanvas: React.FC<ConsolidationCanvasProps> = ({ projectId, setProjectId, discipline, refreshTrigger }) => {
    const structure = useAppStore(state => state.structure);
    const fetchStructure = useAppStore(state => state.fetchStructure);
    const addNode = useAppStore(state => state.addNode);

    // Initial Project Creation if needed
    useEffect(() => {
        // Avoid infinite loops or redundant creation by checking loading/error states
        // But here we just rely on simple check.
        if (!projectId) {
            // Auto-create for demo
            // Add a flag to prevent double creation in React Strict Mode
            let ignore = false;

            api.createDraftProject(`Unified ${discipline} Standard`).then(p => {
                if (ignore) return;
                setProjectId(p.id);
                // Add a default chapter
                api.addDraftNode(p.id, "Topic 1").then(() => {
                    if (ignore) return;
                    fetchStructure();
                });
            });

            return () => { ignore = true; };
        } else {
            fetchStructure();
        }
    }, [projectId, discipline, refreshTrigger, setProjectId, fetchStructure]);

    return (
        <div className="flex-1 bg-slate-50 p-6 flex flex-col h-full overflow-y-auto custom-scrollbar">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-brand-teal" />
                    <h2 className="font-bold text-slate-800 text-lg">Consolidated Outline</h2>
                </div>
                <button
                    onClick={() => projectId && addNode(projectId, "New Topic")}
                    className="text-brand-teal hover:bg-brand-teal/10 p-2 rounded-full transition-colors"
                >
                    <Plus size={20} />
                </button>
            </div>

            {/* Canvas Area */}
            <div className="max-w-4xl mx-auto w-full space-y-6 pb-20">
                {/* Root Project Title */}
                <div className="text-center mb-10">
                    <h1 className="text-3xl font-bold text-slate-800 tracking-tight">
                        {structure.find(n => n.id === projectId)?.title || "Loading..."}
                    </h1>
                    <p className="text-slate-500 text-sm mt-2">Global Standardization Project • {discipline}</p>
                </div>

                {/* Draft Nodes (SynthBlocks) */}
                <div className="space-y-6">
                    {structure.filter(n => n.parent_id === projectId).map(node => (
                        <SynthBlock key={node.id} node={node} onRefresh={fetchStructure} />
                    ))}
                </div>

                {/* Empty State / Placeholder */}
                {structure.length <= 1 && (
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
