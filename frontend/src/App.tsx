import { DndContext, DragOverlay, useSensor, useSensors, MouseSensor, TouchSensor, pointerWithin } from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { TopBar } from './components/TopBar';
import { SourceBrowser } from './components/SourceBrowser';
import { ConsolidationCanvas } from './components/ConsolidationCanvas';
import { SlideInspector } from './components/SlideInspector';
import { StagingArea } from './components/StagingArea';
import { useAppStore } from './store';
import type { SourceSlide } from './api';
import { useEffect, useState } from 'react';

function App() {
  const { discipline, setDiscipline, projectId, setProjectId, createProjectIfNeeded, mapSlideToNode, stagingMode } = useAppStore();
  const [activeDragSlide, setActiveDragSlide] = useState<SourceSlide | null>(null);

  // Ensure a project exists for the current discipline
  useEffect(() => {
    createProjectIfNeeded();
  }, [discipline, createProjectIfNeeded]);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 10 } }),
    useSensor(TouchSensor)
  );

  const handleDragStart = (event: any) => {
    if (event.active.data.current?.slide) {
      setActiveDragSlide(event.active.data.current.slide);
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;

    if (!over) {
      setActiveDragSlide(null);
      return;
    }

    // Handle Sortable reordering within canvas
    if (active.data.current?.sortable) {
      // Dispatch custom event for visual reordering (until backend supports it)
      const event = new CustomEvent('slide-reorder', { detail: { activeId: active.id, overId: over.id } });
      window.dispatchEvent(event);
      setActiveDragSlide(null);
      return;
    }

    // Handle Drop from Source Browser to Canvas Target
    // Use 'over' directly as we know SynthBlock sets 'data'
    const overData = over.data.current;

    if (overData) {
      let targetNodeId = null;

      if (overData.type === 'target') {
        targetNodeId = overData.node.id;
      } else if (overData.type === 'sortable-item') {
        // Dropped onto an existing item in the list
        targetNodeId = overData.node.id;
      }

      // Try to get slide from active data, or fallback to activeDragSlide state
      const slide = active.data.current?.slide || activeDragSlide;

      if (targetNodeId && slide) {
        try {
          // Get fresh node from store using getState() to bypass any React closure staleness
          const currentStructure = useAppStore.getState().structure;
          const freshNode = currentStructure.find(n => n.id === targetNodeId);
          const currentSlides = freshNode?.source_refs || [];

          // Create new list, ensuring uniqueness
          const newSlides = Array.from(new Set([...currentSlides, slide.id]));

          await mapSlideToNode(targetNodeId, newSlides);
        } catch (err) {
          console.error("Error mapping slide:", err);
        }
      }
    }

    setActiveDragSlide(null);
  };

  return (
    <div className="h-screen flex flex-col">
      <DndContext
        sensors={sensors}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        collisionDetection={pointerWithin}
      >
        {/* Top Bar */}
        <TopBar discipline={discipline} setDiscipline={setDiscipline} />

        {/* Main Content Area - Three Resizable Panes */}
        <div className="flex-1 overflow-hidden">
          <PanelGroup direction="horizontal">

            {/* Left Pane: Source Browser (20%) */}
            <Panel defaultSize={20} minSize={15} className="bg-white border-r border-slate-200 relative">
              <SourceBrowser discipline={discipline} />
            </Panel>

            <PanelResizeHandle className="w-1 bg-slate-200 hover:bg-brand-teal transition-colors cursor-col-resize" />

            {/* Center Pane: Staging Area or Consolidation Canvas (50%) */}
            <Panel defaultSize={50} minSize={30} className="bg-slate-50">
              {stagingMode ? (
                <StagingArea />
              ) : (
                <ConsolidationCanvas
                  projectId={projectId}
                  setProjectId={setProjectId}
                  discipline={discipline}
                />
              )}
            </Panel>

            <PanelResizeHandle className="w-1 bg-slate-200 hover:bg-brand-teal transition-colors cursor-col-resize" />

            {/* Right Pane: Preview & Synthesis (30%) */}
            <Panel defaultSize={30} minSize={20} className="bg-white border-l border-slate-200">
              <SlideInspector />
            </Panel>

          </PanelGroup>
        </div>

        <DragOverlay>
          {activeDragSlide ? (
            <div className="w-64 bg-white p-2 rounded shadow-xl border border-brand-teal opacity-90 rotate-3 cursor-grabbing pointer-events-none">
              <div className="font-bold text-xs mb-1">Adding Slide...</div>
              <div className="text-xs text-slate-600 truncate">{activeDragSlide.id}</div>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}

export default App;
