import { useSelectionStore } from '../stores/selectionStore';
import { useAppStore } from '../store';
import { useState } from 'react';
import api from '../api';

export function SidebarActionPanel() {
    const { selectedSourceIds, clearSelection } = useSelectionStore();
    const { setProjectId } = useAppStore();
    const [strategy, setStrategy] = useState('union');
    const [loading, setLoading] = useState(false);

    const count = selectedSourceIds.size;

    // Only show when items are selected
    if (count === 0) return null;

    const handleGenerate = async () => {
        setLoading(true);
        try {
            const response = await api.generateProjectSkeleton({
                title: "New Consolidated Curriculum",
                domain: null,
                selected_source_ids: Array.from(selectedSourceIds)
            });

            console.log('Generated project:', response);

            // Load the generated project directly from the response
            setProjectId(response.project_id);

            // Construct the root project node (needed for ConsolidationCanvas to show title)
            const rootNode = {
                id: response.project_id,
                title: response.title,
                status: 'draft',
                source_refs: [],
                parent_id: undefined,
                // Add other required fields for TargetDraftNode
                content_markdown: null,
                rationale: null,
                is_suggestion: false,
                suggested_source_ids: []
            };

            // Combine root node with generated children
            // We need to cast rootNode to any or TargetDraftNode because strict typing might complain about missing optional fields
            const fullStructure = [rootNode as any, ...(response.nodes || [])];

            // Set the structure directly
            useAppStore.setState({ structure: fullStructure });

            // Show success message
            alert(`✅ Generated curriculum!\n\nProject ID: ${response.project_id}\nSections: ${response.nodes?.length || 0}`);

            // Clear selection
            clearSelection();
        } catch (error) {
            console.error('Generation failed:', error);
            alert('❌ Failed to generate curriculum. Check console for details.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed bottom-4 left-4 right-4 md:right-auto md:w-80 
                    bg-white border border-gray-200 rounded-lg shadow-xl p-4 z-50">
            <div className="flex flex-col gap-3">
                {/* Selection count */}
                <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">
                        {count} item{count !== 1 ? 's' : ''} selected
                    </span>
                    <button
                        onClick={() => clearSelection()}
                        className="text-xs text-gray-500 hover:text-gray-700"
                    >
                        Clear
                    </button>
                </div>

                {/* Strategy dropdown */}
                <div>
                    <label className="block text-xs text-gray-600 mb-1">
                        Merge Strategy
                    </label>
                    <select
                        value={strategy}
                        onChange={(e) => setStrategy(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm
                       focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        <option value="union">Union/Superset</option>
                        <option value="intersection">Intersection/Core</option>
                        <option value="base">Base on First</option>
                    </select>
                </div>

                {/* Generate button */}
                <button
                    onClick={handleGenerate}
                    disabled={loading}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 
                     disabled:bg-gray-400 disabled:cursor-not-allowed 
                     flex items-center justify-center gap-2 font-medium transition-colors"
                >
                    {loading ? (
                        <>
                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                                <circle
                                    className="opacity-25"
                                    cx="12"
                                    cy="12"
                                    r="10"
                                    stroke="currentColor"
                                    strokeWidth="4"
                                    fill="none"
                                />
                                <path
                                    className="opacity-75"
                                    fill="currentColor"
                                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                />
                            </svg>
                            Generating...
                        </>
                    ) : (
                        <>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M13 10V3L4 14h7v7l9-11h-7z"
                                />
                            </svg>
                            Generate Outline
                        </>
                    )}
                </button>
            </div>
        </div>
    );
}
