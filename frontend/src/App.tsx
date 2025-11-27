import { DndContext, DragOverlay, useSensor, useSensors, MouseSensor, TouchSensor, pointerWithin } from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { TopBar } from './components/TopBar';
import { SourceBrowser } from './components/SourceBrowser';
import { ConsolidationCanvas } from './components/ConsolidationCanvas';
import { SlideInspector } from './components/SlideInspector';
import { useAppStore } from './store';
import type { SourceSlide } from './api';
import { useEffect, useState } from 'react';

function App() {
  const { discipline, setDiscipline, projectId, setProjectId, createProjectIfNeeded, mapSlideToNode } = useAppStore();
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
    setActiveDragSlide(null);

    if (!over) return;

    // Handle Sortable reordering within canvas
    if (active.data.current?.sortable) {
       // Dispatch custom event for visual reordering (until backend supports it)
       const event = new CustomEvent('slide-reorder', { detail: { activeId: active.id, overId: over.id } });
       window.dispatchEvent(event);
       return;
    }

    // Handle Drop from Source Browser to Canvas Target
    // Use 'over' directly as we know SynthBlock sets 'data'
    const overData = over.data.current;
    if (overData) {
      let targetNode = null;
      
      if (overData.type === 'target') {
          targetNode = overData.node;
      } else if (overData.type === 'sortable-item') {
          // Dropped onto an existing item in the list
          targetNode = overData.node;
      }

      const slide = active.data.current?.slide;

      if (targetNode && slide) {
        console.log(`Mapping slide ${slide.id} to node ${targetNode.id}`);
        await mapSlideToNode(targetNode.id, slide.id);
      }
    }
  };
  
  return (
    <div className="h-screen w-screen flex flex-col bg-slate-50 text-slate-900 font-sans overflow-hidden">
      <TopBar discipline={discipline} setDiscipline={setDiscipline} />
      
      <DndContext 
        sensors={sensors} 
        collisionDetection={pointerWithin}
        onDragStart={handleDragStart} 
        onDragEnd={handleDragEnd}
      >
        <div className="flex-1 overflow-hidden">
          <PanelGroup direction="horizontal">
            
            {/* Left Pane: Source Map (20%) */}
            <Panel defaultSize={20} minSize={15} className="bg-white border-r border-slate-200">
              <SourceBrowser discipline={discipline} />
            </Panel>
            
            <PanelResizeHandle className="w-1 bg-slate-200 hover:bg-brand-teal transition-colors cursor-col-resize" />
            
            {/* Center Pane: Consolidation Canvas (50%) */}
            <Panel defaultSize={50} minSize={30} className="bg-slate-50">
              <ConsolidationCanvas 
                projectId={projectId} 
                setProjectId={setProjectId}
                discipline={discipline}
              />
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
